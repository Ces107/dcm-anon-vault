"""API-key authentication middleware.

Reads ``DCM_API_KEYS`` (``id1:key1,id2:key2``) at startup, indexes by
SHA-256(key), and validates the ``X-API-Key`` header. On success attaches
both ``request.state.customer_id`` (the human-friendly string) and
``request.state.api_key_hash`` (the column value used by the DB).
"""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


def _parse_api_keys(raw: str) -> dict[str, str]:
    """Parse ``'id1:key1,id2:key2'`` into ``{sha256(key): customer_id}``."""
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


def parse_api_keys(raw: str) -> dict[str, str]:
    """Public wrapper around :func:`_parse_api_keys`."""
    return _parse_api_keys(raw)


def hash_key(raw_key: str) -> str:
    """SHA-256 hex of a raw API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


_OPEN_PATHS = {"/health", "/v1/billing/webhook"}
# /docs, /redoc, /openapi.json are gated by DCM_OPEN_DOCS=1 (default off).


def _docs_open() -> bool:
    return os.environ.get("DCM_OPEN_DOCS", "").lower() in {"1", "true", "yes"}


def _docs_paths() -> set[str]:
    return {"/docs", "/redoc", "/openapi.json"} if _docs_open() else set()


def _load_key_map() -> dict[str, str]:
    raw = os.environ.get("DCM_API_KEYS", "")
    return _parse_api_keys(raw)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validates X-API-Key on every protected route."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in _OPEN_PATHS or request.url.path in _docs_paths():
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

        # Defence-in-depth: confirm the lookup with a constant-time compare
        # against the canonical hash (the dict lookup already matched, this
        # just hardens against future code that bypasses the hash).
        if not any(hmac.compare_digest(stored, key_hash) for stored in key_map):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid API key"},
            )

        request.state.customer_id = customer_id
        request.state.api_key_hash = key_hash
        return await call_next(request)


def require_customer(request: Request) -> str:
    """FastAPI dependency: return customer_id (human-friendly) or raise 401."""
    customer_id: str | None = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return customer_id


def require_api_key_hash(request: Request) -> str:
    """FastAPI dependency: return SHA-256(api_key) or raise 401."""
    key_hash: str | None = getattr(request.state, "api_key_hash", None)
    if not key_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return key_hash
