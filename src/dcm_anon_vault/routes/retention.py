"""Admin retention sweep endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dcm_anon_vault.auth import require_admin
from dcm_anon_vault.db import get_db
from dcm_anon_vault.retention import sweep_all

router = APIRouter()


class RetentionRow(BaseModel):
    customer_id: int
    retention_days: int
    events_deleted: int
    deadletter_deleted: int


class RetentionResponse(BaseModel):
    swept: int
    rows: list[RetentionRow]


@router.post("/v1/admin/retention/sweep", response_model=RetentionResponse)
def trigger_retention_sweep(
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RetentionResponse:
    """Run the retention sweep for all customers; return per-tenant counts.

    Idempotent; safe to run on a schedule (cron / k8s CronJob).
    """
    reports = sweep_all(db)
    return RetentionResponse(
        swept=len(reports),
        rows=[
            RetentionRow(
                customer_id=r.customer_id,
                retention_days=r.retention_days,
                events_deleted=r.events_deleted,
                deadletter_deleted=r.deadletter_deleted,
            )
            for r in reports
        ],
    )
