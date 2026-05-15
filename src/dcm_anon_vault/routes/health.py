"""Health check route."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from dcm_anon_vault import __version__

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return service health and version."""
    return HealthResponse(status="ok", version=__version__)
