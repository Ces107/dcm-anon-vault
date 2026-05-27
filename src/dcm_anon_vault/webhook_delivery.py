"""Outgoing webhook delivery with retries + dead-letter queue.

Customers register a URL via ``POST /v1/webhooks`` to receive event
notifications (e.g. ``anonymize.completed``). Delivery semantics:

* 3 attempts with backoff 1 s → 5 s → 25 s.
* HMAC-SHA256 signature over the JSON payload using the customer's
  registered ``secret`` (``X-Webhook-Signature: sha256=<hex>``).
* On final failure, a row is inserted into ``webhook_deadletter``;
  inspectable by admin via ``GET /v1/webhooks/deadletter``.

The deliver function is **synchronous-friendly** (it uses ``httpx``
sync client) and bounded by a small inline thread (started by the
caller). For higher-throughput deployments swap in a task queue
(Celery / Arq / RQ); the interface here keeps the surface area honest
about what's implemented.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from dcm_anon_vault.models import OutgoingWebhook, WebhookDeadletter

LOG = logging.getLogger("dcm_anon_vault.webhook")

# Delays are tuned for unit tests via env / arg, defaults match docstring.
DEFAULT_BACKOFF: tuple[float, ...] = (1.0, 5.0, 25.0)


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    attempts: int
    last_status: int | None
    last_error: str | None


def sign_payload(secret: str, body: bytes) -> str:
    """Compute the ``X-Webhook-Signature`` header value."""
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


async def _post_once(
    client: httpx.AsyncClient,
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout: float,
) -> tuple[int | None, str | None]:
    try:
        resp = await client.post(url, content=body, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if 200 <= resp.status_code < 300:
        return resp.status_code, None
    return resp.status_code, f"HTTP {resp.status_code}"


async def deliver_with_retries(
    *,
    url: str,
    payload: dict[str, Any],
    secret: str | None,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF,
    timeout: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> DeliveryResult:
    """Try to POST ``payload`` to ``url`` up to ``len(backoff)`` times."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "dcm-anon-vault-webhook/1",
    }
    if secret:
        headers["X-Webhook-Signature"] = sign_payload(secret, body)

    own_client = client is None
    cli = client or httpx.AsyncClient()
    try:
        last_status: int | None = None
        last_error: str | None = None
        for attempt, delay in enumerate(backoff, start=1):
            status_code, err = await _post_once(cli, url, body, headers, timeout)
            last_status = status_code
            last_error = err
            if err is None:
                return DeliveryResult(True, attempt, status_code, None)
            if attempt < len(backoff):
                await asyncio.sleep(delay)
        return DeliveryResult(False, len(backoff), last_status, last_error)
    finally:
        if own_client:
            await cli.aclose()


async def deliver_to_customer(
    db: Session,
    *,
    customer_id: int,
    event_type: str,
    payload: dict[str, Any],
    backoff: tuple[float, ...] = DEFAULT_BACKOFF,
    client: httpx.AsyncClient | None = None,
) -> list[DeliveryResult]:
    """Deliver ``payload`` to every active webhook URL for ``customer_id``.

    Failed deliveries are written to :class:`WebhookDeadletter`.
    """
    stmt = (
        select(OutgoingWebhook)
        .where(OutgoingWebhook.customer_id == customer_id)
        .where(OutgoingWebhook.active == 1)
    )
    targets = list(db.execute(stmt).scalars())
    results: list[DeliveryResult] = []
    for target in targets:
        full_payload = {**payload, "event": event_type}
        result = await deliver_with_retries(
            url=target.url,
            payload=full_payload,
            secret=target.secret,
            backoff=backoff,
            client=client,
        )
        results.append(result)
        if not result.delivered:
            dl = WebhookDeadletter(
                customer_id=customer_id,
                url=target.url,
                event_type=event_type,
                payload=json.dumps(full_payload, sort_keys=True),
                last_status=result.last_status,
                last_error=result.last_error,
                attempts=result.attempts,
            )
            db.add(dl)
            db.commit()
            LOG.warning(
                "webhook delivery failed (deadlettered)",
                extra={
                    "tenant_id": customer_id,
                    "url": target.url,
                    "event_type": event_type,
                    "last_status": result.last_status,
                },
            )
    return results
