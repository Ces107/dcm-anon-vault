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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_SUMMARY = AuditSummary(
    files_processed=1,
    files_failed=0,
    audit_sha256="a" * 64,
)


def _make_fake_zip() -> bytes:
    """Return a minimal ZIP bytes object (in-memory)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("anon.dcm", b"FAKE_DCM_DATA")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnonymizeRoute:
    def test_valid_key_and_dicom_returns_zip(
        self, client: TestClient, sample_dcm_path: Path
    ) -> None:
        """Happy path: valid API key + 1 DICOM file → 200 + ZIP."""
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
        # Validate the ZIP can be parsed
        buf = io.BytesIO(resp.content)
        assert zipfile.is_zipfile(buf)

    def test_missing_key_returns_401(self, client: TestClient) -> None:
        """No X-API-Key header → 401."""
        resp = client.post("/v1/anonymize")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client: TestClient) -> None:
        """Invalid API key → 401."""
        resp = client.post(
            "/v1/anonymize",
            headers={"X-API-Key": "completely-wrong-key"},
        )
        assert resp.status_code == 401

    def test_over_rate_limit_returns_429(
        self,
        client: TestClient,
        sample_dcm_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Free-tier customer over 50 files/month → 429."""
        # Patch monthly count to return a value above the limit
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
