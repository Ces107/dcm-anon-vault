"""Tests for Stripe billing routes."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_KEY


class TestCheckoutSession:
    def test_503_when_stripe_not_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("STRIPE_TEST_KEY", raising=False)
        monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
        resp = client.post(
            "/v1/billing/checkout-session",
            headers={"X-API-Key": TEST_KEY},
            json={"success_url": "https://example.com/ok", "cancel_url": "https://example.com/cancel"},
        )
        assert resp.status_code == 503

    def test_200_with_mock_stripe(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_TEST_KEY", "sk_test_FAKE")
        monkeypatch.setenv("STRIPE_PRICE_ID", "price_FAKE")

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/fake"
        mock_session.id = "cs_test_FAKE"

        with patch("stripe.checkout.Session.create", return_value=mock_session):
            resp = client.post(
                "/v1/billing/checkout-session",
                headers={"X-API-Key": TEST_KEY},
                json={
                    "success_url": "https://example.com/ok",
                    "cancel_url": "https://example.com/cancel",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "checkout_url" in data
        assert "session_id" in data


class TestWebhook:
    def test_503_when_stripe_not_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("STRIPE_TEST_KEY", raising=False)
        resp = client.post(
            "/v1/billing/webhook",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 503

    def test_tier_flip_on_checkout_completed(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_TEST_KEY", "sk_test_FAKE")
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)

        payload = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"customer_id": "test_customer"},
                    "id": "cs_test_FAKE",
                }
            },
        }

        mock_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"customer_id": "test_customer"},
                    "id": "cs_test_FAKE",
                }
            },
        }

        with patch("stripe.Event.construct_from", return_value=mock_event):
            resp = client.post(
                "/v1/billing/webhook",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"
