"""Tests for structured JSON logging."""

from __future__ import annotations

import io
import json
import logging

from dcm_anon_vault.logging_setup import JsonFormatter, configure_logging


def test_json_formatter_basic() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    line = formatter.format(record)
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert parsed["msg"] == "hello world"
    assert parsed["logger"] == "test"
    assert "ts" in parsed


def test_json_formatter_extras() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="m", args=None, exc_info=None,
    )
    record.tenant = "acme"
    record.request_id = "abc123"
    record.status = 200
    line = formatter.format(record)
    parsed = json.loads(line)
    assert parsed["tenant"] == "acme"
    assert parsed["request_id"] == "abc123"
    assert parsed["status"] == 200


def test_configure_logging_emits_json() -> None:
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("dcm_anon_vault.smoke")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.info("trial", extra={"tenant": "x", "duration_ms": 42})
    line = buf.getvalue().strip()
    parsed = json.loads(line)  # MUST be JSON-parseable
    assert parsed["msg"] == "trial"
    assert parsed["tenant"] == "x"
    assert parsed["duration_ms"] == 42


def test_configure_logging_idempotent() -> None:
    """Re-running configure_logging should not stack handlers."""
    configure_logging("INFO")
    root_handlers = len(logging.getLogger().handlers)
    configure_logging("INFO")
    assert len(logging.getLogger().handlers) == root_handlers
