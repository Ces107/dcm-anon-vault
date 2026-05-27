"""Tamper-evident hash chain over :class:`AnonymizationEvent` rows.

Each event row commits to the row that preceded it for the same
*global* event stream: ``row_hash = sha256(canonical_json({
    id, customer_id, file_count, audit_sha256, created_at, prev_hash
}))``.

Any retroactive edit to a past row breaks the chain at the affected
position; the verifier walks the chain and returns the first broken id
(or ``None`` on full success).

Design notes
------------
* Global chain (not per-customer) — simpler to verify, and an attacker
  with write access to one customer's rows would otherwise be able to
  rewrite that customer's history undetectably. Cross-customer chaining
  is the standard pattern for audit-chain integrity.
* No external timestamp authority — chain proves *order* + *immutability
  since each write*, not absolute time. RFC 3161 timestamping is
  out of scope here; document this honestly in ``docs/security.md``.
* Append-only by convention; we don't enforce it at the DB layer (the
  customer's DB admin can always drop the table). The verifier is the
  control.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from dcm_anon_vault.models import AnonymizationEvent

GENESIS_HASH = "0" * 64


def _canonical(row: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding for hashing (sorted keys, no whitespace)."""
    return json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()


def _canonical_ts(dt: datetime) -> str:
    """Normalize a datetime for hashing: UTC, no tzinfo, microsecond precision.

    SQLite drops tzinfo on round-trip, so the canonical form must be
    independent of whether tzinfo is present. We coerce to UTC then strip
    tzinfo before serialising.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def compute_row_hash(
    *,
    row_id: int | None,
    customer_id: int,
    file_count: int,
    audit_sha256: str,
    created_at: datetime,
    prev_hash: str,
) -> str:
    """Compute the canonical ``row_hash`` for a chain entry."""
    payload = {
        "id": row_id,
        "customer_id": customer_id,
        "file_count": file_count,
        "audit_sha256": audit_sha256,
        "created_at": _canonical_ts(created_at),
        "prev_hash": prev_hash,
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def latest_chain_head(db: Session) -> str:
    """Return the ``row_hash`` of the latest event, or :data:`GENESIS_HASH`."""
    stmt = select(AnonymizationEvent).order_by(AnonymizationEvent.id.desc()).limit(1)
    last = db.execute(stmt).scalar_one_or_none()
    if last is None or not last.row_hash:
        return GENESIS_HASH
    return last.row_hash


def stamp_event(db: Session, event: AnonymizationEvent) -> None:
    """Populate ``prev_hash`` + ``row_hash`` on an unsaved event.

    Caller is responsible for ``db.add(event); db.commit()`` after this.
    The event must already have ``customer_id`` / ``file_count`` /
    ``audit_sha256`` / ``created_at`` set; ``id`` may be None (then
    rehashed after first flush, see :func:`finalize_event_id`).
    """
    event.prev_hash = latest_chain_head(db)
    # We compute with id=None first; after the row is flushed and assigned
    # an id, the verifier recomputes with the real id, so we MUST recompute
    # the row_hash post-flush. We do it inline:
    event.row_hash = compute_row_hash(
        row_id=event.id,
        customer_id=event.customer_id,
        file_count=event.file_count,
        audit_sha256=event.audit_sha256,
        created_at=event.created_at,
        prev_hash=event.prev_hash,
    )


def finalize_event_id(db: Session, event: AnonymizationEvent) -> None:
    """Recompute ``row_hash`` once the autoincrement id is assigned.

    Call after ``db.flush()`` (so ``event.id`` is populated) and before
    final commit. This keeps the canonical row hash inclusive of the
    primary key.
    """
    event.row_hash = compute_row_hash(
        row_id=event.id,
        customer_id=event.customer_id,
        file_count=event.file_count,
        audit_sha256=event.audit_sha256,
        created_at=event.created_at,
        prev_hash=event.prev_hash,
    )


def verify_chain(db: Session) -> int | None:
    """Walk the event chain in order. Return the first broken event id, else None.

    Returns ``None`` on success (empty table or fully valid chain).
    """
    stmt = select(AnonymizationEvent).order_by(AnonymizationEvent.id.asc())
    expected_prev = GENESIS_HASH
    for row in db.execute(stmt).scalars():
        if row.prev_hash != expected_prev:
            return int(row.id)
        recomputed = compute_row_hash(
            row_id=row.id,
            customer_id=row.customer_id,
            file_count=row.file_count,
            audit_sha256=row.audit_sha256,
            created_at=row.created_at,
            prev_hash=row.prev_hash,
        )
        if recomputed != row.row_hash:
            return int(row.id)
        expected_prev = row.row_hash
    return None
