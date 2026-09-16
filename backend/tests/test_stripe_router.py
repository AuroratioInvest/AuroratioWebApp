from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from models import Subscription, User
from routers import stripe_router
from services import stripe_subscription_service as service
from subscriber_models import (
    AccessEntitlement,
    EntitlementAccessStatus,
    IntegrationEvent,
    IntegrationProcessingStatus,
    Subscriber,
    SubscriberSubscription,
    SubscriptionPlan,
)


NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
PERIOD_START = NOW - timedelta(days=1)
PERIOD_END = NOW + timedelta(days=30)


class FakeRequest:
    def __init__(self, payload: bytes, signature: str | None):
        self._payload = payload
        self.headers = {}
        if signature is not None:
            self.headers["stripe-signature"] = signature

    async def body(self) -> bytes:
        return self._payload


def _signature(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    timestamp = timestamp or int(time.time())
    signed_payload = f"{timestamp}.{payload.decode()}".encode()
    digest = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _payload(event: dict) -> bytes:
    return json.dumps(event, separators=(",", ":"), sort_keys=True).encode()


def _plan(db_session, *, price_id: str = "price_router") -> SubscriptionPlan:
    plan = SubscriptionPlan(
        code="monthly-signals",
        display_name_en="AuroRatio Monthly Signals",
        display_name_fr="Signaux mensuels AuroRatio",
        stripe_price_id=price_id,
        billing_interval="month",
        is_active=True,
        is_configured=True,
    )
    db_session.add(plan)
    db_session.commit()
    return plan


def _subscription(
    *,
    subscription_id: str = "sub_router",
    customer_id: str = "cus_router",
    email: str = "subscriber@example.com",
    price_id: str = "price_router",
    status: str = "active",
) -> dict:
    return {
        "id": subscription_id,
        "object": "subscription",
        "customer": {
            "id": customer_id,
            "email": email,
            "address": {"country": "FR"},
        },
        "status": status,
        "current_period_start": int(PERIOD_START.timestamp()),
        "current_period_end": int(PERIOD_END.timestamp()),
        "cancel_at_period_end": False,
        "items": {"data": [{"price": {"id": price_id}}]},
        "metadata": {
            "subscription_model": "accountless_subscription",
            "checkout_flow": "public_signal_checkout",
            "plan_code": "monthly-signals",
            "preferred_language": "en",
        },
    }


def _event(
    *,
    event_id: str = "evt_router",
    event_type: str = "customer.subscription.created",
    data_object: dict | None = None,
) -> dict:
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "created": int(NOW.timestamp()),
        "livemode": False,
        "data": {"object": data_object if data_object is not None else _subscription()},
    }


def _deliver(monkeypatch, db_session, event: dict, *, subscription: dict | None = None):
    secret = "whsec_router_test"
    payload = _payload(event)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(stripe_router, "WEBHOOK_SECRET", secret)
    if subscription is not None:
        monkeypatch.setattr(
            service,
            "retrieve_stripe_subscription",
            lambda subscription_id: subscription,
        )
    return asyncio.run(
        stripe_router.stripe_webhook(
            FakeRequest(payload, _signature(payload, secret)),
            db_session,
        )
    )


def test_webhook_accepts_unsupported_event_with_valid_signature(monkeypatch, db_session):
    response = _deliver(
        monkeypatch,
        db_session,
        _event(event_id="evt_unsupported", event_type="customer.created"),
    )

    assert response == {"status": "ok"}
    assert db_session.query(IntegrationEvent).one().processing_status == (
        IntegrationProcessingStatus.ignored
    )


def test_webhook_rejects_invalid_signature(monkeypatch, db_session):
    payload = _payload(_event(event_id="evt_bad_sig"))
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_router_test")
    monkeypatch.setattr(stripe_router, "WEBHOOK_SECRET", "whsec_router_test")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            stripe_router.stripe_webhook(
                FakeRequest(payload, "t=1,v1=invalid"),
                db_session,
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid webhook signature"
    assert db_session.query(IntegrationEvent).count() == 0


def test_webhook_requires_configured_secret(monkeypatch, db_session):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(stripe_router, "WEBHOOK_SECRET", None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(stripe_router.stripe_webhook(FakeRequest(b"{}", None), db_session))

    assert exc_info.value.status_code == 500
    assert "webhook secret" in exc_info.value.detail.lower()


def test_checkout_completed_ingests_accountless_subscription(monkeypatch, db_session):
    _plan(db_session)
    checkout_object = {
        "id": "cs_router",
        "object": "checkout.session",
        "mode": "subscription",
        "customer": "cus_router",
        "customer_details": {"email": "subscriber@example.com"},
        "subscription": "sub_router",
        "metadata": {
            "subscription_model": "accountless_subscription",
            "checkout_flow": "public_signal_checkout",
            "plan_code": "monthly-signals",
        },
    }
    subscription = _subscription()

    response = _deliver(
        monkeypatch,
        db_session,
        _event(
            event_id="evt_checkout_completed",
            event_type="checkout.session.completed",
            data_object=checkout_object,
        ),
        subscription=subscription,
    )

    assert response == {"status": "ok"}
    subscriber = db_session.query(Subscriber).one()
    subscription_row = db_session.query(SubscriberSubscription).one()
    entitlement = db_session.query(AccessEntitlement).one()
    assert subscriber.stripe_customer_id == "cus_router"
    assert subscriber.normalized_email == "subscriber@example.com"
    assert subscription_row.stripe_subscription_id == "sub_router"
    assert entitlement.status == EntitlementAccessStatus.active
    assert db_session.query(User).count() == 0
    assert db_session.query(Subscription).count() == 0


def test_subscription_update_is_idempotent(monkeypatch, db_session):
    _plan(db_session)
    event = _event(event_id="evt_update")

    assert _deliver(monkeypatch, db_session, event, subscription=event["data"]["object"]) == {
        "status": "ok"
    }
    assert _deliver(monkeypatch, db_session, event, subscription=event["data"]["object"]) == {
        "status": "ok"
    }

    assert db_session.query(Subscriber).count() == 1
    assert db_session.query(SubscriberSubscription).count() == 1
    assert db_session.query(AccessEntitlement).count() == 1
    assert db_session.query(IntegrationEvent).count() == 1


def test_invoice_payment_succeeded_reconciles_subscription(monkeypatch, db_session):
    _plan(db_session)
    subscription = _subscription()
    invoice = {
        "id": "in_router",
        "object": "invoice",
        "customer": "cus_router",
        "subscription": "sub_router",
    }

    response = _deliver(
        monkeypatch,
        db_session,
        _event(
            event_id="evt_invoice_paid",
            event_type="invoice.payment_succeeded",
            data_object=invoice,
        ),
        subscription=subscription,
    )

    assert response == {"status": "ok"}
    assert db_session.query(SubscriberSubscription).one().stripe_subscription_id == "sub_router"


def test_missing_local_plan_is_retryable_500(monkeypatch, db_session):
    event = _event(event_id="evt_missing_plan")

    with pytest.raises(HTTPException) as exc_info:
        _deliver(monkeypatch, db_session, event, subscription=event["data"]["object"])

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Stripe event processing deferred"
    assert db_session.query(IntegrationEvent).one().processing_status == (
        IntegrationProcessingStatus.retryable_failure
    )


def test_permanently_invalid_event_returns_400(monkeypatch, db_session):
    _plan(db_session)
    invalid = _event(
        event_id="evt_invalid",
        event_type="checkout.session.completed",
        data_object={
            "id": "cs_invalid",
            "object": "checkout.session",
            "subscription": "sub_router",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        _deliver(monkeypatch, db_session, invalid, subscription=_subscription())

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid Stripe event"
    assert db_session.query(IntegrationEvent).one().processing_status == (
        IntegrationProcessingStatus.permanently_failed
    )


def test_stripe_router_exposes_only_webhook_route():
    paths = [route.path for route in stripe_router.router.routes]

    assert paths == ["/webhook"]
