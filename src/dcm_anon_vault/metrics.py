"""Prometheus metrics for dcm-anon-vault.

Exposes three counters scraped via ``GET /metrics`` (open path):

* ``anonymize_requests_total{tenant,status}`` — every POST /v1/anonymize
  outcome (200, 4xx, 5xx labeled by HTTP status).
* ``anonymize_bytes_processed_total{tenant}`` — sum of input bytes
  processed by the engine.
* ``billing_events_total{tenant,kind}`` — webhook events flipping tier
  / deadletter / etc.

We deliberately use a custom registry instance so unit tests can
construct a fresh registry and avoid cross-test pollution.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter

REGISTRY: CollectorRegistry = CollectorRegistry()

ANONYMIZE_REQUESTS_TOTAL: Counter = Counter(
    "anonymize_requests_total",
    "Count of POST /v1/anonymize requests, labelled by tenant and HTTP status.",
    labelnames=("tenant", "status"),
    registry=REGISTRY,
)

ANONYMIZE_BYTES_TOTAL: Counter = Counter(
    "anonymize_bytes_processed_total",
    "Total bytes of input DICOM payload processed (post-upload, pre-anonymize).",
    labelnames=("tenant",),
    registry=REGISTRY,
)

BILLING_EVENTS_TOTAL: Counter = Counter(
    "billing_events_total",
    "Billing/webhook events received and processed, labelled by tenant and kind.",
    labelnames=("tenant", "kind"),
    registry=REGISTRY,
)


def record_anonymize_request(tenant: str, status_code: int) -> None:
    ANONYMIZE_REQUESTS_TOTAL.labels(tenant=tenant, status=str(status_code)).inc()


def record_anonymize_bytes(tenant: str, n_bytes: int) -> None:
    if n_bytes > 0:
        ANONYMIZE_BYTES_TOTAL.labels(tenant=tenant).inc(n_bytes)


def record_billing_event(tenant: str, kind: str) -> None:
    BILLING_EVENTS_TOTAL.labels(tenant=tenant, kind=kind).inc()
