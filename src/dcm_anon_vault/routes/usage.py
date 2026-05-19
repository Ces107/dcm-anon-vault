"""GET /v1/usage — current-month usage and quota for the calling customer."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dcm_anon_vault.auth import require_api_key_hash
from dcm_anon_vault.db import get_db
from dcm_anon_vault.models import AnonymizationEvent, Customer

router = APIRouter()

_FREE_TIER_MONTHLY_LIMIT = 50


class UsageResponse(BaseModel):
    tier: str
    files_used_mtd: int
    quota: int | None  # None on unlimited / Pro tier
    reset_at: str  # ISO-8601 UTC


def _month_reset_iso() -> str:
    now = datetime.now(timezone.utc)
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        nxt = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


@router.get("/v1/usage", response_model=UsageResponse)
def usage(
    api_key_hash: str = Depends(require_api_key_hash),
    db: Session = Depends(get_db),
) -> UsageResponse:
    """Return tier, files used this UTC month, monthly quota, and reset time."""
    customer = db.execute(
        select(Customer).where(Customer.api_key_hash == api_key_hash)
    ).scalar_one_or_none()
    tier = customer.tier if customer is not None else "free"

    used = 0
    if customer is not None:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        used = int(
            db.execute(
                select(func.coalesce(func.sum(AnonymizationEvent.file_count), 0))
                .where(AnonymizationEvent.customer_id == customer.id)
                .where(AnonymizationEvent.created_at >= month_start)
            ).scalar()
            or 0
        )

    quota: int | None = _FREE_TIER_MONTHLY_LIMIT if tier == "free" else None
    return UsageResponse(
        tier=tier, files_used_mtd=used, quota=quota, reset_at=_month_reset_iso()
    )
