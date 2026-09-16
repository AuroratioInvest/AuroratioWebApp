"""Stripe webhook entry point for the accountless subscription product."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from services.subscriber_fulfillment_service import process_due_fulfillments
from services.stripe_subscription_service import (
    IntegrationProcessingStatus,
    PermanentStripeEventError,
    process_verified_stripe_event,
)

logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

router = APIRouter()


def _webhook_secret() -> str:
    secret = WEBHOOK_SECRET or os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret or not secret.strip():
        raise HTTPException(
            status_code=500,
            detail="Stripe webhook secret is not configured",
        )
    return secret.strip()


async def _process_access_fulfillment_after_webhook() -> None:
    """Best-effort immediate delivery after Stripe grants access.

    Fulfillment remains durable in the database, so the external fulfillment
    worker can retry later if this background pass fails or the process exits.
    """
    try:
        await process_due_fulfillments(
            limit=1,
            now=datetime.now(timezone.utc),
        )
    except Exception:
        logger.exception("Automatic access fulfillment pass failed")


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY") or stripe.api_key

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            _webhook_secret(),
        )
    except ValueError:
        logger.exception("Invalid Stripe webhook payload")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        logger.exception("Invalid Stripe webhook signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = getattr(event, "type", None)
    if isinstance(event, dict):
        event_type = event.get("type")
    logger.info("Stripe webhook event received: %s", event_type)

    try:
        outcome = process_verified_stripe_event(
            db,
            event=event,
            payload=payload,
            now=datetime.now(timezone.utc),
        )
    except PermanentStripeEventError:
        db.rollback()
        logger.exception("Rejected Stripe event before ingestion")
        raise HTTPException(status_code=400, detail="Invalid Stripe event")
    except Exception:
        db.rollback()
        logger.exception("Stripe subscription-domain ingestion failed for %s", event_type)
        raise HTTPException(status_code=500, detail="Stripe event processing failed")

    if outcome.status == IntegrationProcessingStatus.permanently_failed:
        raise HTTPException(status_code=400, detail="Invalid Stripe event")

    if outcome.retryable:
        raise HTTPException(
            status_code=500,
            detail="Stripe event processing deferred",
        )

    # Stripe webhook processing only enqueues durable access work. Trigger one
    # immediate best-effort pass after the 200 response so new subscribers do
    # not wait for the periodic worker. The durable worker remains the fallback
    # for retries, restarts, and provider outages.
    if event_type in {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "invoice.paid",
        "invoice.payment_succeeded",
    } and background_tasks is not None:
        background_tasks.add_task(_process_access_fulfillment_after_webhook)

    return {"status": "ok"}
