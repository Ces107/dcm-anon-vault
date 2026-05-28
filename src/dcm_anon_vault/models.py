"""SQLAlchemy ORM models."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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

    ``rate_limit_per_minute`` and ``retention_days`` are per-tenant
    overrides; ``None`` means "use tier default".
    """

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("api_key_hash", name="uq_customers_api_key_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_id_string: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Per-tenant override; NULL falls back to tier default (free=30/min, pro=600/min).
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # GDPR Art 17 retention window for audit / event rows (default 30 days).
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    @staticmethod
    def hash_key(raw_key: str) -> str:
        """SHA-256 hex of the raw API key for safe storage."""
        return hashlib.sha256(raw_key.encode()).hexdigest()


class AnonymizationEvent(Base):
    """One row per successful ``POST /v1/anonymize`` call.

    ``prev_hash`` + ``row_hash`` form a tamper-evident hash chain
    (see :mod:`dcm_anon_vault.audit_chain`): each row commits to the
    canonical JSON of its predecessor; any retroactive edit detectable
    by walking the chain.
    """

    __tablename__ = "anonymization_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Hash chain columns: row_hash = sha256(canonical_json(this_row, prev_hash))
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="0" * 64)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
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


class OutgoingWebhook(Base):
    """Customer-registered webhook URL to receive anonymize.completed events.

    One row per (customer, url) pair. ``secret`` is used to sign payloads
    with HMAC-SHA256 (``X-Webhook-Signature`` header). NULL secret means
    unsigned delivery (not recommended, used for legacy clients only).
    """

    __tablename__ = "outgoing_webhooks"
    __table_args__ = (
        UniqueConstraint("customer_id", "url", name="uq_outgoing_webhooks_cust_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )


class WebhookDeadletter(Base):
    """Final-failure record for an outgoing webhook delivery.

    Populated after all configured retries are exhausted. The default
    backoff is 3 attempts (1 s / 5 s / 25 s); the BackgroundTask fan-out
    in ``routes/anonymize.py`` uses a shorter 2-attempt backoff (TD-046).
    Inspect via ``GET /v1/webhooks/deadletter``.
    """

    __tablename__ = "webhook_deadletter"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    last_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
