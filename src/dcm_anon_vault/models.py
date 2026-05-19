"""SQLAlchemy ORM models."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    """One row per API key.

    ``api_key_hash`` stores SHA-256 hex of the raw key, never the key itself.
    ``customer_id_string`` is the human-friendly identifier from the config
    ("acme", "research-lab-1", ...). Multiple keys can share a customer_id
    string (key rotation), so it is NOT unique.
    """

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("api_key_hash", name="uq_customers_api_key_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id_string: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """SHA-256 hex of the raw API key for safe storage."""
        return hashlib.sha256(raw_key.encode()).hexdigest()


class AnonymizationEvent(Base):
    """One row per successful ``POST /v1/anonymize`` call."""

    __tablename__ = "anonymization_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )


class WebhookEvent(Base):
    """Stripe webhook idempotency record (one row per event.id)."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stripe_event_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
