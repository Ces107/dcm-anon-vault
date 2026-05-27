"""Admin audit endpoints: chain verification."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dcm_anon_vault.audit_chain import verify_chain
from dcm_anon_vault.auth import require_admin
from dcm_anon_vault.db import get_db

router = APIRouter()


class AuditVerifyResponse(BaseModel):
    status: str  # "ok" or "broken"
    first_broken_id: int | None = None


@router.get("/v1/audit/verify", response_model=AuditVerifyResponse)
def audit_verify(
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuditVerifyResponse:
    """Walk the anonymize-event hash chain. Returns OK or first broken id."""
    broken = verify_chain(db)
    if broken is None:
        return AuditVerifyResponse(status="ok", first_broken_id=None)
    return AuditVerifyResponse(status="broken", first_broken_id=broken)
