"""Health check route — returns 503 if the DB is unreachable."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from dcm_anon_vault import __version__
from dcm_anon_vault.db import db_alive

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return service health and version. 503 if the DB SELECT 1 fails."""
    if not db_alive():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    return HealthResponse(status="ok", version=__version__)
