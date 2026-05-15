"""FastAPI application factory for dcm-anon-vault."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dcm_anon_vault import __version__
from dcm_anon_vault.auth import APIKeyMiddleware
from dcm_anon_vault.db import init_db
from dcm_anon_vault.routes.anonymize import router as anonymize_router
from dcm_anon_vault.routes.billing import router as billing_router
from dcm_anon_vault.routes.health import router as health_router


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize DB on startup."""
    init_db()
    yield


app = FastAPI(
    title="dcm-anon-vault",
    description="Hosted single-tenant DICOM anonymization API.",
    version=__version__,
    lifespan=lifespan,
    # Disable CORS — single-tenant, API-key-only service.
    # Add CORSMiddleware only if you expose a browser-based UI later.
)

# Authentication middleware (runs before routes)
app.add_middleware(APIKeyMiddleware)

app.include_router(health_router)
app.include_router(anonymize_router)
app.include_router(billing_router)
