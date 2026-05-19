"""Tests for GET /v1/usage."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dcm_anon_vault.core import AuditSummary
from tests.conftest import TEST_KEY


def test_usage_initial_state(client: TestClient) -> None:
    resp = client.get("/v1/usage", headers={"X-API-Key": TEST_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["files_used_mtd"] == 0
    assert data["quota"] == 50
    assert "reset_at" in data


def test_usage_increments_after_anonymize(
    client: TestClient, sample_dcm_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = AuditSummary(
        files_processed=3, files_failed=0, files_rejected_burned_in=0, audit_sha256="b" * 64
    )
    fake_zip = b"PK\x05\x06" + b"\x00" * 18  # empty zip EOCD
    with patch(
        "dcm_anon_vault.routes.anonymize.anonymize_files_to_zip",
        return_value=(fake_zip, summary),
    ):
        with sample_dcm_path.open("rb") as f:
            r = client.post(
                "/v1/anonymize",
                headers={"X-API-Key": TEST_KEY},
                files={"files": ("CT_small.dcm", f, "application/octet-stream")},
            )
        assert r.status_code == 200

    resp = client.get("/v1/usage", headers={"X-API-Key": TEST_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["files_used_mtd"] == 3


def test_usage_requires_api_key(client: TestClient) -> None:
    resp = client.get("/v1/usage")
    assert resp.status_code == 401
