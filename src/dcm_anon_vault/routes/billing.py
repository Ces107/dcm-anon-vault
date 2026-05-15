"""Stripe billing routes.

POST /v1/billing/checkout-session — create a Stripe Checkout session for tier upgrade.
POST /v1/billing/webhook — handle Stripe webhook events (checkout.session.completed).

Both routes are stubbed: if STRIPE_TEST_KEY is not set, they return 503 with an
explanation so the MVP can be tested without real Stripe credentials.
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from dcm_anon_vault.auth import require_customer
from dcm_anon_vault.db import get_db
from dcm_anon_vault.models import Customer

LOG = logging.getLogger("dcm_anon_vault.billing")

router = APIRouter()

_STRIPE_NOT_CONFIGURED = (
    "Stripe is not configured on this instance. "
    "Set STRIPE_TEST_KEY and STRIPE_PRICE_ID environment variables."
)


def _stripe_key() -> str | None:
    return os.environ.get("STRIPE_TEST_KEY") or None


def _stripe_price_id() -> str | None:
    return os.environ.get("STRIPE_PRICE_ID") or None


def _stripe_webhook_secret() -> str | None:
    return os.environ.get("STRIPE_WEBHOOK_SECRET") or None


class CheckoutRequest(BaseModel):
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


@router.post("/v1/billing/checkout-session", response_model=CheckoutResponse)
def create_checkout_session(
    body: CheckoutRequest,
    customer_id: str = Depends(require_customer),
    db: Session = Depends(get_db),
) -> CheckoutResponse:
    """Create a Stripe Checkout session for the Pro tier upgrade."""
    key = _stripe_key()
    price_id = _stripe_price_id()
    if not key or not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_STRIPE_NOT_CONFIGURED,
        )

    try:
        import stripe as stripe_lib

        stripe_lib.api_key = key
        session = stripe_lib.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={"customer_id": customer_id},
        )
        return CheckoutResponse(
            checkout_url=str(session.url or ""),
            session_id=str(session.id),
        )
    except Exception as exc:
        LOG.exception("Stripe checkout session creation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Stripe error: {exc}",
        ) from exc


@router.post("/v1/billing/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    """Handle Stripe webhook events.

    On checkout.session.completed, flips the customer's tier to 'pro' in the DB.
    Returns 503 if STRIPE_TEST_KEY is unset (Stripe not configured).
    """
    key = _stripe_key()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_STRIPE_NOT_CONFIGURED,
        )

    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    webhook_secret = _stripe_webhook_secret()

    try:
        import stripe as stripe_lib

        stripe_lib.api_key = key

        if webhook_secret:
            event = stripe_lib.Webhook.construct_event(  # type: ignore[no-untyped-call]
                payload, sig_header, webhook_secret
            )
        else:
            # No signing secret: parse JSON directly (dev/test only)
            LOG.warning(
                "STRIPE_WEBHOOK_SECRET not set — skipping signature verification. "
                "Set it in production."
            )
            event = stripe_lib.Event.construct_from(
                json.loads(payload), stripe_lib.api_key
            )
    except Exception as exc:
        LOG.warning("Stripe webhook parse error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Webhook parse error: {exc}",
        ) from exc

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        metadata = session_obj.get("metadata", {})
        customer_id_str = metadata.get("customer_id")
        if customer_id_str:
            _flip_tier(db, customer_id_str, "pro")

    return {"status": "received"}


def _flip_tier(db: Session, customer_id_str: str, new_tier: str) -> None:
    """Upgrade the customer's tier in the database."""
    from sqlalchemy import select

    stmt = select(Customer).where(Customer.api_key_hash == customer_id_str)
    customer = db.execute(stmt).scalar_one_or_none()
    if customer is not None:
        customer.tier = new_tier
        db.commit()
        LOG.info("Flipped customer %s to tier=%s", customer_id_str, new_tier)
    else:
        LOG.warning("Webhook: customer not found for id=%s", customer_id_str)
