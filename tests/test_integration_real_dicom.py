"""End-to-end test using the real dcm-anonymizer engine.

Pushes a real pydicom CT_small.dcm through `/v1/anonymize` (no mocks of
the engine), unzips the response, re-loads the output, and asserts the
patient-identifying tags are actually scrubbed. This is the test that
anchors the "engine works" claim — `dcm-anon-vault` cannot be marketed
without it passing.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_KEY

pydicom = pytest.importorskip("pydicom")
# dcm-anonymizer is a real runtime dep but the test env may not have it
# installed when running this file in isolation; skip cleanly if so.
dcm_anon = pytest.importorskip("dcm_anon")


def test_real_engine_strips_patient_name(
    client: TestClient, sample_dcm_path: Path
) -> None:
    with sample_dcm_path.open("rb") as f:
        resp = client.post(
            "/v1/anonymize",
            headers={"X-API-Key": TEST_KEY},
            files={"files": ("CT_small.dcm", f, "application/octet-stream")},
        )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    assert int(resp.headers["x-files-processed"]) >= 1
    assert resp.headers["x-files-rejected-burnedin"] == "0"

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".dcm")]
        assert names, f"zip contents: {zf.namelist()}"
        with zf.open(names[0]) as out_dcm:
            out_bytes = out_dcm.read()

    ds_out = pydicom.dcmread(io.BytesIO(out_bytes))
    ds_in = pydicom.dcmread(sample_dcm_path)

    # PatientName MUST be neutralised (placeholder, empty, or removed).
    in_name = str(getattr(ds_in, "PatientName", ""))
    out_name = str(getattr(ds_out, "PatientName", ""))
    assert in_name != out_name or in_name == "", (
        f"PatientName not scrubbed: in={in_name!r} out={out_name!r}"
    )

    # SOPInstanceUID MUST be re-mapped.
    if hasattr(ds_in, "SOPInstanceUID") and hasattr(ds_out, "SOPInstanceUID"):
        assert ds_in.SOPInstanceUID != ds_out.SOPInstanceUID

    # Re-running same input → same output UIDs (deterministic per customer).
    with sample_dcm_path.open("rb") as f:
        resp2 = client.post(
            "/v1/anonymize",
            headers={"X-API-Key": TEST_KEY},
            files={"files": ("CT_small.dcm", f, "application/octet-stream")},
        )
    assert resp2.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp2.content)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".dcm")]
        with zf.open(names[0]) as out_dcm:
            out2_bytes = out_dcm.read()
    ds_out2 = pydicom.dcmread(io.BytesIO(out2_bytes))
    if hasattr(ds_out, "SOPInstanceUID"):
        assert ds_out.SOPInstanceUID == ds_out2.SOPInstanceUID, (
            "UID mapping is not deterministic — longitudinal cohort linkage broken"
        )


def test_burned_in_phi_is_rejected(
    client: TestClient, sample_dcm_path: Path, tmp_path: Path
) -> None:
    """File with BurnedInAnnotation=YES must return 422 — we don't ship a
    Clean Pixel Data Option."""
    ds = pydicom.dcmread(sample_dcm_path)
    ds.BurnedInAnnotation = "YES"
    burned_path = tmp_path / "burned.dcm"
    ds.save_as(burned_path, enforce_file_format=True)

    with burned_path.open("rb") as f:
        resp = client.post(
            "/v1/anonymize",
            headers={"X-API-Key": TEST_KEY},
            files={"files": ("burned.dcm", f, "application/octet-stream")},
        )
    assert resp.status_code == 422
