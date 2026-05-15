"""Database engine and session management for dcm-anon-vault."""

from __future__ import annotations

import os
from collections.abc import Generator

import sqlalchemy
import sqlalchemy.orm
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from dcm_anon_vault.models import Base

_DEFAULT_URL = "sqlite:///./vault.db"


def _db_url() -> str:
    return os.environ.get("DCM_DB_URL", _DEFAULT_URL)


def make_engine(url: str | None = None) -> sqlalchemy.engine.Engine:
    """Create a SQLAlchemy engine.  SQLite gets check_same_thread disabled."""
    target = url or _db_url()
    kwargs: dict[str, object] = {}
    if target.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(target, **kwargs)


def init_db(engine: sqlalchemy.engine.Engine | None = None) -> None:
    """Create all tables if they don't exist."""
    target = engine if engine is not None else _get_engine()
    Base.metadata.create_all(bind=target)


# ---------------------------------------------------------------------------
# Lazy module-level engine + session factory
# ---------------------------------------------------------------------------

_engine: sqlalchemy.engine.Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _get_engine() -> sqlalchemy.engine.Engine:
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session, closes on exit."""
    factory = _get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
