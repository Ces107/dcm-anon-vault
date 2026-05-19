"""FastAPI application factory."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dcm_anon_vault import __version__
from dcm_anon_vault.auth import APIKeyMiddleware
from dcm_anon_vault.db import init_db
from dcm_anon_vault.routes.anonymize import router as anonymize_router
from dcm_anon_vault.routes.billing import router as billing_router
from dcm_anon_vault.routes.health import router as health_router
from dcm_anon_vault.routes.usage import router as usage_router


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield


def _docs_open() -> bool:
    return os.environ.get("DCM_OPEN_DOCS", "").lower() in {"1", "true", "yes"}


app = FastAPI(
    title="dcm-anon-vault",
    description=(
        "Hosted single-tenant DICOM pseudonymization API. "
        "Wraps the dcm-anon engine (PS3.15 Basic Confidentiality Profile)."
    ),
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if _docs_open() else None,
    redoc_url="/redoc" if _docs_open() else None,
    openapi_url="/openapi.json" if _docs_open() else None,
)

app.add_middleware(APIKeyMiddleware)

app.include_router(health_router)
app.include_router(anonymize_router)
app.include_router(billing_router)
app.include_router(usage_router)
