"""Tests for the Prometheus /metrics endpoint."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from dcm_anon_vault.core import AuditSummary
from tests.conftest import TEST_KEY


def test_metrics_endpoint_open(client: TestClient) -> None:
    """No auth required for /metrics."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_metric_names_present_after_anonymize(client: TestClient) -> None:
    with patch(
        "dcm_anon_vault.routes.anonymize.anonymize_files_to_zip",
        return_value=(b"PK\x05\x06" + b"\x00" * 18, AuditSummary(2, 0, 0, "c" * 64)),
    ):
        r = client.post(
            "/v1/anonymize",
            headers={"X-API-Key": TEST_KEY},
            files={"files": ("y.dcm", b"DICOM-bytes-here", "application/octet-stream")},
        )
        assert r.status_code == 200

    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "anonymize_requests_total" in body
    assert "anonymize_bytes_processed_total" in body
    assert 'tenant="test_customer"' in body
    assert 'status="200"' in body
