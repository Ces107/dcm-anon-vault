"""Database engine and session management."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import sqlalchemy
import sqlalchemy.orm
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from dcm_anon_vault.models import Base

_DEFAULT_URL = "sqlite:///./vault.db"


def _db_url() -> str:
    return os.environ.get("DCM_DB_URL", _DEFAULT_URL)


def make_engine(url: str | None = None) -> sqlalchemy.engine.Engine:
    """Create a SQLAlchemy engine.

    On SQLite, enables ``WAL`` journal mode + ``NORMAL`` synchronous, which
    permits concurrent readers while a writer is active and gives ~10x
    throughput over default ``DELETE`` mode.
    """
    target = url or _db_url()
    kwargs: dict[str, Any] = {}
    if target.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(target, **kwargs)

    if target.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn: Any, _connection_record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def init_db(engine: sqlalchemy.engine.Engine | None = None) -> None:
    """Create all tables if they don't exist."""
    target = engine if engine is not None else _get_engine()
    Base.metadata.create_all(bind=target)


def db_alive(engine: sqlalchemy.engine.Engine | None = None) -> bool:
    """Return True if a trivial ``SELECT 1`` succeeds against the engine."""
    target = engine if engine is not None else _get_engine()
    try:
        with target.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


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
