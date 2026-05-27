"""Shared pytest fixtures for dcm-anon-vault tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy
import sqlalchemy.orm
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dcm_anon_vault.app import app
from dcm_anon_vault.db import get_db
from dcm_anon_vault.models import Base
from dcm_anon_vault.rate_limit import get_limiter, set_session_factory_for_test

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_KEY = "test-api-key-abc123"
TEST_CUSTOMER_ID = "test_customer"


# ---------------------------------------------------------------------------
# In-memory SQLite database fixtures
#
# StaticPool: all connections share one in-memory DB so tables created by
# create_all() are visible to every session opened during the test.
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine() -> Generator[sqlalchemy.engine.Engine, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(
    db_engine: sqlalchemy.engine.Engine,
) -> Generator[sqlalchemy.orm.Session, None, None]:
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Test API key environment variable
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_api_keys_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set DCM_API_KEYS so the middleware recognises the test key."""
    monkeypatch.setenv("DCM_API_KEYS", f"{TEST_CUSTOMER_ID}:{TEST_KEY}")
    # Generous per-tier rate limit for tests; specific tests override.
    monkeypatch.setenv("DCM_RATE_LIMIT_FREE", "10000")
    monkeypatch.setenv("DCM_RATE_LIMIT_PRO", "10000")
    # Quiet the JSON access log in tests; specific tests can re-enable.
    monkeypatch.setenv("DCM_DISABLE_JSON_LOG", "1")


@pytest.fixture(autouse=True)
def _reset_limiter() -> Generator[None, None, None]:
    """Clear the in-process rate-limit windows between tests."""
    get_limiter().reset()
    yield
    get_limiter().reset()


# ---------------------------------------------------------------------------
# TestClient with overridden DB dependency
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(db_engine: sqlalchemy.engine.Engine) -> Generator[TestClient, None, None]:
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db() -> Generator[sqlalchemy.orm.Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    set_session_factory_for_test(factory)

    # Patch init_db so the lifespan startup doesn't create tables on the
    # module-level engine (tables are already created on the test engine above).
    with patch("dcm_anon_vault.app.init_db"):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()
    set_session_factory_for_test(None)


# ---------------------------------------------------------------------------
# Sample DICOM file from pydicom test data
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_dcm_path() -> Path:
    """Return a path to a real DICOM test file (from pydicom package data)."""
    try:
        import pydicom.data

        path = pydicom.data.get_testdata_file("CT_small.dcm")
        if path is not None:
            return Path(str(path))
    except Exception:
        pass

    # Fallback: look for a sibling sample fixture (optional, repo-local).
    fallback = Path(__file__).resolve().parent / "fixtures" / "CT_small.dcm"
    if fallback.exists():
        return fallback

    pytest.skip("No sample DICOM file available")
