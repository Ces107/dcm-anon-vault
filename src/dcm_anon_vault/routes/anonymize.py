"""POST /v1/anonymize — multipart DICOM upload, returns ZIP + audit log."""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dcm_anon_vault.audit_chain import finalize_event_id, stamp_event
from dcm_anon_vault.auth import require_api_key_hash, require_customer
from dcm_anon_vault.core import AuditSummary, BurnedInPHIError, anonymize_files_to_zip
from dcm_anon_vault.db import get_db
from dcm_anon_vault.metrics import (
    record_anonymize_bytes,
    record_anonymize_request,
)
from dcm_anon_vault.models import AnonymizationEvent, Customer
from dcm_anon_vault.webhook_delivery import deliver_to_customer

router = APIRouter()

LOG = logging.getLogger("dcm_anon_vault.webhooks")

_FREE_TIER_MONTHLY_LIMIT = 50
_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB per request (multipart total)
_STREAM_CHUNK = 64 * 1024

# TD-046: shorter than webhook_delivery.DEFAULT_BACKOFF (1, 5, 25) so each
# background fan-out bounds threadpool occupancy at ~10.5 s per dead target
# (5 s HTTP timeout + 0.5 s sleep + 5 s HTTP timeout; the trailing sleep is
# gated off by `if attempt < len(backoff)` in deliver_with_retries). Loses
# one transient-5xx retry vs the library default; deadletter is unchanged
# so admin can replay via /v1/webhooks/deadletter.
_BG_WEBHOOK_BACKOFF: tuple[float, ...] = (0.5, 2.0)


def _get_or_create_customer(
    db: Session, *, customer_id: str, api_key_hash: str
) -> Customer:
    """Return or create a Customer keyed by ``api_key_hash``.

    Race-safe: if two workers create concurrently, the second hits the
    unique constraint, rolls back, and re-selects the winner's row.
    """
    stmt = select(Customer).where(Customer.api_key_hash == api_key_hash)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing

    new_customer = Customer(
        api_key_hash=api_key_hash, customer_id_string=customer_id, tier="free"
    )
    db.add(new_customer)
    try:
        db.commit()
        db.refresh(new_customer)
        return new_customer
    except IntegrityError:
        db.rollback()
        return db.execute(stmt).scalar_one()


def _monthly_file_count(db: Session, customer_id_pk: int) -> int:
    """Sum file_count for the current UTC calendar month."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.coalesce(func.sum(AnonymizationEvent.file_count), 0))
        .where(AnonymizationEvent.customer_id == customer_id_pk)
        .where(AnonymizationEvent.created_at >= month_start)
    )
    result = db.execute(stmt).scalar()
    return int(result) if result is not None else 0


def _safe_filename(name: str | None) -> str:
    """Strip directory components from an attacker-controlled filename."""
    if not name:
        return "upload.dcm"
    return Path(name).name or "upload.dcm"


def _fan_out_webhooks_bg(
    *, customer_pk: int, event_type: str, payload: dict[str, object]
) -> None:
    """Deliver outgoing webhooks on its own DB session, off the request path.

    Runs as a FastAPI BackgroundTask AFTER the anonymize response has been
    sent. Uses ``_BG_WEBHOOK_BACKOFF`` (shorter than the library default) so
    a slow or dead customer endpoint bounds at ~10.5 s per target instead of
    ~21 s, protecting the Starlette threadpool from saturation under burst
    load to dead endpoints (TD-046). Final delivery failures still write a
    ``WebhookDeadletter`` row inside ``deliver_to_customer``; admin can
    replay via ``GET /v1/webhooks/deadletter``. Opens a short-lived session
    because the request-scoped session is already closed by the time a
    background task runs.
    """
    import asyncio

    from dcm_anon_vault.db import _get_session_factory

    db = None
    try:
        db = _get_session_factory()()
        asyncio.run(
            deliver_to_customer(
                db,
                customer_id=customer_pk,
                event_type=event_type,
                payload=payload,
                backoff=_BG_WEBHOOK_BACKOFF,
            )
        )
    except Exception as exc:  # TD-045: setup + delivery + cleanup were silent
        # Background best-effort: delivery failures are deadlettered inside
        # deliver_to_customer; anything escaping here is swallowed so the
        # background worker does not crash. We DO log so a DB-pool / import
        # / event-loop failure is at least visible in structured logs with
        # enough context to triage (customer + event + error type).
        LOG.warning(
            "background webhook fan-out failed",
            extra={
                "customer_pk": customer_pk,
                "event_type": event_type,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
    finally:
        if db is not None:
            db.close()


def _enforce_size_cap(request: Request) -> None:
    """Reject requests whose Content-Length exceeds the cap."""
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > _MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Upload exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB cap.",
                )
        except ValueError:
            pass  # malformed header — let body parser handle it


@router.post("/v1/anonymize")
def anonymize(
    request: Request,
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    customer_id: str = Depends(require_customer),
    api_key_hash: str = Depends(require_api_key_hash),
    db: Session = Depends(get_db),
) -> Response:
    """Pseudonymize uploaded DICOM files (PS3.15 Basic Profile).

    Returns a ZIP archive of the scrubbed DICOMs. Rate-limits free-tier
    customers to 50 files / UTC calendar month. Rejects files declaring
    ``BurnedInAnnotation == YES`` (no Clean Pixel Data Option).
    """
    try:
        resp, summary, customer_pk = _anonymize_impl(
            request, files, customer_id, api_key_hash, db
        )
    except HTTPException as exc:
        record_anonymize_request(customer_id, exc.status_code)
        raise
    except Exception:
        record_anonymize_request(customer_id, 500)
        raise

    record_anonymize_request(customer_id, 200)

    # Webhook fan-out runs AFTER the response is sent (BackgroundTask), on
    # its own DB session. A slow/dead customer endpoint (5 s timeout, 2-retry
    # backoff capped at ~10.5 s per target — see _BG_WEBHOOK_BACKOFF, TD-046)
    # must not stall the user's upload response. Failures are deadlettered
    # inside deliver_to_customer.
    background_tasks.add_task(
        _fan_out_webhooks_bg,
        customer_pk=customer_pk,
        event_type="anonymize.completed",
        payload={
            "files_processed": summary.files_processed,
            "audit_sha256": summary.audit_sha256,
        },
    )

    return resp


def _anonymize_impl(
    request: Request,
    files: list[UploadFile],
    customer_id: str,
    api_key_hash: str,
    db: Session,
) -> tuple[Response, AuditSummary, int]:
    _enforce_size_cap(request)
    customer = _get_or_create_customer(
        db, customer_id=customer_id, api_key_hash=api_key_hash
    )

    if customer.tier == "free":
        used = _monthly_file_count(db, customer.id)
        remaining = _FREE_TIER_MONTHLY_LIMIT - used
        if remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Free tier limit of {_FREE_TIER_MONTHLY_LIMIT} files/month reached. "
                    "Upgrade via POST /v1/billing/checkout-session."
                ),
                headers={"Retry-After": "2592000"},
            )
        if len(files) > remaining:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Upload would exceed free-tier limit. "
                    f"Remaining this month: {remaining} files."
                ),
                headers={"Retry-After": "2592000"},
            )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src_paths: list[Path] = []
        bytes_seen = 0
        for upload in files:
            filename = _safe_filename(upload.filename)
            dest = tmp_path / filename
            with dest.open("wb") as out:
                while True:
                    chunk = upload.file.read(_STREAM_CHUNK)
                    if not chunk:
                        break
                    bytes_seen += len(chunk)
                    if bytes_seen > _MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                f"Upload exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB cap."
                            ),
                        )
                    out.write(chunk)
            src_paths.append(dest)

        record_anonymize_bytes(customer_id, bytes_seen)

        try:
            zip_bytes, summary = anonymize_files_to_zip(
                src_paths, customer_salt=api_key_hash
            )
        except BurnedInPHIError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    if summary.files_rejected_burned_in == len(files) and summary.files_processed == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "All uploaded files declared BurnedInAnnotation=YES. "
                "The PS3.15 Clean Pixel Data Option is not supported on this "
                "instance; remove or redact burned-in pixels before upload."
            ),
        )

    event = AnonymizationEvent(
        customer_id=customer.id,
        file_count=summary.files_processed,
        audit_sha256=summary.audit_sha256,
        created_at=datetime.now(timezone.utc),
    )
    # Hash chain: stamp prev_hash + row_hash. We flush to obtain the
    # autoincrement id, then recompute row_hash so the id is included.
    stamp_event(db, event)
    db.add(event)
    db.flush()
    finalize_event_id(db, event)
    db.commit()

    headers = {
        "Content-Disposition": "attachment; filename=anonymized.zip",
        "X-Files-Processed": str(summary.files_processed),
        "X-Files-Failed": str(summary.files_failed),
        "X-Files-Rejected-BurnedIn": str(summary.files_rejected_burned_in),
        "X-Audit-Sha256": summary.audit_sha256,
    }
    return (
        Response(content=zip_bytes, media_type="application/zip", headers=headers),
        summary,
        customer.id,
    )




__all__ = ["anonymize", "router"]
