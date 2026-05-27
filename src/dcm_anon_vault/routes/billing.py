"""Stripe billing routes.

POST /v1/billing/checkout-session — Stripe Checkout for tier upgrade.
POST /v1/billing/portal-session   — Stripe Customer Portal for self-service cancel/update.
POST /v1/billing/webhook          — handle Stripe webhook events.

Webhook signature verification is MANDATORY. The service refuses to
process unsigned events. Idempotency is enforced via the
``webhook_events`` table.

Handled webhook events: checkout.session.completed,
customer.subscription.deleted, customer.subscription.updated.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dcm_anon_vault.auth import require_api_key_hash, require_customer
from dcm_anon_vault.db import get_db
from dcm_anon_vault.models import Customer, WebhookEvent

LOG = logging.getLogger("dcm_anon_vault.billing")

router = APIRouter()

_STRIPE_NOT_CONFIGURED = (
    "Stripe is not configured on this instance. "
    "Set STRIPE_API_KEY, STRIPE_PRICE_ID and STRIPE_WEBHOOK_SECRET."
)
_PLACEHOLDER_SECRET = "whsec_REPLACE_ME"
_MAX_WEBHOOK_PAYLOAD = 1 * 1024 * 1024  # 1 MB


def _stripe_key() -> str | None:
    # Accept legacy STRIPE_TEST_KEY for back-compat, prefer STRIPE_API_KEY.
    return (
        os.environ.get("STRIPE_API_KEY")
        or os.environ.get("STRIPE_TEST_KEY")
        or None
    )


def _stripe_price_id(plan: str = "monthly") -> str | None:
    if plan == "annual":
        return os.environ.get("STRIPE_PRICE_ID_ANNUAL") or None
    return os.environ.get("STRIPE_PRICE_ID") or None


def _stripe_webhook_secret() -> str | None:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET") or None
    if secret == _PLACEHOLDER_SECRET:
        return None
    return secret


def _trial_days() -> int | None:
    raw = os.environ.get("STRIPE_TRIAL_DAYS", "")
    try:
        days = int(raw)
        return days if 0 < days <= 365 else None
    except ValueError:
        return None


class CheckoutRequest(BaseModel):
    success_url: str
    cancel_url: str
    plan: str = "monthly"  # "monthly" or "annual"
    customer_email: str | None = None


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class PortalSessionRequest(BaseModel):
    return_url: str


class PortalSessionResponse(BaseModel):
    portal_url: str


@router.post("/v1/billing/checkout-session", response_model=CheckoutResponse)
def create_checkout_session(
    body: CheckoutRequest,
    customer_id: str = Depends(require_customer),
    api_key_hash: str = Depends(require_api_key_hash),
    db: Session = Depends(get_db),
) -> CheckoutResponse:
    """Create a Stripe Checkout session for a Pro/Annual upgrade."""
    key = _stripe_key()
    price_id = _stripe_price_id(body.plan)
    if not key or not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_STRIPE_NOT_CONFIGURED
        )

    subscription_data: dict[str, Any] = {}
    trial_days = _trial_days()
    if trial_days is not None:
        subscription_data["trial_period_days"] = trial_days

    try:
        import stripe as stripe_lib

        stripe_lib.api_key = key
        kwargs: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": body.success_url,
            "cancel_url": body.cancel_url,
            "metadata": {"customer_id": customer_id, "api_key_hash": api_key_hash},
            "allow_promotion_codes": True,
            "billing_address_collection": "required",
            "tax_id_collection": {"enabled": True},
            "automatic_tax": {"enabled": True},
            "customer_creation": "always",
        }
        if subscription_data:
            kwargs["subscription_data"] = subscription_data
        if body.customer_email:
            kwargs["customer_email"] = body.customer_email
        session = stripe_lib.checkout.Session.create(**kwargs)
        return CheckoutResponse(
            checkout_url=str(session.url or ""),
            session_id=str(session.id),
        )
    except HTTPException:
        raise
    except Exception as exc:
        LOG.exception("Stripe checkout session creation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Stripe error: {exc}"
        ) from exc


@router.post("/v1/billing/portal-session", response_model=PortalSessionResponse)
def create_portal_session(
    body: PortalSessionRequest,
    customer_id: str = Depends(require_customer),
    api_key_hash: str = Depends(require_api_key_hash),
    db: Session = Depends(get_db),
) -> PortalSessionResponse:
    """Create a Stripe Billing Portal session for self-service cancel / update.

    Required by EU consumer-protection law: a customer who subscribed via
    Stripe Checkout must have a self-serve cancellation path. This endpoint
    issues a short-lived URL to the Stripe-hosted Customer Portal where the
    end customer can update payment methods, change plan, view invoices,
    and cancel. Cancellation is reflected in the app via the
    ``customer.subscription.deleted`` webhook handler.
    """
    key = _stripe_key()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_STRIPE_NOT_CONFIGURED
        )

    stmt = select(Customer).where(Customer.api_key_hash == api_key_hash)
    customer = db.execute(stmt).scalar_one_or_none()
    if customer is None or not customer.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No Stripe customer is on file for this API key. "
                "Complete a checkout first via POST /v1/billing/checkout-session."
            ),
        )

    try:
        import stripe as stripe_lib

        stripe_lib.api_key = key
        session = stripe_lib.billing_portal.Session.create(
            customer=customer.stripe_customer_id,
            return_url=body.return_url,
        )
        return PortalSessionResponse(portal_url=str(session.url or ""))
    except HTTPException:
        raise
    except Exception as exc:
        LOG.exception("Stripe portal session creation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Stripe error: {exc}"
        ) from exc


@router.post("/v1/billing/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request, db: Session = Depends(get_db)
) -> dict[str, str]:
    """Handle Stripe webhook events. Signature is mandatory."""
    key = _stripe_key()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_STRIPE_NOT_CONFIGURED
        )

    webhook_secret = _stripe_webhook_secret()
    if not webhook_secret:
        # Refuse to process anything unsigned — never trust unsigned webhooks.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "STRIPE_WEBHOOK_SECRET is not configured. Refusing to process "
                "unsigned webhooks. Set the secret from your Stripe dashboard."
            ),
        )

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_WEBHOOK_PAYLOAD:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Webhook payload too large.",
                )
        except ValueError:
            pass

    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header.",
        )

    try:
        import stripe as stripe_lib

        stripe_lib.api_key = key
        event = stripe_lib.Webhook.construct_event(  # type: ignore[no-untyped-call]
            payload, sig_header, webhook_secret
        )
    except Exception as exc:
        LOG.warning("Stripe webhook signature verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid signature: {exc}",
        ) from exc

    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")

    if event_id and _is_duplicate_event(db, event_id):
        return {"status": "duplicate"}

    if event_type == "checkout.session.completed":
        session_obj = event["data"]["object"]
        metadata = session_obj.get("metadata", {}) or {}
        api_key_hash = metadata.get("api_key_hash")
        customer_id_str = metadata.get("customer_id")
        stripe_customer = session_obj.get("customer")
        if api_key_hash:
            _flip_tier_by_hash(db, api_key_hash, "pro", stripe_customer)
        elif customer_id_str:
            _flip_tier_by_string(db, customer_id_str, "pro", stripe_customer)
        else:
            LOG.warning("checkout.session.completed without customer metadata")

    elif event_type == "customer.subscription.deleted":
        # Subscription cancelled (end of period or immediate). Drop the
        # customer back to the free tier so that the in-app quota matches
        # the billing reality. Required by EU consumer-protection law: a
        # cancellation in Stripe must be reflected in the app without
        # operator intervention.
        sub_obj = event["data"]["object"]
        stripe_customer = sub_obj.get("customer")
        if stripe_customer:
            _flip_tier_by_stripe_customer(db, str(stripe_customer), "free")
        else:
            LOG.warning("customer.subscription.deleted without customer id")

    elif event_type == "customer.subscription.updated":
        # Subscription state change. The most common cases:
        #   - status flips to "canceled" or "incomplete_expired" → free.
        #   - status flips back to "active" or "trialing" → pro.
        # We do not infer tier from price-id changes here; the
        # checkout.session.completed handler is responsible for the initial
        # tier set, and downgrades are handled by subscription.deleted.
        sub_obj = event["data"]["object"]
        stripe_customer = sub_obj.get("customer")
        sub_status = str(sub_obj.get("status") or "")
        if stripe_customer:
            if sub_status in ("canceled", "incomplete_expired", "unpaid"):
                _flip_tier_by_stripe_customer(db, str(stripe_customer), "free")
            elif sub_status in ("active", "trialing"):
                # Idempotent: tier already set by checkout.session.completed.
                # We re-affirm in case the row was created out of order.
                _flip_tier_by_stripe_customer(db, str(stripe_customer), "pro")
            else:
                LOG.info(
                    "customer.subscription.updated status=%s (no tier change)",
                    sub_status,
                )
        else:
            LOG.warning("customer.subscription.updated without customer id")

    if event_id:
        _record_event(db, event_id, event_type)

    return {"status": "received"}


def _is_duplicate_event(db: Session, event_id: str) -> bool:
    stmt = select(WebhookEvent).where(WebhookEvent.stripe_event_id == event_id)
    return db.execute(stmt).scalar_one_or_none() is not None


def _record_event(db: Session, event_id: str, event_type: str) -> None:
    record = WebhookEvent(stripe_event_id=event_id, event_type=event_type)
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # concurrent insert raced us, fine


def _flip_tier_by_hash(
    db: Session, api_key_hash: str, new_tier: str, stripe_customer: str | None
) -> None:
    stmt = select(Customer).where(Customer.api_key_hash == api_key_hash)
    customer = db.execute(stmt).scalar_one_or_none()
    if customer is None:
        LOG.warning("Webhook: customer not found for api_key_hash=%s", api_key_hash[:8])
        return
    customer.tier = new_tier
    if stripe_customer:
        customer.stripe_customer_id = str(stripe_customer)
    db.commit()
    LOG.info("Tier flipped to %s for api_key_hash=%s...", new_tier, api_key_hash[:8])


def _flip_tier_by_string(
    db: Session, customer_id_string: str, new_tier: str, stripe_customer: str | None
) -> None:
    stmt = select(Customer).where(Customer.customer_id_string == customer_id_string)
    rows = db.execute(stmt).scalars().all()
    for customer in rows:
        customer.tier = new_tier
        if stripe_customer:
            customer.stripe_customer_id = str(stripe_customer)
    if rows:
        db.commit()
        LOG.info("Tier flipped to %s for customer_id=%s (%d rows)", new_tier, customer_id_string, len(rows))
    else:
        LOG.warning("Webhook: no customer rows for customer_id=%s", customer_id_string)


def _flip_tier_by_stripe_customer(
    db: Session, stripe_customer_id: str, new_tier: str
) -> None:
    """Flip tier for all Customer rows linked to a Stripe customer id.

    Used by subscription.deleted / subscription.updated handlers, which
    only carry the Stripe customer id (no metadata). The Stripe customer
    id was persisted on the row by the checkout.session.completed
    handler.
    """
    stmt = select(Customer).where(Customer.stripe_customer_id == stripe_customer_id)
    rows = db.execute(stmt).scalars().all()
    if not rows:
        LOG.warning(
            "Webhook: no customer rows for stripe_customer_id=%s", stripe_customer_id
        )
        return
    for customer in rows:
        customer.tier = new_tier
    db.commit()
    LOG.info(
        "Tier flipped to %s for stripe_customer_id=%s (%d rows)",
        new_tier,
        stripe_customer_id,
        len(rows),
    )
