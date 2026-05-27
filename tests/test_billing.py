"""Tests for Stripe billing routes.

The webhook MUST require a signed event; the previous "skip-verification
when secret unset" fallback was a critical-severity bug — the test that
encoded it as passing behaviour has been inverted.
"""

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
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.delenv("STRIPE_TEST_KEY", raising=False)
        monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
        resp = client.post(
            "/v1/billing/checkout-session",
            headers={"X-API-Key": TEST_KEY},
            json={
                "success_url": "https://example.com/ok",
                "cancel_url": "https://example.com/cancel",
            },
        )
        assert resp.status_code == 503

    def test_200_with_mock_stripe(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_FAKE")
        monkeypatch.setenv("STRIPE_PRICE_ID", "price_FAKE")

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/fake"
        mock_session.id = "cs_test_FAKE"

        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            resp = client.post(
                "/v1/billing/checkout-session",
                headers={"X-API-Key": TEST_KEY},
                json={
                    "success_url": "https://example.com/ok",
                    "cancel_url": "https://example.com/cancel",
                    "customer_email": "buyer@example.com",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "checkout_url" in data
        assert "session_id" in data

        kwargs = mock_create.call_args.kwargs
        assert kwargs["mode"] == "subscription"
        assert kwargs["customer_email"] == "buyer@example.com"
        assert kwargs["billing_address_collection"] == "required"
        assert kwargs["tax_id_collection"] == {"enabled": True}
        assert kwargs["automatic_tax"] == {"enabled": True}
        assert kwargs["metadata"]["customer_id"] == "test_customer"
        assert "api_key_hash" in kwargs["metadata"]

    def test_annual_plan_uses_annual_price(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_FAKE")
        monkeypatch.setenv("STRIPE_PRICE_ID", "price_MONTHLY")
        monkeypatch.setenv("STRIPE_PRICE_ID_ANNUAL", "price_ANNUAL")

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/fake"
        mock_session.id = "cs_test_ANNUAL"

        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            resp = client.post(
                "/v1/billing/checkout-session",
                headers={"X-API-Key": TEST_KEY},
                json={
                    "success_url": "https://example.com/ok",
                    "cancel_url": "https://example.com/cancel",
                    "plan": "annual",
                },
            )
        assert resp.status_code == 200
        kwargs = mock_create.call_args.kwargs
        assert kwargs["line_items"][0]["price"] == "price_ANNUAL"


class TestWebhook:
    def test_503_when_stripe_not_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.delenv("STRIPE_TEST_KEY", raising=False)
        resp = client.post(
            "/v1/billing/webhook",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 503

    def test_503_when_webhook_secret_unset(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Refuse to process unsigned webhooks — no dev-mode fallback."""
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_FAKE")
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        resp = client.post(
            "/v1/billing/webhook",
            content=b'{"type":"checkout.session.completed"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 503
        assert "unsigned" in resp.json()["detail"].lower()

    def test_503_when_webhook_secret_is_placeholder(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Treat the README placeholder as if it were unset."""
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_FAKE")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_REPLACE_ME")
        resp = client.post(
            "/v1/billing/webhook",
            content=b'{"type":"checkout.session.completed"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 503

    def test_400_when_signature_invalid(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_FAKE")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_real")

        def _raise(*_a: object, **_k: object) -> None:
            raise ValueError("bad sig")

        with patch("stripe.Webhook.construct_event", side_effect=_raise):
            resp = client.post(
                "/v1/billing/webhook",
                content=b'{"type":"checkout.session.completed"}',
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "garbage",
                },
            )
        assert resp.status_code == 400

    def test_signed_event_flips_tier(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_FAKE")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_real")

        from dcm_anon_vault.auth import hash_key
        from tests.conftest import TEST_CUSTOMER_ID
        from tests.conftest import TEST_KEY as _TK

        key_hash = hash_key(_TK)
        # First make a successful upload so the Customer row exists.
        with patch("dcm_anon_vault.routes.anonymize.anonymize_files_to_zip") as mock:
            from dcm_anon_vault.core import AuditSummary

            mock.return_value = (b"PK\x05\x06" + b"\x00" * 18, AuditSummary(1, 0, 0, "a" * 64))
            r = client.post(
                "/v1/anonymize",
                headers={"X-API-Key": _TK},
                files={"files": ("x.dcm", b"DICOM-bytes", "application/octet-stream")},
            )
            assert r.status_code == 200

        signed_event = {
            "id": "evt_test_001",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {
                        "customer_id": TEST_CUSTOMER_ID,
                        "api_key_hash": key_hash,
                    },
                    "id": "cs_test_FAKE",
                    "customer": "cus_test",
                }
            },
        }
        with patch("stripe.Webhook.construct_event", return_value=signed_event):
            resp = client.post(
                "/v1/billing/webhook",
                content=json.dumps(signed_event).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "ok",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"

        # Replay the same event — must be deduped.
        with patch("stripe.Webhook.construct_event", return_value=signed_event):
            resp2 = client.post(
                "/v1/billing/webhook",
                content=json.dumps(signed_event).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "ok",
                },
            )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "duplicate"


class TestPortalSession:
    """Self-service Stripe Customer Portal for cancel / update."""

    def test_503_when_stripe_not_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("STRIPE_API_KEY", raising=False)
        monkeypatch.delenv("STRIPE_TEST_KEY", raising=False)
        resp = client.post(
            "/v1/billing/portal-session",
            headers={"X-API-Key": TEST_KEY},
            json={"return_url": "https://example.com/account"},
        )
        assert resp.status_code == 503

    def test_404_when_no_stripe_customer_on_file(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A customer who has not completed checkout has no portal."""
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_FAKE")
        # Ensure a Customer row exists (no stripe_customer_id yet).
        with patch("dcm_anon_vault.routes.anonymize.anonymize_files_to_zip") as mock:
            from dcm_anon_vault.core import AuditSummary

            mock.return_value = (
                b"PK\x05\x06" + b"\x00" * 18,
                AuditSummary(1, 0, 0, "a" * 64),
            )
            r = client.post(
                "/v1/anonymize",
                headers={"X-API-Key": TEST_KEY},
                files={"files": ("x.dcm", b"DICOM-bytes", "application/octet-stream")},
            )
            assert r.status_code == 200

        resp = client.post(
            "/v1/billing/portal-session",
            headers={"X-API-Key": TEST_KEY},
            json={"return_url": "https://example.com/account"},
        )
        assert resp.status_code == 404
        assert "checkout" in resp.json()["detail"].lower()

    def test_200_with_mock_stripe(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_FAKE")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_real")

        # Seed: do a checkout webhook so the row carries stripe_customer_id.
        from dcm_anon_vault.auth import hash_key
        from tests.conftest import TEST_CUSTOMER_ID
        from tests.conftest import TEST_KEY as _TK

        key_hash = hash_key(_TK)
        with patch("dcm_anon_vault.routes.anonymize.anonymize_files_to_zip") as mock:
            from dcm_anon_vault.core import AuditSummary

            mock.return_value = (
                b"PK\x05\x06" + b"\x00" * 18,
                AuditSummary(1, 0, 0, "a" * 64),
            )
            client.post(
                "/v1/anonymize",
                headers={"X-API-Key": _TK},
                files={"files": ("x.dcm", b"DICOM-bytes", "application/octet-stream")},
            )

        signed_event = {
            "id": "evt_portal_seed",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {
                        "customer_id": TEST_CUSTOMER_ID,
                        "api_key_hash": key_hash,
                    },
                    "id": "cs_test_PORTAL",
                    "customer": "cus_portal_test",
                }
            },
        }
        with patch("stripe.Webhook.construct_event", return_value=signed_event):
            client.post(
                "/v1/billing/webhook",
                content=json.dumps(signed_event).encode(),
                headers={"Content-Type": "application/json", "Stripe-Signature": "ok"},
            )

        mock_portal = MagicMock()
        mock_portal.url = "https://billing.stripe.com/p/session/fake"

        with patch(
            "stripe.billing_portal.Session.create", return_value=mock_portal
        ) as mock_create:
            resp = client.post(
                "/v1/billing/portal-session",
                headers={"X-API-Key": _TK},
                json={"return_url": "https://example.com/account"},
            )
        assert resp.status_code == 200
        assert resp.json()["portal_url"] == "https://billing.stripe.com/p/session/fake"
        kwargs = mock_create.call_args.kwargs
        assert kwargs["customer"] == "cus_portal_test"
        assert kwargs["return_url"] == "https://example.com/account"


class TestSubscriptionLifecycle:
    """``customer.subscription.deleted`` / ``.updated`` webhook handling.

    Cancellation in Stripe MUST flip the in-app tier back to free without
    operator intervention (EU consumer-protection requirement).
    """

    def _seed_pro_customer(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, stripe_customer: str
    ) -> str:
        """Make TEST_KEY a Pro customer with the given stripe_customer_id."""
        monkeypatch.setenv("STRIPE_API_KEY", "sk_test_FAKE")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_real")

        from dcm_anon_vault.auth import hash_key
        from tests.conftest import TEST_CUSTOMER_ID
        from tests.conftest import TEST_KEY as _TK

        key_hash = hash_key(_TK)
        with patch("dcm_anon_vault.routes.anonymize.anonymize_files_to_zip") as mock:
            from dcm_anon_vault.core import AuditSummary

            mock.return_value = (
                b"PK\x05\x06" + b"\x00" * 18,
                AuditSummary(1, 0, 0, "a" * 64),
            )
            client.post(
                "/v1/anonymize",
                headers={"X-API-Key": _TK},
                files={"files": ("x.dcm", b"DICOM-bytes", "application/octet-stream")},
            )

        seed_event = {
            "id": f"evt_seed_{stripe_customer}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {
                        "customer_id": TEST_CUSTOMER_ID,
                        "api_key_hash": key_hash,
                    },
                    "id": "cs_test_seed",
                    "customer": stripe_customer,
                }
            },
        }
        with patch("stripe.Webhook.construct_event", return_value=seed_event):
            client.post(
                "/v1/billing/webhook",
                content=json.dumps(seed_event).encode(),
                headers={"Content-Type": "application/json", "Stripe-Signature": "ok"},
            )
        return _TK

    def _usage_tier(self, client: TestClient, key: str) -> str:
        r = client.get("/v1/usage", headers={"X-API-Key": key})
        assert r.status_code == 200, r.text
        return str(r.json()["tier"])

    def test_subscription_deleted_flips_to_free(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key = self._seed_pro_customer(client, monkeypatch, "cus_lifecycle_a")
        assert self._usage_tier(client, key) == "pro"

        deleted_event = {
            "id": "evt_sub_deleted_001",
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_X", "customer": "cus_lifecycle_a"}},
        }
        with patch("stripe.Webhook.construct_event", return_value=deleted_event):
            resp = client.post(
                "/v1/billing/webhook",
                content=json.dumps(deleted_event).encode(),
                headers={"Content-Type": "application/json", "Stripe-Signature": "ok"},
            )
        assert resp.status_code == 200
        assert self._usage_tier(client, key) == "free"

    def test_subscription_updated_canceled_flips_to_free(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key = self._seed_pro_customer(client, monkeypatch, "cus_lifecycle_b")
        assert self._usage_tier(client, key) == "pro"

        upd_event = {
            "id": "evt_sub_updated_canceled",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_Y",
                    "customer": "cus_lifecycle_b",
                    "status": "canceled",
                }
            },
        }
        with patch("stripe.Webhook.construct_event", return_value=upd_event):
            resp = client.post(
                "/v1/billing/webhook",
                content=json.dumps(upd_event).encode(),
                headers={"Content-Type": "application/json", "Stripe-Signature": "ok"},
            )
        assert resp.status_code == 200
        assert self._usage_tier(client, key) == "free"

    def test_subscription_updated_active_keeps_pro(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key = self._seed_pro_customer(client, monkeypatch, "cus_lifecycle_c")
        assert self._usage_tier(client, key) == "pro"

        upd_event = {
            "id": "evt_sub_updated_active",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_Z",
                    "customer": "cus_lifecycle_c",
                    "status": "active",
                }
            },
        }
        with patch("stripe.Webhook.construct_event", return_value=upd_event):
            resp = client.post(
                "/v1/billing/webhook",
                content=json.dumps(upd_event).encode(),
                headers={"Content-Type": "application/json", "Stripe-Signature": "ok"},
            )
        assert resp.status_code == 200
        assert self._usage_tier(client, key) == "pro"
