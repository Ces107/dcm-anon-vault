"""Structured JSON logging for dcm-anon-vault.

Each log record is emitted as one JSON line with:

* ``ts``        — ISO-8601 UTC timestamp
* ``level``     — log level name (``INFO``/``WARNING``/...)
* ``logger``    — logger name
* ``msg``       — formatted message
* extra fields when present: ``request_id``, ``tenant``, ``route``,
  ``status``, ``duration_ms``, plus any ``logger.info("...", extra={...})``
  keys.

Use :func:`configure_logging` once at startup. The middleware
:class:`RequestLogMiddleware` adds the per-request fields automatically.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import datetime, timezone
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

LOG = logging.getLogger("dcm_anon_vault.access")

# Standard LogRecord attributes we don't want re-emitted as "extras".
_RESERVED: frozenset[str] = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "taskName", "asctime",
    }
)


class JsonFormatter(logging.Formatter):
    """Format log records as one-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install :class:`JsonFormatter` on the root + uvicorn loggers.

    Idempotent: re-running replaces the handler rather than stacking.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
        lg.setLevel(level)


class RequestLogMiddleware:
    """ASGI middleware that emits one JSON access log per request.

    Fields: ``request_id``, ``tenant``, ``route``, ``method``, ``status``,
    ``duration_ms``. ``tenant`` is filled by :class:`APIKeyMiddleware`
    (it sets ``request.state.customer_id``); for open paths the field is
    ``"anonymous"``.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        request_id = uuid.uuid4().hex[:16]
        status_code: int = 0

        async def _send(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 0))
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        # Make request_id available downstream via scope.
        scope.setdefault("state", {})
        # Starlette stores user state under scope["state"] (a dict).
        if isinstance(scope["state"], dict):
            scope["state"]["request_id"] = request_id

        try:
            await self.app(scope, receive, _send)
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            # Re-derive tenant from scope state if middleware downstream set it.
            tenant = "anonymous"
            state = scope.get("state")
            if isinstance(state, dict):
                tenant = str(state.get("customer_id") or "anonymous")
            request = Request(scope)
            LOG.info(
                "request",
                extra={
                    "request_id": request_id,
                    "tenant": tenant,
                    "route": request.url.path,
                    "method": request.method,
                    "status": status_code,
                    "duration_ms": duration_ms,
                },
            )


__all__ = [
    "JsonFormatter",
    "RequestLogMiddleware",
    "configure_logging",
]


# Touch unused import to satisfy linters that may not see Response above.
_ = Response
