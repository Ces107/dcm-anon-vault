"""API key authentication middleware for dcm-anon-vault.

Reads DCM_API_KEYS env var (comma-separated customer_id:key pairs), hashes each
key with SHA-256, and validates the X-API-Key header against the hash table.
Attaches request.state.customer_id on success; returns 401 on failure.
"""

from __future__ import annotations

import hashlib
import os

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


def _parse_api_keys(raw: str) -> dict[str, str]:
    """Parse 'id1:key1,id2:key2' into {sha256(key): customer_id}."""
    result: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split(":", 1)
        if len(parts) != 2:
            continue
        customer_id, key = parts[0].strip(), parts[1].strip()
        if customer_id and key:
            key_hash = hashlib.sha256(key.encode()).hexdigest()
            result[key_hash] = customer_id
    return result


def _load_key_map() -> dict[str, str]:
    raw = os.environ.get("DCM_API_KEYS", "")
    return _parse_api_keys(raw)


# ---------------------------------------------------------------------------
# Public helpers (used by tests and routes)
# ---------------------------------------------------------------------------

def parse_api_keys(raw: str) -> dict[str, str]:
    """Public wrapper around _parse_api_keys for testability."""
    return _parse_api_keys(raw)


def hash_key(raw_key: str) -> str:
    """SHA-256 hex of a raw API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


# Paths that do not require authentication
_OPEN_PATHS = {"/health", "/openapi.json", "/docs", "/redoc", "/v1/billing/webhook"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates X-API-Key on every protected route."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in _OPEN_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing X-API-Key header"},
            )

        key_map = _load_key_map()
        key_hash = hash_key(api_key)
        customer_id = key_map.get(key_hash)
        if customer_id is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid API key"},
            )

        request.state.customer_id = customer_id
        return await call_next(request)


def require_customer(request: Request) -> str:
    """FastAPI dependency: return customer_id or raise 401."""
    customer_id: str | None = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return customer_id
