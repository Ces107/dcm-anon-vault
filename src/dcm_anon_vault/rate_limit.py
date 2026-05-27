"""Per-tenant rate-limiting middleware.

Fixed-window in-memory limiter (60 s windows). Per-tenant limit is taken
in this priority order:

1. ``Customer.rate_limit_per_minute`` DB column if set (>0).
2. Tier-default env: ``DCM_RATE_LIMIT_<TIER>`` (e.g. ``DCM_RATE_LIMIT_FREE``).
3. Hardcoded fallback: ``free=30/min``, ``pro=600/min``, ``enterprise=6000/min``.

On limit hit responds 429 with ``Retry-After`` (seconds until window reset).

In-memory state is per-process; for multi-worker deployments use a
shared store (Redis) — left as an interface concern (see
``docs/security.md`` § DoS posture).
"""

from __future__ import annotations

import os
import threading
import time

from fastapi import status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from dcm_anon_vault.db import _get_session_factory
from dcm_anon_vault.models import Customer

# Optional override for the session factory (set by tests via conftest so
# rate-limit reads from the same in-memory DB the rest of the app uses).
_session_factory_override: sessionmaker[Session] | None = None


def set_session_factory_for_test(factory: sessionmaker[Session] | None) -> None:
    """Test seam: override the session factory used by the middleware."""
    global _session_factory_override
    _session_factory_override = factory

_WINDOW_SECONDS = 60

# Tier fallbacks if neither DB nor env override is set.
_TIER_DEFAULTS: dict[str, int] = {"free": 30, "pro": 600, "enterprise": 6000}

# Paths that bypass the limiter entirely (health, metrics, billing webhook).
_OPEN_PATHS: frozenset[str] = frozenset(
    {"/health", "/metrics", "/v1/billing/webhook"}
)
_OPEN_PREFIXES: tuple[str, ...] = ("/docs", "/redoc", "/openapi")


def _tier_default(tier: str) -> int:
    env_key = f"DCM_RATE_LIMIT_{tier.upper()}"
    raw = os.environ.get(env_key)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return _TIER_DEFAULTS.get(tier, _TIER_DEFAULTS["free"])


class _Window:
    __slots__ = ("count", "reset_at")

    def __init__(self, reset_at: float) -> None:
        self.count: int = 0
        self.reset_at: float = reset_at


class RateLimiter:
    """In-process fixed-window counter, keyed by api_key_hash."""

    def __init__(self) -> None:
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, now: float | None = None) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)``.

        ``retry_after_seconds`` is 0 when ``allowed`` is True.
        """
        ts = time.monotonic() if now is None else now
        with self._lock:
            win = self._windows.get(key)
            if win is None or ts >= win.reset_at:
                win = _Window(reset_at=ts + _WINDOW_SECONDS)
                self._windows[key] = win
            if win.count >= limit:
                return False, max(1, int(win.reset_at - ts))
            win.count += 1
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


# Module-level singleton used by the middleware.
_LIMITER = RateLimiter()


def get_limiter() -> RateLimiter:
    """Expose the singleton for tests."""
    return _LIMITER


def _lookup_customer_limit(api_key_hash: str) -> tuple[int, str]:
    """Return ``(limit_per_minute, tier)`` for the calling api-key.

    Falls back to ``(_TIER_DEFAULTS['free'], 'free')`` if the customer
    row does not yet exist (first call before /v1/anonymize seeds it).
    """
    factory = _session_factory_override or _get_session_factory()
    db = factory()
    try:
        stmt = select(Customer).where(Customer.api_key_hash == api_key_hash)
        cust = db.execute(stmt).scalar_one_or_none()
        if cust is None:
            return _tier_default("free"), "free"
        if cust.rate_limit_per_minute and cust.rate_limit_per_minute > 0:
            return int(cust.rate_limit_per_minute), str(cust.tier)
        return _tier_default(str(cust.tier)), str(cust.tier)
    except Exception:
        # If the customers table doesn't exist yet (cold start before
        # init_db has run), fall back to the most permissive default
        # rather than 500-ing legitimate requests.
        return _tier_default("free"), "free"
    finally:
        db.close()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce per-tenant requests-per-minute window."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path in _OPEN_PATHS or any(path.startswith(p) for p in _OPEN_PREFIXES):
            return await call_next(request)

        api_key_hash: str | None = getattr(request.state, "api_key_hash", None)
        if not api_key_hash:
            # Auth not yet established; let downstream auth handle 401.
            return await call_next(request)

        limit, _tier = _lookup_customer_limit(api_key_hash)
        allowed, retry_after = _LIMITER.check(api_key_hash, limit)
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"Rate limit exceeded ({limit}/min). Retry in {retry_after}s.",
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
