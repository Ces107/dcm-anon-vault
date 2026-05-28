"""Tests for outgoing webhook delivery + deadletter + management endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest
import sqlalchemy.orm
from fastapi.testclient import TestClient

from dcm_anon_vault.models import Customer, OutgoingWebhook, WebhookDeadletter
from dcm_anon_vault.webhook_delivery import (
    deliver_to_customer,
    deliver_with_retries,
    sign_payload,
)
from tests.conftest import TEST_CUSTOMER_ID, TEST_KEY


def _mock_transport(responder: Any) -> httpx.AsyncClient:
    transport = httpx.MockTransport(responder)
    return httpx.AsyncClient(transport=transport)


def test_sign_payload_deterministic() -> None:
    secret = "topsecret"
    body = b'{"a":1}'
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert sign_payload(secret, body) == expected


def test_deliver_succeeds_first_try() -> None:
    calls = {"n": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True})

    async def run() -> Any:
        async with _mock_transport(responder) as cli:
            return await deliver_with_retries(
                url="https://example.test/hook",
                payload={"x": 1},
                secret="s",
                backoff=(0.0, 0.0, 0.0),
                client=cli,
            )

    result = asyncio.run(run())
    assert result.delivered is True
    assert result.attempts == 1
    assert calls["n"] == 1


def test_deliver_retries_until_success() -> None:
    calls = {"n": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500)
        return httpx.Response(200)

    async def run() -> Any:
        async with _mock_transport(responder) as cli:
            return await deliver_with_retries(
                url="https://example.test/hook",
                payload={"x": 1},
                secret=None,
                backoff=(0.0, 0.0, 0.0),
                client=cli,
            )

    result = asyncio.run(run())
    assert result.delivered is True
    assert result.attempts == 3
    assert calls["n"] == 3


def test_deliver_gives_up_after_all_retries() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async def run() -> Any:
        async with _mock_transport(responder) as cli:
            return await deliver_with_retries(
                url="https://example.test/hook",
                payload={"x": 1},
                secret=None,
                backoff=(0.0, 0.0, 0.0),
                client=cli,
            )

    result = asyncio.run(run())
    assert result.delivered is False
    assert result.attempts == 3
    assert result.last_status == 503


def test_deadletter_on_final_failure(db_session: sqlalchemy.orm.Session) -> None:
    cust = Customer(
        api_key_hash="z" * 64, customer_id_string="acme", tier="free"
    )
    db_session.add(cust)
    db_session.commit()
    db_session.refresh(cust)

    hook = OutgoingWebhook(
        customer_id=cust.id, url="https://example.test/h", secret="s", active=1
    )
    db_session.add(hook)
    db_session.commit()

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async def run() -> Any:
        async with _mock_transport(responder) as cli:
            return await deliver_to_customer(
                db_session,
                customer_id=cust.id,
                event_type="anonymize.completed",
                payload={"files_processed": 3},
                backoff=(0.0, 0.0, 0.0),
                client=cli,
            )

    asyncio.run(run())

    rows = db_session.query(WebhookDeadletter).all()
    assert len(rows) == 1
    payload = json.loads(rows[0].payload)
    assert payload["event"] == "anonymize.completed"
    assert payload["files_processed"] == 3


def test_deadletter_still_written_with_short_backoff(
    db_session: sqlalchemy.orm.Session,
) -> None:
    """TD-046: 2-tuple backoff (bg path) MUST still produce a deadletter row.

    Guards against a future refactor that accidentally requires
    ``len(backoff) == 3`` somewhere on the deadletter path.
    """
    cust = Customer(
        api_key_hash="y" * 64, customer_id_string="acme2", tier="free"
    )
    db_session.add(cust)
    db_session.commit()
    db_session.refresh(cust)

    hook = OutgoingWebhook(
        customer_id=cust.id, url="https://example.test/h2", secret="s", active=1
    )
    db_session.add(hook)
    db_session.commit()

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async def run() -> Any:
        async with _mock_transport(responder) as cli:
            return await deliver_to_customer(
                db_session,
                customer_id=cust.id,
                event_type="anonymize.completed",
                payload={"files_processed": 1},
                backoff=(0.0, 0.0),  # 2-tuple bg-path-shaped
                client=cli,
            )

    results = asyncio.run(run())
    assert len(results) == 1
    assert results[0].delivered is False
    assert results[0].attempts == 2

    rows = db_session.query(WebhookDeadletter).all()
    assert len(rows) == 1
    assert rows[0].attempts == 2
    assert rows[0].last_status == 503


class TestWebhookRoutes:
    def test_register_and_list_webhook(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/webhooks",
            headers={"X-API-Key": TEST_KEY},
            json={"url": "https://customer.example/hook", "secret": "topsecret"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://customer.example/hook"
        assert data["active"] is True

        listing = client.get("/v1/webhooks", headers={"X-API-Key": TEST_KEY})
        assert listing.status_code == 200
        assert len(listing.json()) >= 1

    def test_register_rejects_non_http(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/webhooks",
            headers={"X-API-Key": TEST_KEY},
            json={"url": "ftp://bad/url"},
        )
        assert resp.status_code == 400

    def test_deadletter_requires_admin(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DCM_ADMIN_KEYS", raising=False)
        resp = client.get(
            "/v1/webhooks/deadletter", headers={"X-API-Key": TEST_KEY}
        )
        assert resp.status_code == 403

    def test_deadletter_empty_for_admin(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DCM_ADMIN_KEYS", TEST_CUSTOMER_ID)
        resp = client.get(
            "/v1/webhooks/deadletter", headers={"X-API-Key": TEST_KEY}
        )
        assert resp.status_code == 200
        assert resp.json() == []
