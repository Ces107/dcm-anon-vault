"""POST /v1/anonymize — multipart DICOM upload, returns ZIP + audit log."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dcm_anon_vault.auth import require_customer
from dcm_anon_vault.core import anonymize_files_to_zip
from dcm_anon_vault.db import get_db
from dcm_anon_vault.models import AnonymizationEvent, Customer

router = APIRouter()

_FREE_TIER_MONTHLY_LIMIT = 50


def _get_or_create_customer(db: Session, customer_id: str) -> Customer:
    """Return existing Customer row or create a new free-tier one."""
    stmt = select(Customer).where(Customer.api_key_hash == customer_id)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        return existing
    # Create a stub row; api_key_hash stores the customer_id string here because
    # the middleware has already validated the raw key — we only need an opaque ID.
    new_customer = Customer(api_key_hash=customer_id, tier="free")
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return new_customer


def _monthly_file_count(db: Session, customer_id_pk: int) -> int:
    """Count files anonymized by this customer in the current UTC calendar month."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.coalesce(func.sum(AnonymizationEvent.file_count), 0))
        .where(AnonymizationEvent.customer_id == customer_id_pk)
        .where(AnonymizationEvent.created_at >= month_start)
    )
    result = db.execute(stmt).scalar()
    return int(result) if result is not None else 0


@router.post("/v1/anonymize")
def anonymize(
    request: Request,
    files: list[UploadFile],
    customer_id: str = Depends(require_customer),
    db: Session = Depends(get_db),
) -> Response:
    """Anonymize uploaded DICOM files.

    Accepts one or more DICOM files as multipart form data.  Returns a ZIP
    archive containing anonymized DICOMs and an audit log.

    Rate-limits free-tier customers to 50 files per calendar month.
    """
    customer = _get_or_create_customer(db, customer_id)

    # Rate-limit check for free tier
    if customer.tier == "free":
        used = _monthly_file_count(db, customer.id)
        remaining = _FREE_TIER_MONTHLY_LIMIT - used
        if remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Free tier limit of {_FREE_TIER_MONTHLY_LIMIT} files/month reached. "
                    "Upgrade to Pro at /v1/billing/checkout-session."
                ),
                headers={"Retry-After": "2592000"},  # ~30 days
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

    # Write uploads to a temp directory and anonymize
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src_paths: list[Path] = []
        for upload in files:
            filename = upload.filename or "upload.dcm"
            dest = tmp_path / filename
            dest.write_bytes(upload.file.read())
            src_paths.append(dest)

        zip_bytes, summary = anonymize_files_to_zip(src_paths)

    # Persist the event
    event = AnonymizationEvent(
        customer_id=customer.id,
        file_count=summary.files_processed,
        audit_sha256=summary.audit_sha256,
    )
    db.add(event)
    db.commit()

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=anonymized.zip"},
    )
