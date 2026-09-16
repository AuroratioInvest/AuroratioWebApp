import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import stripe
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import sessionmaker

from database import Base, configure_sqlite_foreign_keys
from models import User
from routers.public_billing import CheckoutSessionRequest
from services.public_billing_service import (
    ACCOUNTLESS_FLOW_MARKER,
    InvalidPublicBillingRequest,
    PortalDeliveryBatch,
    PortalTokenRejected,
    PublicBillingConfigurationError,
    PublicBillingProviderError,
    create_public_checkout_session,
    deliver_portal_access_batch,
    exchange_portal_access_token,
    ensure_public_monthly_plan_configured,
    hash_portal_token,
    request_portal_access,
)
from subscriber_models import (
    AccessEntitlement,
    AuditEvent,
    PortalAccessToken,
    PortalAccessTokenPurpose,
    PortalLinkIssuance,
    Subscriber,
    SubscriberBillingStatus,
    SubscriberSubscription,
    SubscriptionPlan,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def public_billing_environment(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_phase6")
    monkeypatch.setenv("STRIPE_MONTHLY_SIGNAL_PRICE_ID", "price_monthly_phase6")
    monkeypatch.setenv("MONTHLY_SIGNAL_PLAN_CODE", "monthly-signals")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.auroratio.test")
    monkeypatch.setenv("PORTAL_ACCESS_TOKEN_TTL_MINUTES", "15")
    monkeypatch.setenv("PORTAL_LINK_COOLDOWN_MINUTES", "5")
    monkeypatch.setenv("PORTAL_REQUEST_MIN_RESPONSE_MS", "0")
    monkeypatch.delenv("STRIPE_BILLING_PORTAL_CONFIGURATION_ID", raising=False)


def _plan(db, *, code="monthly-signals", price_id="price_monthly_phase6"):
    plan = SubscriptionPlan(
        code=code,
        display_name_en="Monthly signals",
        display_name_fr="Signaux mensuels",
        stripe_price_id=price_id,
        billing_interval="month",
        is_active=True,
        is_configured=True,
    )
    db.add(plan)
    db.commit()
    return plan


def _subscriber(db, *, customer_id="cus_phase6", email="billing@example.com"):
    subscriber = Subscriber(
        stripe_customer_id=customer_id,
        stripe_email=email,
        normalized_email=email.strip().lower(),
    )
    db.add(subscriber)
    db.commit()
    return subscriber


def _subscription(
    db,
    subscriber,
    plan,
    *,
    subscription_id="sub_phase6",
    billing_status=SubscriberBillingStatus.active,
    stripe_status="active",
    period_end=NOW + timedelta(days=30),
    cancel_at_period_end=False,
    created_at=NOW - timedelta(days=1),
):
    subscription = SubscriberSubscription(
        subscriber_id=subscriber.id,
        plan_id=plan.id,
        stripe_subscription_id=subscription_id,
        billing_status=billing_status,
        stripe_status=stripe_status,
        current_period_start=NOW - timedelta(days=1),
        current_period_end=period_end,
        cancel_at_period_end=cancel_at_period_end,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(subscription)
    db.commit()
    return subscription


def test_public_monthly_plan_bootstrap_creates_missing_local_config(db_session):
    assert db_session.query(SubscriptionPlan).count() == 0

    plan = ensure_public_monthly_plan_configured(db_session, now=NOW)

    assert plan is not None
    assert plan.code == "monthly-signals"
    assert plan.stripe_price_id == "price_monthly_phase6"
    assert plan.billing_interval == "month"
    assert plan.is_active is True
    assert plan.is_configured is True
    assert db_session.query(SubscriptionPlan).count() == 1

    again = ensure_public_monthly_plan_configured(
        db_session,
        now=NOW + timedelta(minutes=1),
    )
    assert again.id == plan.id
    assert db_session.query(SubscriptionPlan).count() == 1


def test_public_monthly_plan_bootstrap_does_not_rewrite_existing_plan(db_session):
    plan = SubscriptionPlan(
        code="monthly-signals",
        display_name_en="Manual plan",
        display_name_fr="Plan manuel",
        stripe_price_id="price_manual",
        billing_interval="month",
        is_active=False,
        is_configured=False,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(plan)
    db_session.commit()

    result = ensure_public_monthly_plan_configured(db_session, now=NOW)

    assert result.id == plan.id
    db_session.refresh(plan)
    assert plan.stripe_price_id == "price_manual"
    assert plan.is_active is False
    assert plan.is_configured is False


def test_public_monthly_plan_bootstrap_recovers_from_duplicate_insert_race(
    monkeypatch,
    db_session,
):
    real_commit = db_session.commit
    injected = {"done": False}

    def racing_commit():
        if not injected["done"]:
            injected["done"] = True
            db_session.expunge_all()
            other = SubscriptionPlan(
                code="monthly-signals",
                display_name_en="Concurrent plan",
                display_name_fr="Plan concurrent",
                stripe_price_id="price_monthly_phase6",
                billing_interval="month",
                is_active=True,
                is_configured=True,
                created_at=NOW,
                updated_at=NOW,
            )
            db_session.add(other)
            real_commit()
            raise IntegrityError("insert subscription_plans", {}, Exception("duplicate"))
        return real_commit()

    monkeypatch.setattr(db_session, "commit", racing_commit)

    plan = ensure_public_monthly_plan_configured(db_session, now=NOW)

    assert plan is not None
    assert plan.code == "monthly-signals"
    assert plan.stripe_price_id == "price_monthly_phase6"
    assert db_session.query(SubscriptionPlan).count() == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"stripe_price_id": "price_wrong"},
        {"is_active": False},
        {"archived_at": NOW},
        {"is_configured": False},
        {"billing_interval": "year"},
    ],
)
def test_public_monthly_plan_bootstrap_rejects_invalid_competing_race_row(
    monkeypatch,
    db_session,
    overrides,
):
    real_commit = db_session.commit
    injected = {"done": False}

    def racing_commit():
        if not injected["done"]:
            injected["done"] = True
            db_session.expunge_all()
            values = {
                "code": "monthly-signals",
                "display_name_en": "Invalid concurrent plan",
                "display_name_fr": "Plan concurrent invalide",
                "stripe_price_id": "price_monthly_phase6",
                "billing_interval": "month",
                "is_active": True,
                "is_configured": True,
                "created_at": NOW,
                "updated_at": NOW,
            }
            values.update(overrides)
            db_session.add(SubscriptionPlan(**values))
            real_commit()
            raise IntegrityError("insert subscription_plans", {}, Exception("duplicate"))
        return real_commit()

    monkeypatch.setattr(db_session, "commit", racing_commit)

    with pytest.raises(IntegrityError):
        ensure_public_monthly_plan_configured(db_session, now=NOW)

    plan = (
        db_session.query(SubscriptionPlan)
        .filter(SubscriptionPlan.code == "monthly-signals")
        .one()
    )
    for key, value in overrides.items():
        assert getattr(plan, key) == value


def test_public_monthly_plan_bootstrap_does_not_swallow_unrelated_price_conflict(
    db_session,
):
    db_session.add(
        SubscriptionPlan(
            code="other-plan",
            display_name_en="Other plan",
            display_name_fr="Autre plan",
            stripe_price_id="price_monthly_phase6",
            billing_interval="month",
            is_active=True,
            is_configured=True,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    db_session.commit()

    with pytest.raises(IntegrityError):
        ensure_public_monthly_plan_configured(db_session, now=NOW)

    assert (
        db_session.query(SubscriptionPlan)
        .filter(SubscriptionPlan.code == "monthly-signals")
        .count()
        == 0
    )


def _portal_token(
    db,
    subscriber,
    raw_token,
    *,
    customer_id=None,
    expires_at=NOW + timedelta(minutes=15),
    delivery_claimed_at=None,
    delivered_at=None,
    delivery_failed_at=None,
    consumed_at=None,
    invalidated_at=None,
):
    token = PortalAccessToken(
        token_hash=hash_portal_token(raw_token),
        subscriber_id=subscriber.id,
        stripe_customer_id=customer_id or subscriber.stripe_customer_id,
        purpose=PortalAccessTokenPurpose.customer_portal,
        expires_at=expires_at,
        delivery_claimed_at=delivery_claimed_at,
        delivered_at=delivered_at,
        delivery_failed_at=delivery_failed_at,
        consumed_at=consumed_at,
        invalidated_at=invalidated_at,
        correlation_id="portal-correlation",
        created_at=NOW - timedelta(minutes=1),
        updated_at=NOW - timedelta(minutes=1),
    )
    db.add(token)
    db.commit()
    return token


def test_checkout_uses_server_plan_metadata_and_trusted_redirects(db_session):
    plan = _plan(db_session)
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url="https://checkout.stripe.com/c/pay/session")

    checkout_url = create_public_checkout_session(
        db_session,
        plan_code="monthly-signals",
        locale="fr",
        request_id="a819f52c-f6b2-4c37-9dd1-f79035a93864",
        now=NOW,
        create_session=fake_create,
    )

    assert checkout_url == "https://checkout.stripe.com/c/pay/session"
    assert captured["mode"] == "subscription"
    assert captured["line_items"] == [
        {"price": "price_monthly_phase6", "quantity": 1}
    ]
    assert captured["success_url"] == (
        "https://app.auroratio.test/subscription/success"
        "?session_id={CHECKOUT_SESSION_ID}"
    )
    assert captured["cancel_url"] == (
        "https://app.auroratio.test/subscription/cancelled"
    )
    assert captured["locale"] == "fr"
    assert captured["metadata"] == {
        "subscription_model": ACCOUNTLESS_FLOW_MARKER,
        "checkout_flow": "public_signal_checkout",
        "plan_code": plan.code,
        "preferred_language": "fr",
    }
    assert captured["subscription_data"]["metadata"] == captured["metadata"]
    assert "user_id" not in captured["metadata"]
    assert "email" not in captured["metadata"]
    assert "client_reference_id" not in captured
    assert "customer" not in captured
    assert "customer_email" not in captured
    assert captured["api_key"] == "sk_test_phase6"
    assert captured["idempotency_key"] == (
        "public-checkout:a819f52c-f6b2-4c37-9dd1-f79035a93864"
    )
    assert db_session.query(Subscriber).count() == 0
    assert db_session.query(SubscriberSubscription).count() == 0
    assert db_session.query(AccessEntitlement).count() == 0
    assert db_session.query(User).count() == 0
    assert {
        event.action for event in db_session.query(AuditEvent).all()
    } == {"checkout_session_requested", "checkout_session_created"}


def test_checkout_rejects_arbitrary_price_and_invalid_plan(db_session):
    _plan(db_session)

    with pytest.raises(ValidationError):
        CheckoutSessionRequest.model_validate(
            {
                "plan_code": "monthly-signals",
                "locale": "en",
                "request_id": "a819f52c-f6b2-4c37-9dd1-f79035a93864",
                "price_id": "price_attacker",
            }
        )

    with pytest.raises(InvalidPublicBillingRequest):
        create_public_checkout_session(
            db_session,
            plan_code="attacker-plan",
            locale="en",
            request_id="a819f52c-f6b2-4c37-9dd1-f79035a93864",
            now=NOW,
            create_session=lambda **kwargs: None,
        )


def test_checkout_missing_configuration_and_provider_errors_fail_safely(
    monkeypatch,
    db_session,
):
    _plan(db_session)
    monkeypatch.delenv("STRIPE_MONTHLY_SIGNAL_PRICE_ID")
    with pytest.raises(PublicBillingConfigurationError):
        create_public_checkout_session(
            db_session,
            plan_code="monthly-signals",
            locale="en",
            request_id="a819f52c-f6b2-4c37-9dd1-f79035a93864",
            now=NOW,
        )

    monkeypatch.setenv("STRIPE_MONTHLY_SIGNAL_PRICE_ID", "price_monthly_phase6")

    def stripe_failure(**kwargs):
        raise stripe.error.APIConnectionError("provider unavailable")

    with pytest.raises(PublicBillingProviderError) as exc_info:
        create_public_checkout_session(
            db_session,
            plan_code="monthly-signals",
            locale="en",
            request_id="571623cd-550d-486d-a67f-a531c4734779",
            now=NOW,
            create_session=stripe_failure,
        )
    assert "provider unavailable" not in str(exc_info.value)
    assert db_session.query(Subscriber).count() == 0
    assert db_session.query(AccessEntitlement).count() == 0


@pytest.mark.parametrize(
    "url",
    [
        "http://checkout.stripe.com/c/pay/session",
        "https://checkout.stripe.com.attacker.test/session",
        "https://user@checkout.stripe.com/session",
        "https://example.test/session",
        "",
    ],
)
def test_checkout_rejects_malformed_or_untrusted_stripe_urls(db_session, url):
    _plan(db_session)
    with pytest.raises(PublicBillingProviderError):
        create_public_checkout_session(
            db_session,
            plan_code="monthly-signals",
            locale="en",
            request_id="a819f52c-f6b2-4c37-9dd1-f79035a93864",
            now=NOW,
            create_session=lambda **kwargs: SimpleNamespace(url=url),
        )


def test_checkout_requires_consistent_local_plan_configuration(db_session):
    _plan(db_session, price_id="price_different")
    with pytest.raises(PublicBillingConfigurationError):
        create_public_checkout_session(
            db_session,
            plan_code="monthly-signals",
            locale="en",
            request_id="a819f52c-f6b2-4c37-9dd1-f79035a93864",
            now=NOW,
        )


@pytest.mark.parametrize(
    "public_app_url",
    [
        "https://app.auroratio.test/redirect",
        "https://user@app.auroratio.test",
        "https://app.auroratio.test?next=https://attacker.test",
        "http://app.auroratio.test",
        "javascript:alert(1)",
    ],
)
def test_checkout_rejects_untrusted_public_application_origins(
    monkeypatch,
    db_session,
    public_app_url,
):
    _plan(db_session)
    monkeypatch.setenv("PUBLIC_APP_URL", public_app_url)

    with pytest.raises(PublicBillingConfigurationError):
        create_public_checkout_session(
            db_session,
            plan_code="monthly-signals",
            locale="en",
            request_id="a819f52c-f6b2-4c37-9dd1-f79035a93864",
            now=NOW,
            create_session=lambda **kwargs: pytest.fail(
                "Stripe must not be called for an untrusted redirect origin"
            ),
        )


def test_known_portal_request_hashes_token_and_dispatches_fragment_link(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, email="Billing@Example.com")
    subscriber_id = subscriber.id
    _subscription(db_session, subscriber, plan)

    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="  billing@example.com ",
            locale="fr",
            now=NOW,
        )
    )

    assert isinstance(batch, PortalDeliveryBatch)
    assert batch.to_email == "billing@example.com"
    assert batch.locale == "fr"
    assert len(batch.items) == 1
    raw_token = batch.items[0].raw_token

    delivered = {}

    async def fake_delivery(**kwargs):
        delivered.update(kwargs)
        return True

    asyncio.run(
        deliver_portal_access_batch(
            batch,
            deliver_links=fake_delivery,
            session_factory=lambda: db_session,
            now_factory=lambda: NOW + timedelta(seconds=1),
        )
    )

    assert delivered["to_email"] == "billing@example.com"
    assert delivered["locale"] == "fr"
    assert len(delivered["links"]) == 1
    parsed_link = urlsplit(delivered["links"][0]["url"])
    assert parsed_link.scheme == "https"
    assert parsed_link.netloc == "app.auroratio.test"
    assert parsed_link.path == "/manage-subscription/access"
    assert parsed_link.query == ""
    assert parse_qs(parsed_link.fragment)["token"][0] == raw_token
    assert "cus_phase6" not in delivered["links"][0]["label"]
    assert "sub_phase6" not in delivered["links"][0]["label"]

    stored = db_session.query(PortalAccessToken).one()
    assert stored.subscriber_id == subscriber_id
    assert stored.stripe_customer_id == "cus_phase6"
    assert stored.token_hash == hash_portal_token(raw_token)
    assert stored.token_hash != raw_token
    assert stored.purpose == PortalAccessTokenPurpose.customer_portal
    assert stored.expires_at == NOW + timedelta(minutes=15)
    assert stored.delivery_claimed_at == NOW + timedelta(seconds=1)
    assert stored.delivered_at == NOW + timedelta(seconds=1)
    assert stored.consumed_at is None
    assert stored.invalidated_at is None
    assert db_session.query(PortalLinkIssuance).count() == 1
    assert raw_token not in repr(
        [event.event_metadata for event in db_session.query(AuditEvent).all()]
    )


def test_unknown_email_matches_known_email_public_response(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    _subscription(db_session, subscriber, plan)

    known_batch = asyncio.run(
        request_portal_access(
            db_session,
            email="billing@example.com",
            locale="en",
            now=NOW,
        )
    )
    token_count = db_session.query(PortalAccessToken).count()
    unknown_batch = asyncio.run(
        request_portal_access(
            db_session,
            email="unknown@example.com",
            locale="en",
            now=NOW,
        )
    )

    assert isinstance(known_batch, PortalDeliveryBatch)
    assert unknown_batch is None
    assert db_session.query(PortalAccessToken).count() == token_count


def test_portal_request_does_not_require_active_entitlement(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    _subscription(
        db_session,
        subscriber,
        plan,
        billing_status=SubscriberBillingStatus.ended,
        stripe_status="canceled",
        period_end=NOW - timedelta(days=2),
    )

    batch = asyncio.run(
        request_portal_access(
            db_session,
            email=subscriber.normalized_email,
            locale="en",
            now=NOW,
        )
    )
    assert isinstance(batch, PortalDeliveryBatch)
    assert db_session.query(AccessEntitlement).count() == 0


def test_portal_delivery_failure_is_generic_and_invalidates_token(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    _subscription(db_session, subscriber, plan)

    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="billing@example.com",
            locale="en",
            now=NOW,
        )
    )
    assert isinstance(batch, PortalDeliveryBatch)

    async def failed_delivery(**kwargs):
        return False

    asyncio.run(
        deliver_portal_access_batch(
            batch,
            deliver_links=failed_delivery,
            session_factory=lambda: db_session,
            now_factory=lambda: NOW + timedelta(seconds=1),
        )
    )

    token = db_session.query(PortalAccessToken).one()
    assert token.invalidated_at == NOW + timedelta(seconds=1)
    assert (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "portal_link_delivery_failed")
        .count()
        == 1
    )


def test_portal_delivery_outcome_database_failure_is_contained(
    caplog,
    db_session,
):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, email="delivery-db@example.com")
    _subscription(db_session, subscriber, plan)
    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="delivery-db@example.com",
            locale="en",
            now=NOW,
        )
    )
    assert isinstance(batch, PortalDeliveryBatch)

    async def delivered(**kwargs):
        return True

    session_attempted = False

    def unavailable_session():
        nonlocal session_attempted
        session_attempted = True
        raise RuntimeError("database unavailable")

    with caplog.at_level(logging.ERROR):
        asyncio.run(
            deliver_portal_access_batch(
                batch,
                deliver_links=delivered,
                session_factory=unavailable_session,
                now_factory=lambda: NOW + timedelta(seconds=1),
            )
        )

    assert session_attempted is True
    assert batch.items[0].raw_token not in caplog.text


def test_duplicate_email_issues_one_token_per_distinct_stripe_customer(
    db_session,
):
    plan = _plan(db_session)
    active_subscriber = _subscriber(
        db_session,
        customer_id="cus_active",
        email="shared@example.com",
    )
    historical_subscriber = _subscriber(
        db_session,
        customer_id="cus_historical",
        email="shared@example.com",
    )
    active_subscriber.updated_at = NOW - timedelta(days=30)
    historical_subscriber.updated_at = NOW
    db_session.commit()
    _subscription(
        db_session,
        active_subscriber,
        plan,
        subscription_id="sub_active",
        billing_status=SubscriberBillingStatus.active,
        stripe_status="active",
    )
    _subscription(
        db_session,
        historical_subscriber,
        plan,
        subscription_id="sub_historical",
        billing_status=SubscriberBillingStatus.ended,
        stripe_status="canceled",
        period_end=NOW - timedelta(days=20),
    )

    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="shared@example.com",
            locale="en",
            now=NOW,
        )
    )

    assert isinstance(batch, PortalDeliveryBatch)
    assert len(batch.items) == 2
    assert db_session.query(PortalAccessToken).count() == 2
    assert db_session.query(PortalLinkIssuance).count() == 2
    tokens = {
        token.id: token.subscriber_id
        for token in db_session.query(PortalAccessToken).all()
    }
    assert tokens[batch.items[0].token_id] == active_subscriber.id
    assert tokens[batch.items[1].token_id] == historical_subscriber.id
    assert "Active" in batch.items[0].label
    assert "Historical" in batch.items[1].label
    assert "cus_" not in " ".join(item.label for item in batch.items)
    assert "sub_" not in " ".join(item.label for item in batch.items)


def test_portal_relationships_use_documented_subscription_priority(db_session):
    plan = _plan(db_session)
    cases = [
        (
            "active",
            SubscriberBillingStatus.active,
            "active",
            False,
            NOW + timedelta(days=30),
        ),
        (
            "delinquent",
            SubscriberBillingStatus.delinquent,
            "past_due",
            False,
            NOW + timedelta(days=20),
        ),
        (
            "scheduled",
            SubscriberBillingStatus.active,
            "active",
            True,
            NOW + timedelta(days=10),
        ),
        (
            "historical",
            SubscriberBillingStatus.ended,
            "canceled",
            False,
            NOW - timedelta(days=1),
        ),
    ]
    for (
        name,
        billing_status,
        stripe_status,
        cancel_at_period_end,
        period_end,
    ) in cases:
        subscriber = _subscriber(
            db_session,
            customer_id=f"cus_priority_{name}",
            email="priority@example.com",
        )
        _subscription(
            db_session,
            subscriber,
            plan,
            subscription_id=f"sub_priority_{name}",
            billing_status=billing_status,
            stripe_status=stripe_status,
            cancel_at_period_end=cancel_at_period_end,
            period_end=period_end,
        )

    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="priority@example.com",
            locale="en",
            now=NOW,
        )
    )

    assert isinstance(batch, PortalDeliveryBatch)
    status_labels = [
        item.label.split(" — ", 1)[1].split(" · ", 1)[0]
        for item in batch.items
    ]
    assert status_labels == [
        "Active",
        "Payment action required",
        "Cancellation scheduled",
        "Historical",
    ]


def test_two_active_customers_each_receive_customer_bound_token(db_session):
    plan = _plan(db_session)
    first = _subscriber(
        db_session,
        customer_id="cus_first",
        email="shared-active@example.com",
    )
    second = _subscriber(
        db_session,
        customer_id="cus_second",
        email="shared-active@example.com",
    )
    _subscription(
        db_session,
        first,
        plan,
        subscription_id="sub_first",
        period_end=NOW + timedelta(days=10),
    )
    _subscription(
        db_session,
        second,
        plan,
        subscription_id="sub_second",
        period_end=NOW + timedelta(days=20),
    )
    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="shared-active@example.com",
            locale="en",
            now=NOW,
        )
    )
    assert isinstance(batch, PortalDeliveryBatch)
    assert len(batch.items) == 2

    calls_by_token = {}
    for item in batch.items:
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                url="https://billing.stripe.com/p/session/secure"
            )

        exchange_portal_access_token(
            db_session,
            raw_token=item.raw_token,
            now=NOW + timedelta(seconds=1),
            create_portal_session=fake_create,
        )
        calls_by_token[item.token_id] = captured["customer"]

    token_owners = {
        token.id: token.stripe_customer_id
        for token in db_session.query(PortalAccessToken).all()
    }
    assert calls_by_token == token_owners


def test_portal_token_does_not_retarget_after_subscriber_customer_mutation(
    db_session,
):
    plan = _plan(db_session)
    subscriber = _subscriber(
        db_session,
        customer_id="cus_original",
        email="frozen@example.com",
    )
    _subscription(db_session, subscriber, plan, subscription_id="sub_original")
    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="frozen@example.com",
            locale="en",
            now=NOW,
        )
    )
    assert isinstance(batch, PortalDeliveryBatch)
    token = db_session.query(PortalAccessToken).one()
    assert token.stripe_customer_id == "cus_original"

    subscriber.stripe_customer_id = "cus_mutated"
    db_session.commit()
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url="https://billing.stripe.com/p/session/secure")

    with pytest.raises(PortalTokenRejected):
        exchange_portal_access_token(
            db_session,
            raw_token=batch.items[0].raw_token,
            now=NOW + timedelta(seconds=1),
            create_portal_session=fake_create,
        )

    assert captured == {}
    db_session.refresh(token)
    assert token.invalidated_at == NOW + timedelta(seconds=1)


def test_multiple_subscriptions_for_one_customer_are_deduplicated_by_priority(
    db_session,
):
    plan = _plan(db_session)
    subscriber = _subscriber(
        db_session,
        customer_id="cus_one_relationship",
        email="multi-subscription@example.com",
    )
    _subscription(
        db_session,
        subscriber,
        plan,
        subscription_id="sub_cancelled",
        billing_status=SubscriberBillingStatus.ended,
        stripe_status="canceled",
        period_end=NOW - timedelta(days=10),
    )
    _subscription(
        db_session,
        subscriber,
        plan,
        subscription_id="sub_current",
        billing_status=SubscriberBillingStatus.active,
        stripe_status="active",
        period_end=NOW + timedelta(days=20),
    )

    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="multi-subscription@example.com",
            locale="en",
            now=NOW,
        )
    )

    assert isinstance(batch, PortalDeliveryBatch)
    assert len(batch.items) == 1
    assert "Active" in batch.items[0].label
    assert db_session.query(PortalAccessToken).count() == 1


def test_orphan_subscriber_does_not_receive_portal_token(db_session):
    _subscriber(db_session, email="orphan@example.com")

    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="orphan@example.com",
            locale="en",
            now=NOW,
        )
    )

    assert batch is None
    assert db_session.query(PortalAccessToken).count() == 0
    assert db_session.query(PortalLinkIssuance).count() == 0


def test_portal_cooldown_is_durable_and_supersedes_previous_token(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, email="cooldown@example.com")
    _subscription(db_session, subscriber, plan)

    first_batch = asyncio.run(
        request_portal_access(
            db_session,
            email="cooldown@example.com",
            locale="en",
            now=NOW,
        )
    )
    throttled_batch = asyncio.run(
        request_portal_access(
            db_session,
            email="cooldown@example.com",
            locale="en",
            now=NOW + timedelta(minutes=1),
        )
    )

    assert isinstance(first_batch, PortalDeliveryBatch)
    assert throttled_batch is None
    assert db_session.query(PortalAccessToken).count() == 1

    replacement_batch = asyncio.run(
        request_portal_access(
            db_session,
            email="cooldown@example.com",
            locale="en",
            now=NOW + timedelta(minutes=5),
        )
    )
    assert isinstance(replacement_batch, PortalDeliveryBatch)
    assert db_session.query(PortalAccessToken).count() == 2
    first_token = (
        db_session.query(PortalAccessToken)
        .filter(PortalAccessToken.id == first_batch.items[0].token_id)
        .one()
    )
    assert first_token.invalidated_at == NOW + timedelta(minutes=5)


def test_expired_portal_tokens_are_opportunistically_invalidated(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, email="expired-cleanup@example.com")
    _subscription(db_session, subscriber, plan)
    expired = _portal_token(
        db_session,
        subscriber,
        "e" * 43,
        expires_at=NOW - timedelta(seconds=1),
    )

    asyncio.run(
        request_portal_access(
            db_session,
            email="unknown@example.com",
            locale="en",
            now=NOW,
        )
    )

    db_session.refresh(expired)
    assert expired.invalidated_at == NOW


def test_superseded_queued_token_is_not_emailed(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, email="stale-delivery@example.com")
    _subscription(db_session, subscriber, plan)
    first_batch = asyncio.run(
        request_portal_access(
            db_session,
            email="stale-delivery@example.com",
            locale="en",
            now=NOW,
        )
    )
    replacement_batch = asyncio.run(
        request_portal_access(
            db_session,
            email="stale-delivery@example.com",
            locale="en",
            now=NOW + timedelta(minutes=5),
        )
    )
    assert isinstance(first_batch, PortalDeliveryBatch)
    assert isinstance(replacement_batch, PortalDeliveryBatch)
    calls = []

    async def delivery(**kwargs):
        calls.append(kwargs)
        return True

    asyncio.run(
        deliver_portal_access_batch(
            first_batch,
            deliver_links=delivery,
            session_factory=lambda: db_session,
            now_factory=lambda: NOW + timedelta(minutes=5, seconds=1),
        )
    )

    assert calls == []
    first_token = (
        db_session.query(PortalAccessToken)
        .filter(PortalAccessToken.id == first_batch.items[0].token_id)
        .one()
    )
    replacement_token = (
        db_session.query(PortalAccessToken)
        .filter(PortalAccessToken.id == replacement_batch.items[0].token_id)
        .one()
    )
    assert first_token.invalidated_at == NOW + timedelta(minutes=5)
    assert first_token.delivery_claimed_at is None
    assert replacement_token.invalidated_at is None


def test_mixed_delivery_batch_sends_only_current_valid_links(db_session):
    plan = _plan(db_session)
    first = _subscriber(
        db_session,
        customer_id="cus_mixed_valid",
        email="mixed-delivery@example.com",
    )
    second = _subscriber(
        db_session,
        customer_id="cus_mixed_stale",
        email="mixed-delivery@example.com",
    )
    _subscription(db_session, first, plan, subscription_id="sub_mixed_valid")
    _subscription(db_session, second, plan, subscription_id="sub_mixed_stale")
    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="mixed-delivery@example.com",
            locale="en",
            now=NOW,
        )
    )
    assert isinstance(batch, PortalDeliveryBatch)
    assert len(batch.items) == 2
    stale_token = (
        db_session.query(PortalAccessToken)
        .filter(PortalAccessToken.id == batch.items[1].token_id)
        .one()
    )
    stale_token.invalidated_at = NOW + timedelta(seconds=1)
    db_session.commit()
    delivered = {}

    async def delivery(**kwargs):
        delivered.update(kwargs)
        return True

    asyncio.run(
        deliver_portal_access_batch(
            batch,
            deliver_links=delivery,
            session_factory=lambda: db_session,
            now_factory=lambda: NOW + timedelta(seconds=2),
        )
    )

    assert len(delivered["links"]) == 1
    assert parse_qs(urlsplit(delivered["links"][0]["url"]).fragment)["token"][0] == (
        batch.items[0].raw_token
    )
    valid_token = (
        db_session.query(PortalAccessToken)
        .filter(PortalAccessToken.id == batch.items[0].token_id)
        .one()
    )
    stale_token = (
        db_session.query(PortalAccessToken)
        .filter(PortalAccessToken.id == batch.items[1].token_id)
        .one()
    )
    assert valid_token.delivered_at == NOW + timedelta(seconds=2)
    assert stale_token.delivered_at is None


def test_duplicate_delivery_task_sends_at_most_once(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, email="duplicate-task@example.com")
    _subscription(db_session, subscriber, plan)
    batch = asyncio.run(
        request_portal_access(
            db_session,
            email="duplicate-task@example.com",
            locale="en",
            now=NOW,
        )
    )
    assert isinstance(batch, PortalDeliveryBatch)
    calls = []

    async def delivery(**kwargs):
        calls.append(kwargs)
        return True

    for _ in range(2):
        asyncio.run(
            deliver_portal_access_batch(
                batch,
                deliver_links=delivery,
                session_factory=lambda: db_session,
                now_factory=lambda: NOW + timedelta(seconds=1),
            )
        )

    assert len(calls) == 1
    token = db_session.query(PortalAccessToken).one()
    assert token.delivery_claimed_at == NOW + timedelta(seconds=1)
    assert token.delivered_at == NOW + timedelta(seconds=1)
    assert token.invalidated_at is None


def test_delivery_failure_invalidates_only_claimed_batch(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, email="failure-current@example.com")
    _subscription(db_session, subscriber, plan)
    first_batch = asyncio.run(
        request_portal_access(
            db_session,
            email="failure-current@example.com",
            locale="en",
            now=NOW,
        )
    )
    assert isinstance(first_batch, PortalDeliveryBatch)

    async def failed_after_reissue(**kwargs):
        replacement = await request_portal_access(
            db_session,
            email="failure-current@example.com",
            locale="en",
            now=NOW + timedelta(minutes=5),
        )
        assert isinstance(replacement, PortalDeliveryBatch)
        return False

    asyncio.run(
        deliver_portal_access_batch(
            first_batch,
            deliver_links=failed_after_reissue,
            session_factory=lambda: db_session,
            now_factory=lambda: NOW + timedelta(seconds=1),
        )
    )

    tokens = db_session.query(PortalAccessToken).order_by(PortalAccessToken.created_at).all()
    assert len(tokens) == 2
    assert tokens[0].delivery_failed_at == NOW + timedelta(seconds=1)
    assert tokens[0].invalidated_at == NOW + timedelta(seconds=1)
    assert tokens[1].invalidated_at is None
    assert tokens[1].delivery_failed_at is None


@pytest.mark.parametrize(
    "token_state",
    ["consumed", "expired", "customer_mismatch"],
)
def test_unavailable_or_mismatched_tokens_are_never_emailed(db_session, token_state):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, email=f"{token_state}@example.com")
    _subscription(db_session, subscriber, plan)
    batch = asyncio.run(
        request_portal_access(
            db_session,
            email=f"{token_state}@example.com",
            locale="en",
            now=NOW,
        )
    )
    assert isinstance(batch, PortalDeliveryBatch)
    token = db_session.query(PortalAccessToken).one()
    if token_state == "consumed":
        token.consumed_at = NOW + timedelta(seconds=1)
    elif token_state == "expired":
        pass
    else:
        token.stripe_customer_id = "cus_wrong"
    db_session.commit()
    calls = []

    async def delivery(**kwargs):
        calls.append(kwargs)
        return True

    asyncio.run(
        deliver_portal_access_batch(
            batch,
            deliver_links=delivery,
            session_factory=lambda: db_session,
            now_factory=(
                lambda: NOW + timedelta(minutes=20)
                if token_state == "expired"
                else NOW + timedelta(seconds=2)
            ),
        )
    )

    assert calls == []


def test_portal_link_issuance_timestamps_are_aware_and_normalized(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, email="timezone@example.com")
    _subscription(db_session, subscriber, plan)
    non_utc_now = NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))

    asyncio.run(
        request_portal_access(
            db_session,
            email="timezone@example.com",
            locale="en",
            now=non_utc_now,
        )
    )

    db_session.expire_all()
    issuance = db_session.query(PortalLinkIssuance).one()
    assert issuance.last_issued_at == NOW
    assert issuance.last_issued_at.tzinfo == timezone.utc
    assert issuance.next_allowed_at == NOW + timedelta(minutes=5)

    second_subscriber = _subscriber(
        db_session,
        customer_id="cus_naive_issuance",
        email="naive-issuance@example.com",
    )
    db_session.add(
        PortalLinkIssuance(
            subscriber_id=second_subscriber.id,
            last_issued_at=NOW.replace(tzinfo=None),
            next_allowed_at=(NOW + timedelta(minutes=5)).replace(tzinfo=None),
            created_at=NOW.replace(tzinfo=None),
            updated_at=NOW.replace(tzinfo=None),
        )
    )
    with pytest.raises(StatementError):
        db_session.commit()
    db_session.rollback()


def test_concurrent_portal_requests_claim_one_database_cooldown(tmp_path):
    database_path = tmp_path / "portal-issuance-concurrency.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    configure_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    seed = session_factory()
    plan = _plan(seed)
    subscriber = _subscriber(seed, email="concurrent-request@example.com")
    _subscription(seed, subscriber, plan)
    seed.close()

    barrier = threading.Barrier(2)
    outcomes = []
    errors = []

    def request_link():
        session = session_factory()
        try:
            barrier.wait(timeout=3)
            outcomes.append(
                asyncio.run(
                    request_portal_access(
                        session,
                        email="concurrent-request@example.com",
                        locale="en",
                        now=NOW,
                    )
                )
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            session.close()

    first = threading.Thread(target=request_link)
    second = threading.Thread(target=request_link)
    first.start()
    second.start()
    first.join(timeout=8)
    second.join(timeout=8)

    verification = session_factory()
    try:
        assert errors == []
        assert len(outcomes) == 2
        assert sum(isinstance(outcome, PortalDeliveryBatch) for outcome in outcomes) == 1
        assert sum(outcome is None for outcome in outcomes) == 1
        assert verification.query(PortalLinkIssuance).count() == 1
        assert verification.query(PortalAccessToken).count() == 1
    finally:
        verification.close()
        engine.dispose()


def test_valid_portal_token_uses_trusted_customer_and_is_consumed(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, customer_id="cus_trusted")
    _subscription(db_session, subscriber, plan)
    raw_token = "p" * 43
    token = _portal_token(db_session, subscriber, raw_token)
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url="https://billing.stripe.com/p/session/secure")

    portal_url = exchange_portal_access_token(
        db_session,
        raw_token=raw_token,
        now=NOW,
        create_portal_session=fake_create,
    )

    assert portal_url == "https://billing.stripe.com/p/session/secure"
    assert captured["customer"] == "cus_trusted"
    assert captured["return_url"] == (
        "https://app.auroratio.test/manage-subscription?portal=return"
    )
    assert captured["api_key"] == "sk_test_phase6"
    assert captured["idempotency_key"] == f"portal-access:{token.id}"
    assert captured["customer"] != raw_token
    assert set(captured) <= {
        "customer",
        "return_url",
        "api_key",
        "idempotency_key",
    }
    db_session.refresh(token)
    assert token.consumed_at == NOW
    assert {
        event.action
        for event in db_session.query(AuditEvent)
        .filter(AuditEvent.correlation_id == "portal-correlation")
        .all()
    } == {"portal_token_consumed", "portal_session_created"}


@pytest.mark.parametrize("state", ["expired", "consumed", "invalidated"])
def test_unavailable_portal_tokens_are_rejected(db_session, state):
    subscriber = _subscriber(db_session)
    raw_token = "u" * 43
    kwargs = {}
    if state == "expired":
        kwargs["expires_at"] = NOW - timedelta(seconds=1)
    elif state == "consumed":
        kwargs["consumed_at"] = NOW - timedelta(seconds=1)
    else:
        kwargs["invalidated_at"] = NOW - timedelta(seconds=1)
    _portal_token(db_session, subscriber, raw_token, **kwargs)

    with pytest.raises(PortalTokenRejected):
        exchange_portal_access_token(
            db_session,
            raw_token=raw_token,
            now=NOW,
            create_portal_session=lambda **kwargs: pytest.fail(
                "Stripe must not be called"
            ),
        )


def test_invalid_portal_token_is_rejected_without_customer_input(db_session):
    _subscriber(db_session)
    with pytest.raises(PortalTokenRejected):
        exchange_portal_access_token(
            db_session,
            raw_token="x" * 43,
            now=NOW,
            create_portal_session=lambda **kwargs: pytest.fail(
                "Stripe must not be called"
            ),
        )


def test_portal_provider_failure_rolls_back_token_claim_and_hides_details(
    caplog,
    db_session,
):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    _subscription(db_session, subscriber, plan)
    raw_token = "r" * 43
    token = _portal_token(db_session, subscriber, raw_token)

    def provider_failure(**kwargs):
        raise stripe.error.APIConnectionError(
            f"provider failed for secret token {raw_token}"
        )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(PublicBillingProviderError):
            exchange_portal_access_token(
                db_session,
                raw_token=raw_token,
                now=NOW,
                create_portal_session=provider_failure,
            )

    db_session.refresh(token)
    assert token.consumed_at is None
    assert raw_token not in caplog.text
    assert "provider failed" not in caplog.text


def test_processed_portal_token_cannot_be_replayed(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    _subscription(db_session, subscriber, plan)
    raw_token = "s" * 43
    _portal_token(db_session, subscriber, raw_token)
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(url="https://billing.stripe.com/p/session/secure")

    exchange_portal_access_token(
        db_session,
        raw_token=raw_token,
        now=NOW,
        create_portal_session=fake_create,
    )
    with pytest.raises(PortalTokenRejected):
        exchange_portal_access_token(
            db_session,
            raw_token=raw_token,
            now=NOW + timedelta(seconds=1),
            create_portal_session=fake_create,
        )
    assert len(calls) == 1


def test_concurrent_portal_consumption_allows_one_session(tmp_path):
    database_path = tmp_path / "portal-concurrency.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    configure_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    seed = session_factory()
    plan = _plan(seed)
    subscriber = _subscriber(seed)
    _subscription(seed, subscriber, plan)
    raw_token = "c" * 43
    _portal_token(seed, subscriber, raw_token)
    seed.close()

    provider_entered = threading.Event()
    release_provider = threading.Event()
    provider_calls = []
    outcomes = []

    def fake_create(**kwargs):
        provider_calls.append(kwargs)
        provider_entered.set()
        assert release_provider.wait(timeout=3)
        return SimpleNamespace(url="https://billing.stripe.com/p/session/secure")

    def exchange():
        session = session_factory()
        try:
            outcomes.append(
                (
                    "success",
                    exchange_portal_access_token(
                        session,
                        raw_token=raw_token,
                        now=NOW,
                        create_portal_session=fake_create,
                    ),
                )
            )
        except PortalTokenRejected:
            outcomes.append(("rejected", None))
        finally:
            session.close()

    first = threading.Thread(target=exchange)
    second = threading.Thread(target=exchange)
    first.start()
    assert provider_entered.wait(timeout=3)
    second.start()
    time.sleep(0.1)
    release_provider.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert sorted(outcome[0] for outcome in outcomes) == ["rejected", "success"]
    assert len(provider_calls) == 1
    engine.dispose()
