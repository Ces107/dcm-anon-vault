"""GET /metrics — Prometheus exposition (open path)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from dcm_anon_vault.metrics import REGISTRY

router = APIRouter()


@router.get("/metrics")
def metrics() -> Response:
    """Expose Prometheus metrics. No auth — scrape-only endpoint.

    Mount behind a private network or an auth proxy in production
    (k8s NetworkPolicy / Fly internal port). The endpoint emits only
    counters; no PHI or secret material.
    """
    body = generate_latest(REGISTRY)
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)
