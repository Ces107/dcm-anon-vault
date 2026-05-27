"""GDPR Art 17 retention sweep.

Deletes :class:`AnonymizationEvent` rows older than the tenant's
``retention_days`` setting. Deadletter rows are also swept on the same
window (operator can audit failed deliveries within the window; after
that, they're personal-data-by-association and must be erased).

This is **per-tenant**, configurable via ``Customer.retention_days``
(default 30). The default aligns with EDPB's "storage limitation"
guidance for short-term processing logs.

Hash-chain interaction
----------------------
Deleting historical audit rows breaks the hash chain by design — the
operator MUST run ``/v1/audit/verify`` BEFORE a sweep if they wish to
prove chain integrity up to that point. Post-sweep, the chain restarts
from the oldest surviving row. This trade-off is documented in
``docs/compliance.md`` § "right to erasure vs immutable audit".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from dcm_anon_vault.models import AnonymizationEvent, Customer, WebhookDeadletter


@dataclass(frozen=True)
class RetentionReport:
    customer_id: int
    retention_days: int
    events_deleted: int
    deadletter_deleted: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sweep_customer(
    db: Session, customer: Customer, *, now: datetime | None = None
) -> RetentionReport:
    """Delete expired rows for one customer; return :class:`RetentionReport`."""
    current = now or _utc_now()
    cutoff = current - timedelta(days=int(customer.retention_days))

    events_stmt = delete(AnonymizationEvent).where(
        AnonymizationEvent.customer_id == customer.id,
        AnonymizationEvent.created_at < cutoff,
    )
    deadletter_stmt = delete(WebhookDeadletter).where(
        WebhookDeadletter.customer_id == customer.id,
        WebhookDeadletter.created_at < cutoff,
    )

    events_result = db.execute(events_stmt)
    deadletter_result = db.execute(deadletter_stmt)
    db.commit()

    events_count = getattr(events_result, "rowcount", 0) or 0
    deadletter_count = getattr(deadletter_result, "rowcount", 0) or 0
    return RetentionReport(
        customer_id=customer.id,
        retention_days=int(customer.retention_days),
        events_deleted=int(events_count),
        deadletter_deleted=int(deadletter_count),
    )


def sweep_all(db: Session, *, now: datetime | None = None) -> list[RetentionReport]:
    """Sweep every customer; returns a list of per-tenant reports."""
    customers = list(db.execute(select(Customer)).scalars())
    return [sweep_customer(db, c, now=now) for c in customers]
