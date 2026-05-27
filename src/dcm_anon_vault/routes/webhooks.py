"""Customer-facing webhook management + admin deadletter inspection."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dcm_anon_vault.auth import require_admin, require_api_key_hash
from dcm_anon_vault.db import get_db
from dcm_anon_vault.models import Customer, OutgoingWebhook, WebhookDeadletter

router = APIRouter()


class WebhookRegistration(BaseModel):
    url: str = Field(..., min_length=8, max_length=512)
    secret: str | None = Field(default=None, max_length=128)


class WebhookResponse(BaseModel):
    id: int
    url: str
    active: bool
    created_at: datetime


class DeadletterRow(BaseModel):
    id: int
    customer_id: int
    url: str
    event_type: str
    last_status: int | None
    last_error: str | None
    attempts: int
    created_at: datetime


def _resolve_customer(db: Session, api_key_hash: str) -> Customer:
    stmt = select(Customer).where(Customer.api_key_hash == api_key_hash)
    cust = db.execute(stmt).scalar_one_or_none()
    if cust is None:
        # Lazy-create so customers can register a webhook before any /v1/anonymize
        # call (e.g. integration test pre-wiring).
        cust = Customer(
            api_key_hash=api_key_hash,
            customer_id_string=api_key_hash[:16],
            tier="free",
        )
        db.add(cust)
        try:
            db.commit()
            db.refresh(cust)
        except IntegrityError:
            db.rollback()
            cust = db.execute(stmt).scalar_one()
    return cust


@router.post(
    "/v1/webhooks", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED
)
def register_webhook(
    body: WebhookRegistration,
    api_key_hash: str = Depends(require_api_key_hash),
    db: Session = Depends(get_db),
) -> WebhookResponse:
    """Register a webhook URL for ``anonymize.completed`` notifications."""
    if not (body.url.startswith("http://") or body.url.startswith("https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="url must be http:// or https://",
        )
    customer = _resolve_customer(db, api_key_hash)
    hook = OutgoingWebhook(
        customer_id=customer.id, url=body.url, secret=body.secret, active=1
    )
    db.add(hook)
    try:
        db.commit()
        db.refresh(hook)
    except IntegrityError:
        db.rollback()
        # Already registered — fetch and return.
        existing = db.execute(
            select(OutgoingWebhook).where(
                OutgoingWebhook.customer_id == customer.id,
                OutgoingWebhook.url == body.url,
            )
        ).scalar_one()
        hook = existing
    return WebhookResponse(
        id=hook.id, url=hook.url, active=bool(hook.active), created_at=hook.created_at
    )


@router.get("/v1/webhooks", response_model=list[WebhookResponse])
def list_webhooks(
    api_key_hash: str = Depends(require_api_key_hash),
    db: Session = Depends(get_db),
) -> list[WebhookResponse]:
    """List the calling customer's registered webhook URLs."""
    customer = _resolve_customer(db, api_key_hash)
    rows = db.execute(
        select(OutgoingWebhook).where(OutgoingWebhook.customer_id == customer.id)
    ).scalars()
    return [
        WebhookResponse(
            id=r.id, url=r.url, active=bool(r.active), created_at=r.created_at
        )
        for r in rows
    ]


@router.get("/v1/webhooks/deadletter", response_model=list[DeadletterRow])
def list_deadletter(
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = 100,
) -> list[DeadletterRow]:
    """Admin view of failed webhook deliveries (deadletter queue)."""
    stmt = (
        select(WebhookDeadletter)
        .order_by(WebhookDeadletter.id.desc())
        .limit(min(max(limit, 1), 1000))
    )
    rows = db.execute(stmt).scalars()
    return [
        DeadletterRow(
            id=r.id,
            customer_id=r.customer_id,
            url=r.url,
            event_type=r.event_type,
            last_status=r.last_status,
            last_error=r.last_error,
            attempts=r.attempts,
            created_at=r.created_at,
        )
        for r in rows
    ]
