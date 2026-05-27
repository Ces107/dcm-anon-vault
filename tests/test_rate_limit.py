"""Tests for the per-tenant rate-limit middleware."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dcm_anon_vault.rate_limit import RateLimiter, get_limiter
from tests.conftest import TEST_KEY


class TestRateLimiterUnit:
    def test_allows_under_limit(self) -> None:
        limiter = RateLimiter()
        for _ in range(5):
            allowed, retry = limiter.check("k", limit=5)
            assert allowed is True
            assert retry == 0

    def test_blocks_at_limit(self) -> None:
        limiter = RateLimiter()
        for _ in range(3):
            limiter.check("k", limit=3)
        allowed, retry = limiter.check("k", limit=3)
        assert allowed is False
        assert retry >= 1

    def test_window_reset(self) -> None:
        limiter = RateLimiter()
        # Consume the budget at t=0.
        for _ in range(2):
            limiter.check("k", limit=2, now=0.0)
        blocked, _ = limiter.check("k", limit=2, now=0.0)
        assert blocked is False
        # Past the window.
        allowed, _ = limiter.check("k", limit=2, now=120.0)
        assert allowed is True

    def test_separate_keys_isolated(self) -> None:
        limiter = RateLimiter()
        for _ in range(3):
            limiter.check("a", limit=3)
        # 'b' has its own budget.
        allowed, _ = limiter.check("b", limit=3)
        assert allowed is True


class TestRateLimitMiddleware:
    def test_429_when_exceeded(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DCM_RATE_LIMIT_FREE", "2")
        # Health endpoint is open, so use /v1/usage.
        get_limiter().reset()
        r1 = client.get("/v1/usage", headers={"X-API-Key": TEST_KEY})
        r2 = client.get("/v1/usage", headers={"X-API-Key": TEST_KEY})
        r3 = client.get("/v1/usage", headers={"X-API-Key": TEST_KEY})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers

    def test_health_endpoint_not_rate_limited(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DCM_RATE_LIMIT_FREE", "1")
        get_limiter().reset()
        # /health is open; should never 429.
        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_metrics_endpoint_not_rate_limited(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DCM_RATE_LIMIT_FREE", "1")
        get_limiter().reset()
        for _ in range(5):
            resp = client.get("/metrics")
            assert resp.status_code == 200

    def test_reset_clears_state(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DCM_RATE_LIMIT_FREE", "1")
        get_limiter().reset()
        r1 = client.get("/v1/usage", headers={"X-API-Key": TEST_KEY})
        r2 = client.get("/v1/usage", headers={"X-API-Key": TEST_KEY})
        assert r1.status_code == 200
        assert r2.status_code == 429
        # Reset and try again.
        get_limiter().reset()
        r3 = client.get("/v1/usage", headers={"X-API-Key": TEST_KEY})
        assert r3.status_code == 200
