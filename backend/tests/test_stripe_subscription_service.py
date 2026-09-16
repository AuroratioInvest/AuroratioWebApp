import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from database import configure_sqlite_foreign_keys
from models import Subscription, SubscriptionStatus, User
from routers import stripe_router
from services import stripe_subscription_service as service
from services.subscriber_domain import entitlement_grants_access
from subscriber_models import (
    AccessEntitlement,
    EntitlementAccessStatus,
    IntegrationEvent,
    IntegrationProcessingStatus,
    Subscriber,
    SubscriberBillingStatus,
    SubscriberSubscription,
    SubscriptionAccessEvent,
    SubscriptionPlan,
)


NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
PERIOD_START = NOW - timedelta(days=15)
PERIOD_END = NOW + timedelta(days=15)


@pytest.fixture(autouse=True)
def phase_four_environment(monkeypatch, db_session):
    monkeypatch.delenv("STRIPE_PAYMENT_FAILURE_GRACE_DAYS", raising=False)
    monkeypatch.delenv("STRIPE_EVENT_RETRY_SECONDS", raising=False)
    monkeypatch.delenv("STRIPE_EVENT_MAX_ATTEMPTS", raising=False)


def _plan(
    db_session,
    *,
    price_id: str = "price_launch",
    active: bool = True,
    configured: bool = True,
    archived_at=None,
):
    plan = SubscriptionPlan(
        code=f"plan-{price_id}",
        display_name_en="Launch",
        display_name_fr="Lancement",
        stripe_price_id=price_id,
        is_active=active,
        is_configured=configured,
        archived_at=archived_at,
    )
    db_session.add(plan)
    db_session.commit()
    return plan


def _subscription_object(
    *,
    subscription_id: str = "sub_new",
    customer_id: str = "cus_new",
    email: str = "Subscriber@Example.com",
    price_id: str = "price_launch",
    status: str = "active",
    period_start: datetime | None = PERIOD_START,
    period_end: datetime | None = PERIOD_END,
    cancel_at_period_end: bool = False,
    canceled_at: datetime | None = None,
    ended_at: datetime | None = None,
):
    def epoch(value):
        return int(value.timestamp()) if value is not None else None

    return {
        "id": subscription_id,
        "object": "subscription",
        "customer": {
            "id": customer_id,
            "email": email,
            "address": {"country": "FR"},
        },
        "status": status,
        "current_period_start": epoch(period_start),
        "current_period_end": epoch(period_end),
        "cancel_at_period_end": cancel_at_period_end,
        "canceled_at": epoch(canceled_at),
        "ended_at": epoch(ended_at),
        "items": {
            "data": [
                {
                    "price": {"id": price_id},
                }
            ]
        },
        "metadata": {"preferred_language": "fr"},
    }


def _event(
    *,
    event_id: str = "evt_created",
    event_type: str = "customer.subscription.created",
    created_at: datetime = NOW,
    data_object=None,
):
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "created": int(created_at.timestamp()),
        "livemode": False,
        "data": {
            "object": data_object
            if data_object is not None
            else _subscription_object()
        },
    }


def _payload(event) -> bytes:
    return json.dumps(event, separators=(",", ":"), sort_keys=True).encode()


def _process(db_session, event, *, retrieve_subscription=None, now=NOW):
    kwargs = {}
    if retrieve_subscription is not None:
        kwargs["retrieve_subscription"] = retrieve_subscription
    elif event["type"] in service.SUBSCRIPTION_EVENT_TYPES:
        kwargs["retrieve_subscription"] = (
            lambda subscription_id: event["data"]["object"]
        )
    return service.process_verified_stripe_event(
        db_session,
        event=event,
        payload=_payload(event),
        now=now,
        **kwargs,
    )


def _domain_rows(db_session):
    return {
        "subscribers": db_session.query(Subscriber).count(),
        "subscriptions": db_session.query(SubscriberSubscription).count(),
        "entitlements": db_session.query(AccessEntitlement).count(),
        "history": db_session.query(SubscriptionAccessEvent).count(),
    }


def _created_domain(db_session):
    subscription = db_session.query(SubscriberSubscription).one()
    entitlement = db_session.query(AccessEntitlement).one()
    return subscription, entitlement


def test_status_mapping_is_explicit_and_preserves_unknown_as_pending():
    expected = {
        "active": SubscriberBillingStatus.active,
        "past_due": SubscriberBillingStatus.delinquent,
        "unpaid": SubscriberBillingStatus.delinquent,
        "canceled": SubscriberBillingStatus.ended,
        "cancelled": SubscriberBillingStatus.ended,
        "incomplete_expired": SubscriberBillingStatus.ended,
        "incomplete": SubscriberBillingStatus.pending,
        "trialing": SubscriberBillingStatus.pending,
        "paused": SubscriberBillingStatus.pending,
        "future_status": SubscriberBillingStatus.pending,
    }
    assert {
        value: service.map_stripe_billing_status(value) for value in expected
    } == expected


def test_subscription_creation_uses_customer_identity_and_activates_access(db_session):
    _plan(db_session)
    outcome = _process(db_session, _event())

    subscriber = db_session.query(Subscriber).one()
    subscription, entitlement = _created_domain(db_session)

    assert outcome.status == IntegrationProcessingStatus.processed
    assert subscriber.stripe_customer_id == "cus_new"
    assert subscriber.stripe_email == "Subscriber@Example.com"
    assert subscriber.normalized_email == "subscriber@example.com"
    assert subscriber.preferred_language == "fr"
    assert subscriber.billing_country == "FR"
    assert subscription.subscriber_id == subscriber.id
    assert subscription.stripe_status == "active"
    assert subscription.billing_status == SubscriberBillingStatus.active
    assert subscription.current_period_end == PERIOD_END
    assert entitlement.status == EntitlementAccessStatus.active
    assert entitlement.paid_through_at == PERIOD_END
    assert entitlement_grants_access(entitlement, now=NOW)
    assert db_session.query(User).count() == 0


def test_same_customer_updates_same_subscriber_and_email_is_not_identity(db_session):
    _plan(db_session)
    _process(db_session, _event())

    updated = _subscription_object(email="new@example.com")
    _process(
        db_session,
        _event(
            event_id="evt_updated",
            event_type="customer.subscription.updated",
            created_at=NOW + timedelta(seconds=1),
            data_object=updated,
        ),
    )

    assert db_session.query(Subscriber).count() == 1
    assert db_session.query(Subscriber).one().stripe_email == "new@example.com"

    second = _subscription_object(
        subscription_id="sub_other",
        customer_id="cus_other",
        email="new@example.com",
    )
    _process(
        db_session,
        _event(
            event_id="evt_other",
            created_at=NOW + timedelta(seconds=2),
            data_object=second,
        ),
    )
    assert db_session.query(Subscriber).count() == 2
    assert db_session.query(User).count() == 0


def test_same_customer_can_have_multiple_historical_subscriptions(db_session):
    _plan(db_session)
    _process(db_session, _event())
    replacement = _subscription_object(subscription_id="sub_replacement")
    _process(
        db_session,
        _event(
            event_id="evt_replacement",
            created_at=NOW + timedelta(seconds=1),
            data_object=replacement,
        ),
    )

    assert db_session.query(Subscriber).count() == 1
    assert db_session.query(SubscriberSubscription).count() == 2
    assert db_session.query(AccessEntitlement).count() == 2


def test_checkout_session_uses_authoritative_subscription_state(db_session):
    _plan(db_session)
    checkout = {
        "id": "cs_new",
        "mode": "subscription",
        "customer": "cus_new",
        "customer_details": {"email": "checkout@example.com"},
        "subscription": "sub_checkout",
    }
    authoritative = _subscription_object(
        subscription_id="sub_checkout",
        email="checkout@example.com",
    )
    retrieved = []

    outcome = _process(
        db_session,
        _event(
            event_id="evt_checkout",
            event_type="checkout.session.completed",
            data_object=checkout,
        ),
        retrieve_subscription=lambda subscription_id: (
            retrieved.append(subscription_id) or authoritative
        ),
    )

    assert outcome.status == IntegrationProcessingStatus.processed
    assert retrieved == ["sub_checkout"]
    assert (
        db_session.query(SubscriberSubscription).one().stripe_subscription_id
        == "sub_checkout"
    )


@pytest.mark.parametrize(
    "plan_values",
    [
        {},
        {"active": False},
        {"configured": False},
        {"archived_at": NOW},
    ],
)
def test_unresolved_or_inactive_plan_never_grants_access(db_session, plan_values):
    if plan_values:
        _plan(db_session, **plan_values)

    outcome = _process(db_session, _event())

    assert outcome.status == IntegrationProcessingStatus.retryable_failure
    assert outcome.retryable
    assert _domain_rows(db_session) == {
        "subscribers": 0,
        "subscriptions": 0,
        "entitlements": 0,
        "history": 0,
    }


def test_missing_subscription_items_is_retryable_and_fails_closed(db_session):
    _plan(db_session)
    stripe_subscription = _subscription_object()
    stripe_subscription["items"] = {"data": []}

    outcome = _process(
        db_session,
        _event(data_object=stripe_subscription),
    )

    assert outcome.status == IntegrationProcessingStatus.retryable_failure
    assert db_session.query(AccessEntitlement).count() == 0


def test_active_subscription_missing_period_end_is_retryable_and_fails_closed(
    db_session,
):
    _plan(db_session)
    missing_date = _subscription_object(period_end=None)

    outcome = _process(db_session, _event(data_object=missing_date))

    assert outcome.status == IntegrationProcessingStatus.retryable_failure
    assert _domain_rows(db_session) == {
        "subscribers": 0,
        "subscriptions": 0,
        "entitlements": 0,
        "history": 0,
    }


def test_ambiguous_mapping_error_is_permanent_and_fails_closed(
    monkeypatch,
    db_session,
):
    _plan(db_session)

    def ambiguous(*args, **kwargs):
        raise service.PermanentStripeEventError("Ambiguous mapping")

    monkeypatch.setattr(service, "_resolve_plan", ambiguous)
    outcome = _process(db_session, _event())

    assert outcome.status == IntegrationProcessingStatus.permanently_failed
    assert db_session.query(AccessEntitlement).count() == 0


def test_duplicate_delivery_is_successful_and_does_not_repeat_history(db_session):
    _plan(db_session)
    event = _event()

    first = _process(db_session, event)
    second = _process(db_session, event)

    assert first.status == IntegrationProcessingStatus.processed
    assert second.status == IntegrationProcessingStatus.processed
    assert second.duplicate
    assert db_session.query(IntegrationEvent).count() == 1
    assert db_session.query(SubscriptionAccessEvent).count() == 1


def test_duplicate_event_id_with_changed_payload_is_rejected_without_reprocessing(
    db_session,
):
    _plan(db_session)
    original = _event()
    _process(db_session, original)
    changed = _event(data_object=_subscription_object(status="canceled"))

    with pytest.raises(service.PermanentStripeEventError):
        _process(db_session, changed)

    subscription, entitlement = _created_domain(db_session)
    assert subscription.billing_status == SubscriberBillingStatus.active
    assert entitlement.status == EntitlementAccessStatus.active
    assert db_session.query(IntegrationEvent).count() == 1
    assert db_session.query(SubscriptionAccessEvent).count() == 1


def test_existing_received_event_is_claimed_once_and_processed(db_session):
    _plan(db_session)
    event = _event(event_id="evt_pre_recorded")
    db_session.add(
        IntegrationEvent(
            provider=service.IntegrationProvider.stripe,
            external_event_id="evt_pre_recorded",
            event_type=event["type"],
            provider_created_at=NOW,
            received_at=NOW,
            processing_status=IntegrationProcessingStatus.received,
        )
    )
    db_session.commit()

    outcome = _process(db_session, event)

    assert outcome.duplicate
    assert outcome.status == IntegrationProcessingStatus.processed
    assert db_session.query(IntegrationEvent).one().processing_attempts == 1
    assert db_session.query(SubscriberSubscription).count() == 1


def test_abandoned_processing_event_is_recoverable(db_session):
    _plan(db_session)
    event = _event(event_id="evt_abandoned")
    db_session.add(
        IntegrationEvent(
            provider=service.IntegrationProvider.stripe,
            external_event_id="evt_abandoned",
            event_type=event["type"],
            provider_created_at=NOW,
            received_at=NOW - timedelta(minutes=1),
            processing_status=IntegrationProcessingStatus.processing,
            processing_attempts=1,
            payload_checksum=hashlib.sha256(_payload(event)).hexdigest(),
        )
    )
    db_session.commit()

    outcome = _process(db_session, event)
    integration = db_session.query(IntegrationEvent).one()

    assert outcome.status == IntegrationProcessingStatus.processed
    assert integration.processing_attempts == 2
    assert integration.processed_at == NOW


def test_unique_insert_race_reuses_the_already_recorded_event(
    monkeypatch,
    db_session,
):
    _plan(db_session)
    event = _event(event_id="evt_race")
    payload = _payload(event)
    db_session.add(
        IntegrationEvent(
            provider=service.IntegrationProvider.stripe,
            external_event_id="evt_race",
            event_type=event["type"],
            provider_created_at=NOW,
            received_at=NOW,
            processing_status=IntegrationProcessingStatus.received,
            payload_checksum=hashlib.sha256(payload).hexdigest(),
        )
    )
    db_session.commit()

    original_lookup = service._integration_event_for_update
    lookup_count = 0

    def race_lookup(db, event_id):
        nonlocal lookup_count
        lookup_count += 1
        if lookup_count == 1:
            return None
        return original_lookup(db, event_id)

    monkeypatch.setattr(service, "_integration_event_for_update", race_lookup)
    outcome = _process(db_session, event)

    assert outcome.status == IntegrationProcessingStatus.processed
    assert outcome.duplicate
    assert lookup_count >= 2
    assert db_session.query(IntegrationEvent).count() == 1
    assert db_session.query(SubscriberSubscription).count() == 1


def test_unsupported_valid_event_is_recorded_as_ignored_without_created_timestamp(
    db_session,
):
    event = {
        "id": "evt_unsupported",
        "type": "charge.refunded",
        "livemode": True,
        "data": {
            "object": {
                "id": "ch_123",
                "payment_method_details": {"card": {"last4": "4242"}},
                "billing_details": {"email": "private@example.com"},
            }
        },
    }

    outcome = _process(db_session, event)
    recorded = db_session.query(IntegrationEvent).one()

    assert outcome.status == IntegrationProcessingStatus.ignored
    assert recorded.processing_status == IntegrationProcessingStatus.ignored
    serialized = json.dumps(recorded.selected_metadata)
    assert "4242" not in serialized
    assert "private@example.com" not in serialized
    assert recorded.payload_checksum == hashlib.sha256(_payload(event)).hexdigest()
    assert _domain_rows(db_session) == {
        "subscribers": 0,
        "subscriptions": 0,
        "entitlements": 0,
        "history": 0,
    }


def test_stale_and_equal_subscription_events_cannot_regress_state_or_contact(
    db_session,
):
    _plan(db_session)
    newest = _subscription_object(email="current@example.com")
    _process(
        db_session,
        _event(
            event_id="evt_newest",
            event_type="customer.subscription.updated",
            created_at=NOW + timedelta(minutes=2),
            data_object=newest,
        ),
    )

    authoritative = _subscription_object(email="authoritative@example.com")
    latest = NOW + timedelta(minutes=2)
    for suffix, created_at in (("old", NOW), ("equal", latest)):
        stale = _subscription_object(email=f"{suffix}@example.com", status="canceled")
        _process(
            db_session,
            _event(
                event_id=f"evt_{suffix}",
                event_type="customer.subscription.deleted",
                created_at=created_at,
                data_object=stale,
            ),
            retrieve_subscription=lambda subscription_id: authoritative,
        )

    subscriber = db_session.query(Subscriber).one()
    subscription, entitlement = _created_domain(db_session)
    assert subscriber.stripe_email == "authoritative@example.com"
    assert subscription.billing_status == SubscriberBillingStatus.active
    assert entitlement.status == EntitlementAccessStatus.active
    assert db_session.query(SubscriptionAccessEvent).count() == 1
    assert subscription.latest_provider_event_created_at == latest


def test_equal_timestamp_cancellation_is_authoritatively_reconciled(db_session):
    _plan(db_session)
    _process(db_session, _event())
    embedded_stale = _subscription_object(cancel_at_period_end=False)
    authoritative = _subscription_object(cancel_at_period_end=True)

    _process(
        db_session,
        _event(
            event_id="evt_equal_cancellation",
            event_type="customer.subscription.updated",
            created_at=NOW,
            data_object=embedded_stale,
        ),
        retrieve_subscription=lambda subscription_id: authoritative,
    )

    subscription, entitlement = _created_domain(db_session)
    assert subscription.cancel_at_period_end
    assert entitlement.status == EntitlementAccessStatus.active
    assert (
        db_session.query(SubscriptionAccessEvent)
        .filter(
            SubscriptionAccessEvent.external_event_id
            == "evt_equal_cancellation"
        )
        .one()
        .event_type
        == "stripe_cancellation_scheduled"
    )


def test_equal_timestamp_deletion_is_not_discarded(db_session):
    _plan(db_session)
    _process(db_session, _event())
    deleted = _subscription_object(
        status="canceled",
        period_end=NOW - timedelta(seconds=1),
        ended_at=NOW - timedelta(seconds=1),
    )

    _process(
        db_session,
        _event(
            event_id="evt_equal_deletion",
            event_type="customer.subscription.deleted",
            created_at=NOW,
            data_object=_subscription_object(),
        ),
        retrieve_subscription=lambda subscription_id: deleted,
    )

    subscription, entitlement = _created_domain(db_session)
    assert subscription.billing_status == SubscriberBillingStatus.ended
    assert entitlement.status == EntitlementAccessStatus.expired


def test_deleted_subscription_uses_signed_deleted_object_when_stripe_returns_404(
    db_session,
):
    _plan(db_session)
    _process(db_session, _event())
    deleted = _subscription_object(
        status="canceled",
        period_end=NOW - timedelta(seconds=1),
        ended_at=NOW - timedelta(seconds=1),
    )

    def missing_subscription(subscription_id):
        raise service.StripeSubscriptionNotFoundError(
            "Stripe subscription no longer exists"
        )

    _process(
        db_session,
        _event(
            event_id="evt_deleted_not_found",
            event_type="customer.subscription.deleted",
            created_at=NOW + timedelta(seconds=1),
            data_object=deleted,
        ),
        retrieve_subscription=missing_subscription,
    )

    subscription, entitlement = _created_domain(db_session)
    assert subscription.billing_status == SubscriberBillingStatus.ended
    assert entitlement.status == EntitlementAccessStatus.expired


def test_authoritative_newer_state_cannot_be_regressed_by_intermediate_event(
    db_session,
):
    _plan(db_session)
    _process(db_session, _event(created_at=NOW - timedelta(minutes=2)))
    canceled = _subscription_object(
        status="canceled",
        period_end=PERIOD_END,
        cancel_at_period_end=True,
        ended_at=NOW,
    )
    invoice = {"id": "in_old", "subscription": "sub_new"}

    _process(
        db_session,
        _event(
            event_id="evt_old_invoice",
            event_type="invoice.paid",
            created_at=NOW - timedelta(minutes=1),
            data_object=invoice,
        ),
        retrieve_subscription=lambda subscription_id: canceled,
    )
    _process(
        db_session,
        _event(
            event_id="evt_intermediate_snapshot",
            event_type="customer.subscription.updated",
            created_at=NOW,
            data_object=_subscription_object(status="active"),
        ),
        retrieve_subscription=lambda subscription_id: canceled,
    )

    subscription, entitlement = _created_domain(db_session)
    assert subscription.billing_status == SubscriberBillingStatus.ended
    assert subscription.stripe_status == "canceled"
    assert subscription.cancel_at_period_end
    assert entitlement.status == EntitlementAccessStatus.active
    assert entitlement.paid_through_at == PERIOD_END
    assert (
        db_session.query(SubscriptionAccessEvent)
        .filter(
            SubscriptionAccessEvent.external_event_id == "evt_old_invoice"
        )
        .one()
        .event_type
        == "stripe_subscription_ended"
    )


def test_authoritative_subscription_retrieval_failure_is_retryable(db_session):
    _plan(db_session)

    def fail_retrieval(subscription_id):
        raise RuntimeError("temporary network failure")

    outcome = _process(
        db_session,
        _event(event_id="evt_retrieval_failure"),
        retrieve_subscription=fail_retrieval,
    )

    assert outcome.status == IntegrationProcessingStatus.retryable_failure
    assert outcome.retryable
    assert db_session.query(Subscriber).count() == 0


def test_active_subscription_uses_single_item_periods_when_root_periods_absent(
    db_session,
):
    _plan(db_session)
    subscription = _subscription_object(period_start=None, period_end=None)
    subscription["items"]["data"][0]["current_period_start"] = int(
        PERIOD_START.timestamp()
    )
    subscription["items"]["data"][0]["current_period_end"] = int(
        PERIOD_END.timestamp()
    )

    outcome = _process(db_session, _event(data_object=subscription))

    assert outcome.status == IntegrationProcessingStatus.processed
    created = db_session.query(SubscriberSubscription).one()
    entitlement = db_session.query(AccessEntitlement).one()
    assert created.current_period_start == PERIOD_START
    assert created.current_period_end == PERIOD_END
    assert created.billing_status == SubscriberBillingStatus.active
    assert entitlement.status == EntitlementAccessStatus.active
    assert entitlement.paid_through_at == PERIOD_END


def test_cancellation_at_period_end_retains_access(db_session):
    _plan(db_session)
    _process(db_session, _event())
    cancellation = _subscription_object(cancel_at_period_end=True)

    _process(
        db_session,
        _event(
            event_id="evt_cancel_scheduled",
            event_type="customer.subscription.updated",
            created_at=NOW + timedelta(seconds=1),
            data_object=cancellation,
        ),
    )

    subscription, entitlement = _created_domain(db_session)
    assert subscription.cancel_at_period_end
    assert subscription.billing_status == SubscriberBillingStatus.active
    assert entitlement.status == EntitlementAccessStatus.active
    assert entitlement.paid_through_at == PERIOD_END
    assert entitlement_grants_access(entitlement, now=PERIOD_END)


def test_deletion_expires_only_after_paid_through(db_session):
    _plan(db_session)
    _process(db_session, _event())
    ended_at = PERIOD_END + timedelta(seconds=1)
    deleted = _subscription_object(
        status="canceled",
        period_end=PERIOD_END,
        canceled_at=PERIOD_END,
        ended_at=PERIOD_END,
    )

    _process(
        db_session,
        _event(
            event_id="evt_deleted",
            event_type="customer.subscription.deleted",
            created_at=ended_at,
            data_object=deleted,
        ),
        now=ended_at,
    )

    subscription, entitlement = _created_domain(db_session)
    assert subscription.stripe_status == "canceled"
    assert subscription.billing_status == SubscriberBillingStatus.ended
    assert entitlement.status == EntitlementAccessStatus.expired
    assert entitlement.expires_at == PERIOD_END
    assert not entitlement_grants_access(entitlement, now=ended_at)


def test_initial_payment_failure_does_not_create_grace_access(db_session):
    _plan(db_session)
    invoice = {"id": "in_initial_failure", "subscription": "sub_new"}
    failed_state = _subscription_object(status="past_due")

    outcome = _process(
        db_session,
        _event(
            event_id="evt_initial_failure",
            event_type="invoice.payment_failed",
            data_object=invoice,
        ),
        retrieve_subscription=lambda subscription_id: failed_state,
    )

    subscription, entitlement = _created_domain(db_session)
    assert outcome.status == IntegrationProcessingStatus.processed
    assert subscription.billing_status == SubscriberBillingStatus.delinquent
    assert entitlement.status == EntitlementAccessStatus.pending
    assert entitlement.access_starts_at is None
    assert entitlement.paid_through_at is None
    assert entitlement.grace_period_ends_at is None
    assert (
        db_session.query(SubscriptionAccessEvent)
        .filter(
            SubscriptionAccessEvent.external_event_id
            == "evt_initial_failure"
        )
        .one()
        .event_type
        == "stripe_payment_failed"
    )
    assert not entitlement_grants_access(entitlement, now=NOW)


@pytest.mark.parametrize("stripe_status", ["past_due", "unpaid"])
def test_first_seen_delinquent_subscription_remains_denied(
    db_session,
    stripe_status,
):
    _plan(db_session)
    delinquent = _subscription_object(status=stripe_status)

    _process(db_session, _event(data_object=delinquent))

    subscription, entitlement = _created_domain(db_session)
    assert subscription.billing_status == SubscriberBillingStatus.delinquent
    assert entitlement.status == EntitlementAccessStatus.pending
    assert entitlement.access_starts_at is None
    assert entitlement.grace_period_ends_at is None
    assert not entitlement_grants_access(entitlement, now=NOW)


def test_failed_renewal_after_expired_paid_access_enters_grace(db_session):
    _plan(db_session)
    paid_through = NOW - timedelta(hours=1)
    _process(
        db_session,
        _event(data_object=_subscription_object(period_end=paid_through)),
    )
    entitlement = db_session.query(AccessEntitlement).one()
    entitlement.status = EntitlementAccessStatus.expired
    entitlement.expires_at = paid_through
    db_session.commit()

    invoice = {"id": "in_expired_renewal", "subscription": "sub_new"}
    failed_state = _subscription_object(
        status="past_due",
        period_end=NOW + timedelta(days=30),
    )
    _process(
        db_session,
        _event(
            event_id="evt_expired_renewal",
            event_type="invoice.payment_failed",
            data_object=invoice,
        ),
        retrieve_subscription=lambda subscription_id: failed_state,
    )

    db_session.refresh(entitlement)
    assert entitlement.status == EntitlementAccessStatus.grace_period
    assert entitlement.paid_through_at == paid_through
    assert entitlement.grace_period_ends_at == NOW + timedelta(days=3)
    assert entitlement.expires_at is None
    assert entitlement_grants_access(entitlement, now=NOW)


def test_payment_failure_uses_first_failure_plus_three_days_without_unpaid_period(
    db_session,
):
    _plan(db_session)
    paid_through = NOW + timedelta(hours=12)
    active = _subscription_object(period_end=paid_through)
    _process(db_session, _event(data_object=active))

    unpaid_period_end = NOW + timedelta(days=30)
    failed_state = _subscription_object(
        status="past_due",
        period_end=unpaid_period_end,
    )
    invoice = {
        "id": "in_failed",
        "subscription": "sub_new",
        "customer": "cus_new",
    }
    failed_event = _event(
        event_id="evt_failed",
        event_type="invoice.payment_failed",
        created_at=NOW + timedelta(hours=1),
        data_object=invoice,
    )
    _process(
        db_session,
        failed_event,
        retrieve_subscription=lambda subscription_id: failed_state,
        now=NOW + timedelta(hours=1),
    )

    subscription, entitlement = _created_domain(db_session)
    expected_deadline = NOW + timedelta(hours=1, days=3)
    assert subscription.billing_status == SubscriberBillingStatus.delinquent
    assert entitlement.status == EntitlementAccessStatus.grace_period
    assert entitlement.paid_through_at == paid_through
    assert entitlement.grace_period_ends_at == expected_deadline
    assert entitlement.grace_period_ends_at != unpaid_period_end

    repeated = _event(
        event_id="evt_failed_again",
        event_type="invoice.payment_failed",
        created_at=NOW + timedelta(days=1),
        data_object=invoice,
    )
    _process(
        db_session,
        repeated,
        retrieve_subscription=lambda subscription_id: failed_state,
        now=NOW + timedelta(days=1),
    )
    db_session.refresh(entitlement)
    assert entitlement.grace_period_ends_at == expected_deadline


def test_payment_recovery_restores_access_and_clears_grace(db_session):
    _plan(db_session)
    _process(db_session, _event())
    failed = _subscription_object(status="past_due")
    invoice = {"id": "in_1", "subscription": "sub_new"}
    _process(
        db_session,
        _event(
            event_id="evt_failed",
            event_type="invoice.payment_failed",
            created_at=NOW + timedelta(seconds=1),
            data_object=invoice,
        ),
        retrieve_subscription=lambda subscription_id: failed,
        now=NOW + timedelta(seconds=1),
    )

    recovered_end = PERIOD_END + timedelta(days=30)
    recovered = _subscription_object(period_end=recovered_end)
    _process(
        db_session,
        _event(
            event_id="evt_paid",
            event_type="invoice.paid",
            created_at=NOW + timedelta(seconds=2),
            data_object=invoice,
        ),
        retrieve_subscription=lambda subscription_id: recovered,
        now=NOW + timedelta(seconds=2),
    )

    subscription, entitlement = _created_domain(db_session)
    assert subscription.billing_status == SubscriberBillingStatus.active
    assert entitlement.status == EntitlementAccessStatus.active
    assert entitlement.paid_through_at == recovered_end
    assert entitlement.grace_period_ends_at is None
    assert (
        db_session.query(SubscriptionAccessEvent)
        .filter(SubscriptionAccessEvent.external_event_id == "evt_paid")
        .one()
        .event_type
        == "stripe_payment_recovered"
    )


def test_stale_payment_failure_cannot_regress_recovered_state(db_session):
    _plan(db_session)
    latest = NOW + timedelta(minutes=5)
    _process(
        db_session,
        _event(
            event_id="evt_current",
            created_at=latest,
            data_object=_subscription_object(),
        ),
    )
    invoice = {"id": "in_stale", "subscription": "sub_new"}
    _process(
        db_session,
        _event(
            event_id="evt_stale_failure",
            event_type="invoice.payment_failed",
            created_at=NOW,
            data_object=invoice,
        ),
        retrieve_subscription=lambda subscription_id: _subscription_object(),
    )

    subscription, entitlement = _created_domain(db_session)
    assert subscription.billing_status == SubscriberBillingStatus.active
    assert entitlement.status == EntitlementAccessStatus.active
    assert db_session.query(SubscriptionAccessEvent).count() == 1


def test_administrative_revocation_is_never_cleared(db_session):
    _plan(db_session)
    _process(db_session, _event())
    entitlement = db_session.query(AccessEntitlement).one()
    entitlement.administratively_revoked = True
    entitlement.status = EntitlementAccessStatus.revoked
    entitlement.revoked_at = NOW
    db_session.commit()

    _process(
        db_session,
        _event(
            event_id="evt_after_revocation",
            event_type="customer.subscription.updated",
            created_at=NOW + timedelta(seconds=1),
            data_object=_subscription_object(
                period_end=PERIOD_END + timedelta(days=30)
            ),
        ),
    )

    db_session.refresh(entitlement)
    assert entitlement.administratively_revoked
    assert entitlement.status == EntitlementAccessStatus.revoked
    assert not entitlement_grants_access(entitlement, now=NOW + timedelta(seconds=1))


def test_corrected_paid_through_restores_expired_entitlement(db_session):
    _plan(db_session)
    expired_at = NOW - timedelta(days=1)
    _process(
        db_session,
        _event(data_object=_subscription_object(period_end=expired_at)),
    )
    entitlement = db_session.query(AccessEntitlement).one()
    entitlement.status = EntitlementAccessStatus.expired
    entitlement.expires_at = expired_at
    db_session.commit()

    corrected_end = NOW + timedelta(days=10)
    ended_with_paid_access = _subscription_object(
        status="canceled",
        period_end=corrected_end,
        ended_at=NOW,
    )
    _process(
        db_session,
        _event(
            event_id="evt_corrected_paid_through",
            event_type="customer.subscription.deleted",
            created_at=NOW + timedelta(seconds=1),
            data_object=ended_with_paid_access,
        ),
        retrieve_subscription=lambda subscription_id: ended_with_paid_access,
    )

    db_session.refresh(entitlement)
    assert entitlement.status == EntitlementAccessStatus.active
    assert entitlement.paid_through_at == corrected_end
    assert entitlement.expires_at is None
    assert entitlement_grants_access(entitlement, now=NOW)


def test_paid_through_restoration_does_not_override_admin_revocation(db_session):
    _plan(db_session)
    _process(db_session, _event())
    entitlement = db_session.query(AccessEntitlement).one()
    entitlement.administratively_revoked = True
    entitlement.status = EntitlementAccessStatus.revoked
    entitlement.revoked_at = NOW
    entitlement.expires_at = NOW - timedelta(days=1)
    db_session.commit()
    ended = _subscription_object(
        status="canceled",
        period_end=NOW + timedelta(days=10),
        ended_at=NOW,
    )

    _process(
        db_session,
        _event(
            event_id="evt_revoked_paid_through",
            event_type="customer.subscription.deleted",
            created_at=NOW + timedelta(seconds=1),
            data_object=ended,
        ),
        retrieve_subscription=lambda subscription_id: ended,
    )

    db_session.refresh(entitlement)
    assert entitlement.administratively_revoked
    assert entitlement.status == EntitlementAccessStatus.revoked
    assert not entitlement_grants_access(entitlement, now=NOW)


def test_noop_sync_updates_integration_without_misleading_history(db_session):
    _plan(db_session)
    _process(db_session, _event())

    _process(
        db_session,
        _event(
            event_id="evt_noop",
            event_type="customer.subscription.updated",
            created_at=NOW + timedelta(seconds=1),
            data_object=_subscription_object(),
        ),
    )

    assert db_session.query(IntegrationEvent).count() == 2
    assert db_session.query(SubscriptionAccessEvent).count() == 1


def test_history_records_previous_new_states_and_external_event(db_session):
    _plan(db_session)
    _process(db_session, _event())
    history = db_session.query(SubscriptionAccessEvent).one()

    assert history.external_event_id == "evt_created"
    assert history.previous_access_status == "pending"
    assert history.new_access_status == "active"
    assert history.previous_billing_status == "pending"
    assert history.new_billing_status == "active"
    assert history.occurred_at == NOW


@pytest.mark.parametrize(
    ("authoritative_status", "expected_event_type"),
    [
        ("past_due", "stripe_payment_failed"),
        ("incomplete", "stripe_subscription_updated"),
        ("canceled", "stripe_entitlement_expired"),
    ],
)
def test_invoice_paid_history_uses_actual_resulting_transition(
    db_session,
    authoritative_status,
    expected_event_type,
):
    _plan(db_session)
    _process(db_session, _event())
    invoice = {"id": "in_result", "subscription": "sub_new"}
    authoritative = _subscription_object(
        status=authoritative_status,
        period_end=(
            NOW - timedelta(seconds=1)
            if authoritative_status == "canceled"
            else PERIOD_END
        ),
    )

    _process(
        db_session,
        _event(
            event_id=f"evt_paid_{authoritative_status}",
            event_type="invoice.paid",
            created_at=NOW + timedelta(seconds=1),
            data_object=invoice,
        ),
        retrieve_subscription=lambda subscription_id: authoritative,
        now=NOW + timedelta(seconds=1),
    )

    latest = (
        db_session.query(SubscriptionAccessEvent)
        .filter(
            SubscriptionAccessEvent.external_event_id
            == f"evt_paid_{authoritative_status}"
        )
        .one()
    )
    assert latest.event_type == expected_event_type
    assert latest.event_type != "stripe_payment_recovered"
    assert latest.new_billing_status == service.map_stripe_billing_status(
        authoritative_status
    ).value


def test_history_labels_only_the_transition_into_ended_as_subscription_ended(
    db_session,
):
    _plan(db_session)
    ended = _subscription_object(
        status="canceled",
        period_end=PERIOD_END,
        ended_at=NOW,
    )
    _process(db_session, _event(data_object=ended))
    ended_again = _subscription_object(
        status="canceled",
        period_end=PERIOD_END,
        ended_at=NOW + timedelta(seconds=1),
    )
    _process(
        db_session,
        _event(
            event_id="evt_ended_metadata_update",
            event_type="customer.subscription.updated",
            created_at=NOW + timedelta(seconds=1),
            data_object=ended_again,
        ),
        retrieve_subscription=lambda subscription_id: ended_again,
    )

    history = (
        db_session.query(SubscriptionAccessEvent)
        .order_by(SubscriptionAccessEvent.occurred_at)
        .all()
    )
    assert history[0].event_type == "stripe_subscription_ended"
    assert history[1].event_type == "stripe_subscription_updated"


def test_failure_after_subscriber_creation_rolls_back_all_domain_changes(
    monkeypatch,
    db_session,
):
    _plan(db_session)

    def fail_after_creation(*args, **kwargs):
        raise RuntimeError("sk_test_secret_should_be_redacted")

    monkeypatch.setattr(service, "_apply_entitlement_state", fail_after_creation)
    outcome = _process(db_session, _event(event_id="evt_rollback"))
    integration = db_session.query(IntegrationEvent).one()

    assert outcome.status == IntegrationProcessingStatus.retryable_failure
    assert _domain_rows(db_session) == {
        "subscribers": 0,
        "subscriptions": 0,
        "entitlements": 0,
        "history": 0,
    }
    assert "sk_test_secret_should_be_redacted" not in integration.last_error
    assert integration.last_error == "RuntimeError: unexpected processing failure"


def test_retryable_event_attempts_increment_and_same_event_can_succeed(db_session):
    event = _event(event_id="evt_retry")
    first = _process(db_session, event)
    integration = db_session.query(IntegrationEvent).one()

    assert first.retryable
    assert integration.processing_attempts == 1
    assert integration.next_retry_at == NOW + timedelta(seconds=300)

    deferred = _process(db_session, event, now=NOW + timedelta(seconds=30))
    db_session.refresh(integration)
    assert deferred.retryable
    assert integration.processing_attempts == 1

    _plan(db_session)
    second = _process(db_session, event, now=NOW + timedelta(minutes=5))
    db_session.refresh(integration)

    assert second.status == IntegrationProcessingStatus.processed
    assert integration.processing_attempts == 2
    assert integration.processed_at == NOW + timedelta(minutes=5)
    assert integration.next_retry_at is None
    assert db_session.query(SubscriberSubscription).count() == 1


def test_retryable_event_remains_replayable_after_automatic_retry_window(db_session):
    event = _event(event_id="evt_terminal")
    outcome = _process(db_session, event)
    integration = db_session.query(IntegrationEvent).one()

    assert outcome.retryable
    assert outcome.status == IntegrationProcessingStatus.retryable_failure
    assert integration.processing_attempts == 1
    assert integration.processed_at is None
    assert integration.next_retry_at == NOW + timedelta(seconds=300)

    _plan(db_session)
    replayed = service.replay_stripe_integration_event(
        db_session,
        event_id="evt_terminal",
        now=NOW + timedelta(minutes=5),
        retrieve_event=lambda event_id: event,
        retrieve_subscription=lambda subscription_id: event["data"]["object"],
    )
    db_session.refresh(integration)
    assert replayed.status == IntegrationProcessingStatus.processed
    assert integration.processing_attempts == 2
    assert db_session.query(SubscriberSubscription).count() == 1


def test_replay_retrieval_failure_cannot_overwrite_concurrent_completion(
    db_session,
):
    event = _event(event_id="evt_replay_failure_race")
    _process(db_session, event)
    _plan(db_session)
    completed_at = NOW + timedelta(minutes=5)

    def complete_then_fail(event_id):
        completed = service.process_verified_stripe_event(
            db_session,
            event=event,
            payload=_payload(event),
            now=completed_at,
            retrieve_subscription=lambda subscription_id: event["data"]["object"],
        )
        assert completed.status == IntegrationProcessingStatus.processed
        raise service.RetryableStripeEventError("Stripe Event retrieval failed")

    replayed = service.replay_stripe_integration_event(
        db_session,
        event_id=event["id"],
        now=completed_at,
        retrieve_event=complete_then_fail,
    )
    integration = db_session.query(IntegrationEvent).one()

    assert replayed.status == IntegrationProcessingStatus.processed
    assert replayed.duplicate
    assert integration.processing_status == IntegrationProcessingStatus.processed
    assert integration.processing_attempts == 2
    assert integration.processed_at == completed_at
    assert integration.last_error is None
    assert integration.next_retry_at is None
    assert db_session.query(SubscriptionAccessEvent).count() == 1


def test_replay_id_mismatch_cannot_overwrite_concurrent_completion(db_session):
    event = _event(event_id="evt_replay_mismatch_race")
    _process(db_session, event)
    _plan(db_session)
    completed_at = NOW + timedelta(minutes=5)

    def complete_then_return_mismatch(event_id):
        completed = service.process_verified_stripe_event(
            db_session,
            event=event,
            payload=_payload(event),
            now=completed_at,
            retrieve_subscription=lambda subscription_id: event["data"]["object"],
        )
        assert completed.status == IntegrationProcessingStatus.processed
        return _event(event_id="evt_wrong_authoritative_id")

    replayed = service.replay_stripe_integration_event(
        db_session,
        event_id=event["id"],
        now=completed_at,
        retrieve_event=complete_then_return_mismatch,
    )
    integration = db_session.query(IntegrationEvent).one()

    assert replayed.status == IntegrationProcessingStatus.processed
    assert replayed.duplicate
    assert integration.processing_status == IntegrationProcessingStatus.processed
    assert integration.processing_attempts == 2
    assert integration.processed_at == completed_at
    assert integration.last_error is None
    assert integration.next_retry_at is None
    assert db_session.query(SubscriptionAccessEvent).count() == 1


def test_replay_retrieval_failure_updates_only_a_still_replayable_event(db_session):
    event = _event(event_id="evt_replay_failure")
    _process(db_session, event)
    replayed_at = NOW + timedelta(minutes=1)

    def fail_retrieval(event_id):
        raise service.RetryableStripeEventError("Stripe Event retrieval failed")

    replayed = service.replay_stripe_integration_event(
        db_session,
        event_id=event["id"],
        now=replayed_at,
        retrieve_event=fail_retrieval,
    )
    integration = db_session.query(IntegrationEvent).one()

    assert replayed.status == IntegrationProcessingStatus.retryable_failure
    assert integration.processing_status == IntegrationProcessingStatus.retryable_failure
    assert integration.processing_attempts == 2
    assert integration.processed_at is None
    assert integration.next_retry_at is None
    assert "Stripe Event retrieval failed" in integration.last_error


def test_replay_id_mismatch_permanently_fails_only_a_replayable_event(db_session):
    event = _event(event_id="evt_replay_mismatch")
    _process(db_session, event)
    replayed_at = NOW + timedelta(minutes=1)

    replayed = service.replay_stripe_integration_event(
        db_session,
        event_id=event["id"],
        now=replayed_at,
        retrieve_event=lambda event_id: _event(event_id="evt_wrong_id"),
    )
    integration = db_session.query(IntegrationEvent).one()

    assert replayed.status == IntegrationProcessingStatus.permanently_failed
    assert integration.processing_status == IntegrationProcessingStatus.permanently_failed
    assert integration.processing_attempts == 2
    assert integration.processed_at == replayed_at
    assert integration.next_retry_at is None
    assert "does not match" in integration.last_error


def test_transient_stripe_failure_can_later_succeed(db_session):
    _plan(db_session)
    event = _event(event_id="evt_transient")

    def transient_failure(subscription_id):
        raise service.RetryableStripeEventError("Temporary Stripe API failure")

    first = _process(
        db_session,
        event,
        retrieve_subscription=transient_failure,
    )
    second = _process(
        db_session,
        event,
        retrieve_subscription=lambda subscription_id: event["data"]["object"],
        now=NOW + timedelta(seconds=300),
    )

    integration = db_session.query(IntegrationEvent).one()
    assert first.status == IntegrationProcessingStatus.retryable_failure
    assert second.status == IntegrationProcessingStatus.processed
    assert integration.processing_attempts == 2


def test_permanently_invalid_event_cannot_be_replayed(db_session):
    _plan(db_session)
    event = _event(
        event_id="evt_permanent",
        data_object=_subscription_object(customer_id=" "),
    )
    first = _process(db_session, event)
    retrievals = []

    replay = service.replay_stripe_integration_event(
        db_session,
        event_id="evt_permanent",
        now=NOW + timedelta(minutes=1),
        retrieve_event=lambda event_id: retrievals.append(event_id),
    )

    assert first.status == IntegrationProcessingStatus.permanently_failed
    assert replay.status == IntegrationProcessingStatus.permanently_failed
    assert retrievals == []


def test_processed_event_internal_replay_remains_idempotent(db_session):
    _plan(db_session)
    event = _event(event_id="evt_processed_replay")
    _process(db_session, event)
    retrievals = []

    replay = service.replay_stripe_integration_event(
        db_session,
        event_id="evt_processed_replay",
        now=NOW + timedelta(minutes=1),
        retrieve_event=lambda event_id: retrievals.append(event_id),
    )

    assert replay.status == IntegrationProcessingStatus.processed
    assert replay.duplicate
    assert retrievals == []
    assert db_session.query(SubscriptionAccessEvent).count() == 1


def test_ignored_event_internal_replay_remains_terminal(db_session):
    event = _event(
        event_id="evt_ignored_replay",
        event_type="charge.succeeded",
        data_object={"id": "ch_ignored"},
    )
    _process(db_session, event)
    integration = db_session.query(IntegrationEvent).one()
    original = (
        integration.processing_attempts,
        integration.processed_at,
        integration.last_error,
        integration.next_retry_at,
    )
    retrievals = []

    replayed = service.replay_stripe_integration_event(
        db_session,
        event_id=event["id"],
        now=NOW + timedelta(minutes=1),
        retrieve_event=lambda event_id: retrievals.append(event_id),
    )
    db_session.refresh(integration)

    assert replayed.status == IntegrationProcessingStatus.ignored
    assert replayed.duplicate
    assert retrievals == []
    assert (
        integration.processing_attempts,
        integration.processed_at,
        integration.last_error,
        integration.next_retry_at,
    ) == original


def test_invalid_customer_id_is_permanent_and_never_grants_access(db_session):
    _plan(db_session)
    invalid = _subscription_object(customer_id=" ")
    outcome = _process(db_session, _event(data_object=invalid))

    assert outcome.status == IntegrationProcessingStatus.permanently_failed
    assert db_session.query(Subscriber).count() == 0
    assert db_session.query(AccessEntitlement).count() == 0


class FakeRequest:
    def __init__(self, payload: bytes, signature: str | None):
        self._payload = payload
        self.headers = {}
        if signature is not None:
            self.headers["stripe-signature"] = signature

    async def body(self):
        return self._payload


def _signature(payload: bytes, secret: str, timestamp: int) -> str:
    signed = f"{timestamp}.{payload.decode()}".encode()
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _deliver_signed_webhook(
    monkeypatch,
    db_session,
    event,
    *,
    authoritative_subscription=None,
):
    secret = "whsec_phase_4_delivery"
    payload = _payload(event)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(stripe_router, "WEBHOOK_SECRET", secret)
    if authoritative_subscription is not None:
        monkeypatch.setattr(
            service,
            "retrieve_stripe_subscription",
            lambda subscription_id: authoritative_subscription,
        )
    return asyncio.run(
        stripe_router.stripe_webhook(
            FakeRequest(payload, _signature(payload, secret, timestamp)),
            db_session,
        )
    )


def test_webhook_valid_signature_ingests_new_subscription(monkeypatch, db_session):
    _plan(db_session)
    secret = "whsec_phase_4"
    event = _event()
    payload = _payload(event)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(stripe_router, "WEBHOOK_SECRET", secret)
    monkeypatch.setattr(
        service,
        "retrieve_stripe_subscription",
        lambda subscription_id: event["data"]["object"],
    )

    response = asyncio.run(
        stripe_router.stripe_webhook(
            FakeRequest(payload, _signature(payload, secret, timestamp)),
            db_session,
        )
    )

    assert response == {"status": "ok"}
    assert db_session.query(SubscriberSubscription).count() == 1
    assert db_session.query(Subscription).count() == 0


def test_webhook_malformed_signed_payload_is_rejected_before_persistence(
    monkeypatch,
    db_session,
):
    secret = "whsec_phase_4"
    payload = b'{"not-valid-json"'
    timestamp = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(stripe_router, "WEBHOOK_SECRET", secret)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            stripe_router.stripe_webhook(
                FakeRequest(payload, _signature(payload, secret, timestamp)),
                db_session,
            )
        )

    assert exc_info.value.status_code == 400
    assert db_session.query(IntegrationEvent).count() == 0


def test_webhook_retryable_failure_returns_500_for_stripe_redelivery(
    monkeypatch,
    db_session,
):
    secret = "whsec_phase_4"
    event = _event(event_id="evt_needs_plan")
    payload = _payload(event)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(stripe_router, "WEBHOOK_SECRET", secret)
    monkeypatch.setattr(
        service,
        "retrieve_stripe_subscription",
        lambda subscription_id: event["data"]["object"],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            stripe_router.stripe_webhook(
                FakeRequest(payload, _signature(payload, secret, timestamp)),
                db_session,
            )
        )

    assert exc_info.value.status_code == 500
    assert (
        db_session.query(IntegrationEvent).one().processing_status
        == IntegrationProcessingStatus.retryable_failure
    )


def test_same_email_new_customer_stays_in_accountless_domain(
    monkeypatch,
    db_session,
):
    legacy_user = User(
        email="shared@example.com",
        hashed_password="unused",
        is_active=False,
    )
    db_session.add(legacy_user)
    db_session.commit()
    _plan(db_session)
    accountless = _subscription_object(
        customer_id="cus_accountless",
        email="shared@example.com",
    )
    event = _event(event_id="evt_shared_email", data_object=accountless)

    response = _deliver_signed_webhook(
        monkeypatch,
        db_session,
        event,
        authoritative_subscription=accountless,
    )

    db_session.refresh(legacy_user)
    assert response == {"status": "ok"}
    assert db_session.query(Subscriber).one().stripe_customer_id == "cus_accountless"
    assert not legacy_user.is_active
    assert db_session.query(Subscription).count() == 0


def test_same_email_accountless_checkout_does_not_activate_legacy_user(
    monkeypatch,
    db_session,
):
    legacy_user = User(
        email="checkout-shared@example.com",
        hashed_password="unused",
        is_active=False,
    )
    db_session.add(legacy_user)
    db_session.commit()
    _plan(db_session)
    checkout = {
        "id": "cs_accountless",
        "mode": "subscription",
        "customer": "cus_checkout_new",
        "customer_details": {"email": "checkout-shared@example.com"},
        "subscription": "sub_checkout_new",
    }
    authoritative = _subscription_object(
        subscription_id="sub_checkout_new",
        customer_id="cus_checkout_new",
        email="checkout-shared@example.com",
    )

    response = _deliver_signed_webhook(
        monkeypatch,
        db_session,
        _event(
            event_id="evt_checkout_shared_email",
            event_type="checkout.session.completed",
            data_object=checkout,
        ),
        authoritative_subscription=authoritative,
    )

    db_session.refresh(legacy_user)
    assert response == {"status": "ok"}
    assert db_session.query(Subscriber).one().stripe_email == (
        "checkout-shared@example.com"
    )
    assert not legacy_user.is_active
    assert db_session.query(Subscription).count() == 0


def test_customer_id_collision_without_legacy_identity_stays_accountless(
    monkeypatch,
    db_session,
):
    legacy_user = User(
        email="legacy-customer@example.com",
        hashed_password="unused",
        is_active=False,
    )
    db_session.add(legacy_user)
    db_session.flush()
    legacy_subscription = Subscription(
        user_id=legacy_user.id,
        stripe_customer_id="cus_shared",
        stripe_subscription_id="sub_legacy_existing",
        status=SubscriptionStatus.pending,
    )
    db_session.add(legacy_subscription)
    db_session.commit()
    _plan(db_session)
    accountless = _subscription_object(
        subscription_id="sub_accountless_new",
        customer_id="cus_shared",
        email="new-contact@example.com",
    )

    response = _deliver_signed_webhook(
        monkeypatch,
        db_session,
        _event(event_id="evt_customer_collision", data_object=accountless),
        authoritative_subscription=accountless,
    )

    db_session.refresh(legacy_subscription)
    db_session.refresh(legacy_user)
    assert response == {"status": "ok"}
    assert db_session.query(Subscriber).one().stripe_customer_id == "cus_shared"
    assert legacy_subscription.stripe_subscription_id == "sub_legacy_existing"
    assert legacy_subscription.status == SubscriptionStatus.pending
    assert not legacy_user.is_active


@pytest.mark.parametrize(
    ("field_location", "unverified_value"),
    [
        ("metadata_user_id", "unknown-legacy-user"),
        ("metadata_user_id", {"unexpected": "format"}),
        ("metadata_user_id", "   "),
        ("metadata_client_reference_id", "unknown-client-reference"),
        ("client_reference_id", {"unexpected": "format"}),
        ("client_reference_id", " \t "),
    ],
    ids=[
        "unknown-metadata-user",
        "malformed-metadata-user",
        "whitespace-metadata-user",
        "unknown-metadata-client-reference",
        "malformed-client-reference",
        "whitespace-client-reference",
    ],
)
def test_unverified_legacy_shaped_metadata_remains_accountless(
    monkeypatch,
    db_session,
    field_location,
    unverified_value,
):
    _plan(db_session)
    accountless = _subscription_object()
    if field_location == "metadata_user_id":
        accountless["metadata"]["user_id"] = unverified_value
    elif field_location == "metadata_client_reference_id":
        accountless["metadata"]["client_reference_id"] = unverified_value
    else:
        accountless["client_reference_id"] = unverified_value

    response = _deliver_signed_webhook(
        monkeypatch,
        db_session,
        _event(
            event_id=f"evt_{field_location}",
            data_object=accountless,
        ),
        authoritative_subscription=accountless,
    )

    assert response == {"status": "ok"}
    assert _domain_rows(db_session) == {
        "subscribers": 1,
        "subscriptions": 1,
        "entitlements": 1,
        "history": 1,
    }
    assert (
        db_session.query(IntegrationEvent).one().processing_status
        == IntegrationProcessingStatus.processed
    )


def test_existing_legacy_subscription_id_is_not_routed_to_legacy_handler(
    monkeypatch,
    db_session,
):
    _plan(db_session)
    legacy_user = User(
        email="existing-legacy@example.com",
        hashed_password="unused",
        is_active=False,
    )
    db_session.add(legacy_user)
    db_session.flush()
    legacy_subscription = Subscription(
        user_id=legacy_user.id,
        stripe_customer_id="cus_existing_legacy",
        stripe_subscription_id="sub_existing_legacy",
        status=SubscriptionStatus.pending,
    )
    db_session.add(legacy_subscription)
    db_session.commit()
    event_object = _subscription_object(
        subscription_id="sub_existing_legacy",
        customer_id="cus_existing_legacy",
        email="unrelated@example.com",
    )
    event_object["metadata"]["user_id"] = "unknown-user-must-not-mask-subscription"

    response = _deliver_signed_webhook(
        monkeypatch,
        db_session,
        _event(
            event_id="evt_existing_legacy_subscription",
            event_type="customer.subscription.updated",
            data_object=event_object,
        ),
        authoritative_subscription=event_object,
    )

    db_session.refresh(legacy_subscription)
    db_session.refresh(legacy_user)
    assert response == {"status": "ok"}
    assert legacy_subscription.status == SubscriptionStatus.pending
    assert not legacy_user.is_active
    assert db_session.query(Subscriber).count() == 1
    assert db_session.query(SubscriberSubscription).count() == 1


def test_legacy_user_metadata_is_ignored_by_accountless_webhook(
    monkeypatch,
    db_session,
):
    _plan(db_session)
    user = User(
        email="legacy@example.com",
        hashed_password="unused",
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()

    secret = "whsec_phase_4"
    legacy_subscription = _subscription_object(
        subscription_id="sub_legacy",
        customer_id="cus_legacy",
        email="legacy@example.com",
    )
    legacy_subscription["metadata"]["user_id"] = user.id
    event = _event(
        event_id="evt_legacy",
        data_object=legacy_subscription,
    )
    payload = _payload(event)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(stripe_router, "WEBHOOK_SECRET", secret)
    monkeypatch.setattr(
        service,
        "retrieve_stripe_subscription",
        lambda subscription_id: legacy_subscription,
    )

    response = asyncio.run(
        stripe_router.stripe_webhook(
            FakeRequest(payload, _signature(payload, secret, timestamp)),
            db_session,
        )
    )

    db_session.refresh(user)
    assert response == {"status": "ok"}
    assert not user.is_active
    assert db_session.query(Subscription).count() == 0
    assert db_session.query(Subscriber).count() == 1
    assert (
        db_session.query(IntegrationEvent).one().processing_status
        == IntegrationProcessingStatus.processed
    )


def test_postgresql_subscription_lock_targets_only_subscription_table(db_session):
    query = service._existing_subscription_lock_query(db_session, "sub_lock")
    compiled = str(query.statement.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE" in compiled
    assert "JOIN" not in compiled
    assert "subscriber_subscriptions" in compiled


def test_normal_sqlite_engine_connections_enable_foreign_keys():
    sqlite_engine = create_engine("sqlite:///:memory:")
    assert configure_sqlite_foreign_keys(sqlite_engine)
    assert configure_sqlite_foreign_keys(sqlite_engine)

    with sqlite_engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

    sqlite_engine.dispose()


def test_runtime_sqlite_foreign_keys_reject_inconsistent_subscriber_rows(db_session):
    db_session.add(
        SubscriberSubscription(
            subscriber_id="missing-subscriber",
            plan_id="missing-plan",
            stripe_subscription_id="sub_runtime_fk",
            billing_status=SubscriberBillingStatus.pending,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_postgresql_engine_path_does_not_register_sqlite_listener():
    fake_postgresql_engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql")
    )

    assert not configure_sqlite_foreign_keys(fake_postgresql_engine)
    assert not hasattr(
        fake_postgresql_engine,
        "_auroratio_sqlite_fk_configured",
    )


def test_service_has_no_external_fulfillment_or_trading_dependencies():
    source = service.__file__
    with open(source, encoding="utf-8") as handle:
        content = handle.read()

    forbidden = (
        "telegram",
        "brevo",
        "snaptrade",
        "ibkr",
        "fa_service",
        "trade_service",
        "signal",
    )
    assert not any(token in content.lower() for token in forbidden)


def test_failed_renewal_does_not_treat_unpaid_period_as_paid(db_session):
    _plan(db_session)

    # Initial paid period.
    _process(db_session, _event())

    subscription, entitlement = _created_domain(db_session)

    previous_paid_through = entitlement.paid_through_at

    # Renewal begins at the previous paid-through boundary,
    # but its invoice fails.
    failed_period_end = previous_paid_through + timedelta(days=30)

    failed_subscription = _subscription_object(
        status="past_due",
        period_start=previous_paid_through,
        period_end=failed_period_end,
    )

    _process(
        db_session,
        _event(
            event_id="evt_failed_renewal",
            event_type="invoice.payment_failed",
            created_at=previous_paid_through,
            data_object={
                "id": "in_failed_renewal",
                "subscription": "sub_new",
            },
        ),
        retrieve_subscription=lambda subscription_id: failed_subscription,
        now=previous_paid_through,
    )

    db_session.refresh(entitlement)

    assert entitlement.paid_through_at == previous_paid_through
    assert entitlement.grace_period_ends_at == (
        previous_paid_through + timedelta(days=3)
    )
    assert entitlement.status == EntitlementAccessStatus.grace_period