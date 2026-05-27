"""Tests for the GDPR Art 17 retention sweep."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy.orm
from fastapi.testclient import TestClient

from dcm_anon_vault.audit_chain import finalize_event_id, stamp_event
from dcm_anon_vault.models import AnonymizationEvent, Customer, WebhookDeadletter
from dcm_anon_vault.retention import sweep_all, sweep_customer
from tests.conftest import TEST_CUSTOMER_ID, TEST_KEY


def _make_customer(
    db: sqlalchemy.orm.Session, retention_days: int = 30
) -> Customer:
    cust = Customer(
        api_key_hash="r" * 64,
        customer_id_string="retention-tenant",
        tier="free",
        retention_days=retention_days,
    )
    db.add(cust)
    db.commit()
    db.refresh(cust)
    return cust


def _add_event(
    db: sqlalchemy.orm.Session, customer_id: int, *, created_at: datetime
) -> None:
    event = AnonymizationEvent(
        customer_id=customer_id,
        file_count=1,
        audit_sha256="d" * 64,
        created_at=created_at,
    )
    stamp_event(db, event)
    db.add(event)
    db.flush()
    finalize_event_id(db, event)
    db.commit()


def test_sweep_deletes_old_events(db_session: sqlalchemy.orm.Session) -> None:
    cust = _make_customer(db_session, retention_days=30)
    now = datetime.now(timezone.utc)
    _add_event(db_session, cust.id, created_at=now - timedelta(days=60))
    _add_event(db_session, cust.id, created_at=now - timedelta(days=10))

    report = sweep_customer(db_session, cust, now=now)
    assert report.events_deleted == 1
    remaining = db_session.query(AnonymizationEvent).count()
    assert remaining == 1


def test_sweep_respects_per_tenant_retention(
    db_session: sqlalchemy.orm.Session,
) -> None:
    cust_short = Customer(
        api_key_hash="s" * 64, customer_id_string="short", tier="free", retention_days=7
    )
    cust_long = Customer(
        api_key_hash="l" * 64, customer_id_string="long", tier="pro", retention_days=90
    )
    db_session.add_all([cust_short, cust_long])
    db_session.commit()
    db_session.refresh(cust_short)
    db_session.refresh(cust_long)

    now = datetime.now(timezone.utc)
    # 14 days old: short keeps, long keeps; 14 < 90 but > 7.
    _add_event(db_session, cust_short.id, created_at=now - timedelta(days=14))
    _add_event(db_session, cust_long.id, created_at=now - timedelta(days=14))

    reports = sweep_all(db_session, now=now)
    by_id = {r.customer_id: r for r in reports}
    assert by_id[cust_short.id].events_deleted == 1
    assert by_id[cust_long.id].events_deleted == 0


def test_sweep_deletes_old_deadletter(db_session: sqlalchemy.orm.Session) -> None:
    cust = _make_customer(db_session, retention_days=30)
    now = datetime.now(timezone.utc)
    old = WebhookDeadletter(
        customer_id=cust.id,
        url="https://x",
        event_type="anonymize.completed",
        payload="{}",
        attempts=3,
        created_at=now - timedelta(days=60),
    )
    fresh = WebhookDeadletter(
        customer_id=cust.id,
        url="https://x",
        event_type="anonymize.completed",
        payload="{}",
        attempts=3,
        created_at=now - timedelta(days=5),
    )
    db_session.add_all([old, fresh])
    db_session.commit()
    report = sweep_customer(db_session, cust, now=now)
    assert report.deadletter_deleted == 1


class TestRetentionEndpoint:
    def test_admin_required(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DCM_ADMIN_KEYS", raising=False)
        resp = client.post(
            "/v1/admin/retention/sweep", headers={"X-API-Key": TEST_KEY}
        )
        assert resp.status_code == 403

    def test_admin_ok(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DCM_ADMIN_KEYS", TEST_CUSTOMER_ID)
        resp = client.post(
            "/v1/admin/retention/sweep", headers={"X-API-Key": TEST_KEY}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "swept" in body
        assert "rows" in body
