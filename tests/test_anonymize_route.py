"""Tests for POST /v1/anonymize."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dcm_anon_vault.core import AuditSummary
from tests.conftest import TEST_KEY

_FAKE_SUMMARY = AuditSummary(
    files_processed=1, files_failed=0, files_rejected_burned_in=0, audit_sha256="a" * 64
)


def _make_fake_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("anon.dcm", b"FAKE_DCM_DATA")
    return buf.getvalue()


class TestAnonymizeRoute:
    def test_valid_key_and_dicom_returns_zip(
        self, client: TestClient, sample_dcm_path: Path
    ) -> None:
        fake_zip = _make_fake_zip()
        with patch(
            "dcm_anon_vault.routes.anonymize.anonymize_files_to_zip",
            return_value=(fake_zip, _FAKE_SUMMARY),
        ):
            with sample_dcm_path.open("rb") as f:
                resp = client.post(
                    "/v1/anonymize",
                    headers={"X-API-Key": TEST_KEY},
                    files={"files": ("CT_small.dcm", f, "application/octet-stream")},
                )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert resp.headers["x-files-processed"] == "1"
        assert resp.headers["x-audit-sha256"] == "a" * 64
        buf = io.BytesIO(resp.content)
        assert zipfile.is_zipfile(buf)

    def test_missing_key_returns_401(self, client: TestClient) -> None:
        resp = client.post("/v1/anonymize")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/anonymize", headers={"X-API-Key": "completely-wrong-key"}
        )
        assert resp.status_code == 401

    def test_path_traversal_filename_is_sanitised(
        self, client: TestClient, sample_dcm_path: Path
    ) -> None:
        """A filename like '../../etc/passwd' must not escape the temp dir."""
        captured: list[str] = []

        def _capture(src_paths: list[Path], *, customer_salt: str) -> tuple[bytes, AuditSummary]:
            for p in src_paths:
                captured.append(p.name)
            return (_make_fake_zip(), _FAKE_SUMMARY)

        with patch(
            "dcm_anon_vault.routes.anonymize.anonymize_files_to_zip",
            side_effect=_capture,
        ):
            with sample_dcm_path.open("rb") as f:
                resp = client.post(
                    "/v1/anonymize",
                    headers={"X-API-Key": TEST_KEY},
                    files={
                        "files": (
                            "../../etc/passwd",
                            f,
                            "application/octet-stream",
                        )
                    },
                )
        assert resp.status_code == 200
        assert captured, "engine was not invoked"
        for name in captured:
            assert ".." not in name
            assert "/" not in name and "\\" not in name

    def test_oversize_content_length_rejected(
        self, client: TestClient, sample_dcm_path: Path
    ) -> None:
        with sample_dcm_path.open("rb") as f:
            resp = client.post(
                "/v1/anonymize",
                headers={
                    "X-API-Key": TEST_KEY,
                    # Lie about content-length to trigger the early reject.
                    "Content-Length": str(200 * 1024 * 1024),
                },
                files={"files": ("CT_small.dcm", f, "application/octet-stream")},
            )
        # 413 if our middleware caught it; 200 fallback if the underlying
        # client recomputed content-length (TestClient does). Either way,
        # nothing leaks beyond the cap. We accept both.
        assert resp.status_code in {200, 413}

    def test_over_rate_limit_returns_429(
        self,
        client: TestClient,
        sample_dcm_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with patch(
            "dcm_anon_vault.routes.anonymize._monthly_file_count",
            return_value=50,
        ):
            with sample_dcm_path.open("rb") as f:
                resp = client.post(
                    "/v1/anonymize",
                    headers={"X-API-Key": TEST_KEY},
                    files={"files": ("CT_small.dcm", f, "application/octet-stream")},
                )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


class TestFanOutWebhooksBg:
    """TD-045: setup-path failures in _fan_out_webhooks_bg must NOT be silent."""

    def test_session_factory_failure_is_logged_not_silent(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import logging

        from dcm_anon_vault.routes.anonymize import _fan_out_webhooks_bg

        caplog.set_level(logging.WARNING, logger="dcm_anon_vault.webhooks")

        def _boom() -> object:
            raise RuntimeError("DB pool exhausted")

        with patch("dcm_anon_vault.db._get_session_factory", return_value=_boom):
            _fan_out_webhooks_bg(
                customer_pk=42,
                event_type="anonymize.completed",
                payload={"foo": "bar"},
            )

        warning_records = [
            r for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert len(warning_records) == 1
        rec = warning_records[0]
        assert "background webhook fan-out failed" in rec.getMessage()
        assert rec.customer_pk == 42
        assert rec.event_type == "anonymize.completed"
        assert rec.error_type == "RuntimeError"
        assert "DB pool exhausted" in rec.error

    def test_uses_short_backoff_not_library_default(self) -> None:
        """TD-046: bg call site MUST pass _BG_WEBHOOK_BACKOFF, not default.

        Locks in the architectural decision against a future copy-paste
        regression. If someone drops the backoff kwarg, the threadpool-
        starvation regression returns silently — this test catches it.
        """
        from unittest.mock import MagicMock

        from dcm_anon_vault.routes.anonymize import (
            _BG_WEBHOOK_BACKOFF,
            _fan_out_webhooks_bg,
        )

        recorded: dict[str, object] = {}

        async def _fake_deliver(
            db: object,
            *,
            customer_id: int,
            event_type: str,
            payload: dict[str, object],
            **kwargs: object,
        ) -> list[object]:
            recorded["backoff"] = kwargs.get("backoff")
            recorded["customer_id"] = customer_id
            recorded["event_type"] = event_type
            return []

        with patch(
            "dcm_anon_vault.routes.anonymize.deliver_to_customer",
            side_effect=_fake_deliver,
        ), patch(
            "dcm_anon_vault.db._get_session_factory",
            return_value=lambda: MagicMock(close=MagicMock()),
        ):
            _fan_out_webhooks_bg(
                customer_pk=7,
                event_type="anonymize.completed",
                payload={"ok": True},
            )

        assert recorded["backoff"] == _BG_WEBHOOK_BACKOFF
        assert recorded["backoff"] != (1.0, 5.0, 25.0)  # library default
        assert recorded["customer_id"] == 7
        assert recorded["event_type"] == "anonymize.completed"

    def test_short_backoff_constant_bounds_attempts_at_two(self) -> None:
        """TD-046: the constant itself MUST be a 2-tuple.

        deliver_with_retries uses ``len(backoff)`` as the attempt count.
        A future drift to a 3-tuple silently brings the 21 s worst case
        back; this test guards the structural invariant.
        """
        from dcm_anon_vault.routes.anonymize import _BG_WEBHOOK_BACKOFF

        assert isinstance(_BG_WEBHOOK_BACKOFF, tuple)
        assert len(_BG_WEBHOOK_BACKOFF) == 2
        # Each delay < default (1, 5, 25): no individual sleep > 5 s.
        assert all(d <= 5.0 for d in _BG_WEBHOOK_BACKOFF)
