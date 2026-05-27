"""FastAPI application factory."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dcm_anon_vault import __version__
from dcm_anon_vault.auth import APIKeyMiddleware
from dcm_anon_vault.db import init_db
from dcm_anon_vault.logging_setup import RequestLogMiddleware, configure_logging
from dcm_anon_vault.rate_limit import RateLimitMiddleware
from dcm_anon_vault.routes.anonymize import router as anonymize_router
from dcm_anon_vault.routes.audit import router as audit_router
from dcm_anon_vault.routes.billing import router as billing_router
from dcm_anon_vault.routes.health import router as health_router
from dcm_anon_vault.routes.metrics import router as metrics_router
from dcm_anon_vault.routes.retention import router as retention_router
from dcm_anon_vault.routes.usage import router as usage_router
from dcm_anon_vault.routes.webhooks import router as webhooks_router


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield


def _docs_open() -> bool:
    return os.environ.get("DCM_OPEN_DOCS", "").lower() in {"1", "true", "yes"}


def _logging_enabled() -> bool:
    # Default ON; tests can disable via DCM_DISABLE_JSON_LOG=1 to avoid noise.
    return os.environ.get("DCM_DISABLE_JSON_LOG", "").lower() not in {"1", "true", "yes"}


if _logging_enabled():
    configure_logging(os.environ.get("DCM_LOG_LEVEL", "INFO"))


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

# Middleware order matters; Starlette runs them in reverse-insertion order
# (outer = last added). We want, on the request path:
#   RequestLog -> APIKey (sets state.customer_id) -> RateLimit (reads it)
# So add in reverse: RateLimit first, then APIKey, then RequestLog.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(RequestLogMiddleware)

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(anonymize_router)
app.include_router(billing_router)
app.include_router(usage_router)
app.include_router(audit_router)
app.include_router(webhooks_router)
app.include_router(retention_router)
