"""Tests for the tamper-evident audit hash chain."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import sqlalchemy.orm
from fastapi.testclient import TestClient

from dcm_anon_vault.audit_chain import (
    GENESIS_HASH,
    finalize_event_id,
    latest_chain_head,
    stamp_event,
    verify_chain,
)
from dcm_anon_vault.core import AuditSummary
from dcm_anon_vault.models import AnonymizationEvent, Customer
from tests.conftest import TEST_CUSTOMER_ID, TEST_KEY


def _seed_customer(db: sqlalchemy.orm.Session) -> Customer:
    cust = Customer(
        api_key_hash="a" * 64, customer_id_string=TEST_CUSTOMER_ID, tier="free"
    )
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust


def _add_event(db: sqlalchemy.orm.Session, customer_id: int, *, file_count: int) -> int:
    event = AnonymizationEvent(
        customer_id=customer_id,
        file_count=file_count,
        audit_sha256="f" * 64,
        created_at=datetime.now(timezone.utc),
    )
    stamp_event(db, event)
    db.add(event)
    db.flush()
    finalize_event_id(db, event)
    db.commit()
    return event.id


def test_empty_chain_returns_none(db_session: sqlalchemy.orm.Session) -> None:
    assert verify_chain(db_session) is None
    assert latest_chain_head(db_session) == GENESIS_HASH


def test_single_event_chain_verifies(db_session: sqlalchemy.orm.Session) -> None:
    cust = _seed_customer(db_session)
    _add_event(db_session, cust.id, file_count=3)
    assert verify_chain(db_session) is None


def test_multi_event_chain_verifies(db_session: sqlalchemy.orm.Session) -> None:
    cust = _seed_customer(db_session)
    for i in range(5):
        _add_event(db_session, cust.id, file_count=i + 1)
    assert verify_chain(db_session) is None


def test_tampered_row_detected(db_session: sqlalchemy.orm.Session) -> None:
    cust = _seed_customer(db_session)
    ids = [_add_event(db_session, cust.id, file_count=i + 1) for i in range(3)]
    # Mutate row 2 retroactively (simulate attacker rewriting history).
    second = db_session.get(AnonymizationEvent, ids[1])
    assert second is not None
    second.file_count = 999
    db_session.commit()
    broken = verify_chain(db_session)
    assert broken == ids[1]


def test_tampered_prev_hash_detected(db_session: sqlalchemy.orm.Session) -> None:
    cust = _seed_customer(db_session)
    ids = [_add_event(db_session, cust.id, file_count=1) for _ in range(2)]
    second = db_session.get(AnonymizationEvent, ids[1])
    assert second is not None
    second.prev_hash = "0" * 64
    db_session.commit()
    broken = verify_chain(db_session)
    assert broken == ids[1]


class TestAuditVerifyEndpoint:
    def test_admin_required(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DCM_ADMIN_KEYS", raising=False)
        resp = client.get("/v1/audit/verify", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 403

    def test_admin_ok_on_empty_chain(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DCM_ADMIN_KEYS", TEST_CUSTOMER_ID)
        resp = client.get("/v1/audit/verify", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "first_broken_id": None}

    def test_admin_ok_after_real_request(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("DCM_ADMIN_KEYS", TEST_CUSTOMER_ID)
        # Drive a successful anonymize so an event is appended.
        with patch(
            "dcm_anon_vault.routes.anonymize.anonymize_files_to_zip",
            return_value=(
                b"PK\x05\x06" + b"\x00" * 18,
                AuditSummary(1, 0, 0, "b" * 64),
            ),
        ):
            r = client.post(
                "/v1/anonymize",
                headers={"X-API-Key": TEST_KEY},
                files={"files": ("x.dcm", b"DICOM-bytes", "application/octet-stream")},
            )
            assert r.status_code == 200
        resp = client.get("/v1/audit/verify", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# Avoid unused-import warning for tests that don't directly reference `os`.
_ = os
