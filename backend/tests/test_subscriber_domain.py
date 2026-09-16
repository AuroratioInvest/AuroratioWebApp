from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from models import MembershipLevel, Subscription, User
from services.subscriber_domain import (
    append_audit_event,
    append_subscription_access_event,
    entitlement_grants_access,
    normalize_subscriber_email,
)
from subscriber_models import (
    AccessEntitlement,
    AuditActorType,
    AuditEvent,
    EntitlementAccessStatus,
    IntegrationEvent,
    IntegrationProcessingStatus,
    IntegrationProvider,
    PlanChannelMapping,
    Subscriber,
    SubscriberBillingStatus,
    SubscriberSubscription,
    SubscriptionAccessEvent,
    SubscriptionEventSource,
    SubscriptionPlan,
    TelegramChannel,
)


NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


def _plan(db_session, *, code: str = "launch") -> SubscriptionPlan:
    plan = SubscriptionPlan(
        code=code,
        display_name_en="Launch",
        display_name_fr="Lancement",
        stripe_price_id=f"price_{code}",
    )
    db_session.add(plan)
    db_session.flush()
    return plan


def _subscriber(
    db_session,
    *,
    customer_id: str = "cus_new",
    email: str = "Subscriber@Example.com",
) -> Subscriber:
    subscriber = Subscriber(
        stripe_customer_id=customer_id,
        stripe_email=email,
        normalized_email=normalize_subscriber_email(email),
    )
    db_session.add(subscriber)
    db_session.flush()
    return subscriber


def _subscription(
    db_session,
    subscriber: Subscriber,
    plan: SubscriptionPlan,
    *,
    subscription_id: str = "sub_new",
    billing_status: SubscriberBillingStatus = SubscriberBillingStatus.active,
) -> SubscriberSubscription:
    subscription = SubscriberSubscription(
        subscriber_id=subscriber.id,
        plan_id=plan.id,
        stripe_subscription_id=subscription_id,
        stripe_status=billing_status.value,
        billing_status=billing_status,
    )
    db_session.add(subscription)
    db_session.flush()
    return subscription


def _entitlement(
    *,
    status: EntitlementAccessStatus = EntitlementAccessStatus.active,
    starts_at: datetime | None = NOW - timedelta(days=1),
    paid_through: datetime | None = NOW + timedelta(days=1),
    grace_ends: datetime | None = None,
    revoked: bool = False,
    expires_at: datetime | None = None,
) -> AccessEntitlement:
    return AccessEntitlement(
        status=status,
        access_starts_at=starts_at,
        paid_through_at=paid_through,
        grace_period_ends_at=grace_ends,
        administratively_revoked=revoked,
        expires_at=expires_at,
    )


def _persist_entitlement(
    db_session,
    subscriber: Subscriber,
    subscription: SubscriberSubscription,
    plan: SubscriptionPlan,
    **values,
) -> AccessEntitlement:
    entitlement = AccessEntitlement(
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        plan_id=plan.id,
        status=values.pop("status", EntitlementAccessStatus.active),
        access_starts_at=values.pop("access_starts_at", NOW - timedelta(days=1)),
        paid_through_at=values.pop("paid_through_at", NOW + timedelta(days=1)),
        **values,
    )
    db_session.add(entitlement)
    db_session.flush()
    return entitlement


def test_duplicate_stripe_customer_id_is_rejected(db_session):
    db_session.add_all(
        [
            Subscriber(stripe_customer_id="cus_duplicate"),
            Subscriber(stripe_customer_id="cus_duplicate"),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_stripe_subscription_id_is_rejected(db_session):
    plan = _plan(db_session)
    first = _subscriber(db_session, customer_id="cus_first")
    second = _subscriber(db_session, customer_id="cus_second")
    db_session.add_all(
        [
            SubscriberSubscription(
                subscriber_id=first.id,
                plan_id=plan.id,
                stripe_subscription_id="sub_duplicate",
                billing_status=SubscriberBillingStatus.active,
            ),
            SubscriberSubscription(
                subscriber_id=second.id,
                plan_id=plan.id,
                stripe_subscription_id="sub_duplicate",
                billing_status=SubscriberBillingStatus.active,
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_integration_event_provider_idempotency_is_enforced(db_session):
    db_session.add_all(
        [
            IntegrationEvent(
                provider=IntegrationProvider.stripe,
                external_event_id="evt_duplicate",
                event_type="invoice.paid",
            ),
            IntegrationEvent(
                provider=IntegrationProvider.stripe,
                external_event_id="evt_duplicate",
                event_type="invoice.paid",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_normalized_email_can_belong_to_different_customers(db_session):
    db_session.add_all(
        [
            Subscriber(
                stripe_customer_id="cus_one",
                stripe_email="Same@Example.com",
                normalized_email="same@example.com",
            ),
            Subscriber(
                stripe_customer_id="cus_two",
                stripe_email="same@example.com",
                normalized_email="same@example.com",
            ),
        ]
    )
    db_session.commit()
    assert db_session.query(Subscriber).count() == 2


def test_duplicate_plan_channel_mapping_is_rejected(db_session):
    plan = _plan(db_session)
    channel = TelegramChannel(
        code="signals",
        display_name_en="Signals",
        display_name_fr="Signaux",
    )
    db_session.add(channel)
    db_session.flush()
    db_session.add_all(
        [
            PlanChannelMapping(plan_id=plan.id, channel_id=channel.id),
            PlanChannelMapping(plan_id=plan.id, channel_id=channel.id),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_new_domain_foreign_keys_are_enforced(db_session):
    db_session.add(
        SubscriberSubscription(
            subscriber_id="missing-subscriber",
            plan_id="missing-plan",
            stripe_subscription_id="sub_orphan",
            billing_status=SubscriberBillingStatus.pending,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_entitlement_subscriber_must_match_subscription(db_session):
    plan = _plan(db_session)
    owner = _subscriber(db_session, customer_id="cus_owner")
    other = _subscriber(db_session, customer_id="cus_other")
    subscription = _subscription(db_session, owner, plan)
    db_session.commit()

    db_session.add(
        AccessEntitlement(
            subscriber_id=other.id,
            subscriber_subscription_id=subscription.id,
            plan_id=plan.id,
            status=EntitlementAccessStatus.pending,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_entitlement_plan_must_match_subscription(db_session):
    first_plan = _plan(db_session, code="first")
    second_plan = _plan(db_session, code="second")
    subscriber = _subscriber(db_session)
    subscription = _subscription(db_session, subscriber, first_plan)
    db_session.commit()

    db_session.add(
        AccessEntitlement(
            subscriber_id=subscriber.id,
            subscriber_subscription_id=subscription.id,
            plan_id=second_plan.id,
            status=EntitlementAccessStatus.pending,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_access_event_subscription_must_belong_to_subscriber(db_session):
    plan = _plan(db_session)
    owner = _subscriber(db_session, customer_id="cus_event_owner")
    other = _subscriber(db_session, customer_id="cus_event_other")
    subscription = _subscription(db_session, owner, plan)
    db_session.commit()

    db_session.add(
        SubscriptionAccessEvent(
            subscriber_id=other.id,
            subscriber_subscription_id=subscription.id,
            event_type="mismatched_subscription",
            source=SubscriptionEventSource.system,
            occurred_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_access_event_entitlement_must_match_subscriber(db_session):
    plan = _plan(db_session)
    first = _subscriber(db_session, customer_id="cus_entitlement_first")
    second = _subscriber(db_session, customer_id="cus_entitlement_second")
    first_subscription = _subscription(
        db_session,
        first,
        plan,
        subscription_id="sub_entitlement_first",
    )
    second_subscription = _subscription(
        db_session,
        second,
        plan,
        subscription_id="sub_entitlement_second",
    )
    entitlement = _persist_entitlement(
        db_session,
        first,
        first_subscription,
        plan,
    )
    db_session.commit()

    db_session.add(
        SubscriptionAccessEvent(
            subscriber_id=second.id,
            subscriber_subscription_id=second_subscription.id,
            entitlement_id=entitlement.id,
            event_type="mismatched_entitlement_subscriber",
            source=SubscriptionEventSource.system,
            occurred_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_access_event_entitlement_must_match_subscription(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    first_subscription = _subscription(
        db_session,
        subscriber,
        plan,
        subscription_id="sub_event_first",
    )
    second_subscription = _subscription(
        db_session,
        subscriber,
        plan,
        subscription_id="sub_event_second",
    )
    entitlement = _persist_entitlement(
        db_session,
        subscriber,
        first_subscription,
        plan,
    )
    db_session.commit()

    db_session.add(
        SubscriptionAccessEvent(
            subscriber_id=subscriber.id,
            subscriber_subscription_id=second_subscription.id,
            entitlement_id=entitlement.id,
            event_type="mismatched_entitlement_subscription",
            source=SubscriptionEventSource.system,
            occurred_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_entitlement_event_requires_subscription_id(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    subscription = _subscription(db_session, subscriber, plan)
    entitlement = _persist_entitlement(
        db_session,
        subscriber,
        subscription,
        plan,
    )
    db_session.commit()

    db_session.add(
        SubscriptionAccessEvent(
            subscriber_id=subscriber.id,
            entitlement_id=entitlement.id,
            event_type="missing_subscription",
            source=SubscriptionEventSource.system,
            occurred_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_only_one_entitlement_per_subscription_across_sessions(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    subscription = _subscription(db_session, subscriber, plan)
    _persist_entitlement(db_session, subscriber, subscription, plan)
    db_session.commit()

    other_session = Session(bind=db_session.get_bind())
    try:
        other_session.add(
            AccessEntitlement(
                subscriber_id=subscriber.id,
                subscriber_subscription_id=subscription.id,
                plan_id=plan.id,
                status=EntitlementAccessStatus.pending,
            )
        )
        with pytest.raises(IntegrityError):
            other_session.commit()
    finally:
        other_session.rollback()
        other_session.close()


def test_separate_subscriptions_for_same_plan_each_have_entitlement(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    first = _subscription(
        db_session,
        subscriber,
        plan,
        subscription_id="sub_parallel_one",
    )
    second = _subscription(
        db_session,
        subscriber,
        plan,
        subscription_id="sub_parallel_two",
    )
    _persist_entitlement(db_session, subscriber, first, plan)
    _persist_entitlement(db_session, subscriber, second, plan)
    db_session.commit()
    assert db_session.query(AccessEntitlement).count() == 2


@pytest.mark.parametrize("value", ["", "   "])
def test_plan_code_rejects_empty_values(db_session, value):
    db_session.add(
        SubscriptionPlan(
            code=value,
            display_name_en="Invalid",
            display_name_fr="Invalide",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("value", ["", "   "])
def test_plan_stripe_price_rejects_empty_values(db_session, value):
    db_session.add(
        SubscriptionPlan(
            code=f"price-{len(value)}",
            display_name_en="Invalid",
            display_name_fr="Invalide",
            stripe_price_id=value,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("value", ["", "   "])
def test_channel_code_rejects_empty_values(db_session, value):
    db_session.add(
        TelegramChannel(
            code=value,
            display_name_en="Invalid",
            display_name_fr="Invalide",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("value", ["", "   "])
def test_stripe_customer_id_rejects_empty_values(db_session, value):
    db_session.add(Subscriber(stripe_customer_id=value))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("value", ["", "   "])
def test_stripe_subscription_id_rejects_empty_values(db_session, value):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    db_session.add(
        SubscriberSubscription(
            subscriber_id=subscriber.id,
            plan_id=plan.id,
            stripe_subscription_id=value,
            billing_status=SubscriberBillingStatus.pending,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("value", ["", "   "])
def test_integration_external_event_id_rejects_empty_values(db_session, value):
    db_session.add(
        IntegrationEvent(
            provider=IntegrationProvider.stripe,
            external_event_id=value,
            event_type="test.event",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("value", ["", "   "])
def test_normalized_email_rejects_empty_values(db_session, value):
    db_session.add(
        Subscriber(
            stripe_customer_id=f"cus_email_{len(value)}",
            normalized_email=value,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_nullable_identifiers_and_email_accept_null(db_session):
    plan = SubscriptionPlan(
        code="nullable-plan",
        display_name_en="Nullable",
        display_name_fr="Nullable",
        stripe_price_id=None,
    )
    channel = TelegramChannel(
        code="nullable-channel",
        display_name_en="Nullable",
        display_name_fr="Nullable",
        telegram_chat_id=None,
    )
    subscriber = Subscriber(
        stripe_customer_id="cus_nullable",
        normalized_email=None,
    )
    db_session.add_all([plan, channel, subscriber])
    db_session.commit()


def test_active_entitlement_grants_access_within_paid_through():
    assert entitlement_grants_access(_entitlement(), now=NOW) is True


def test_cancelled_billing_can_retain_paid_through_access():
    subscription = SubscriberSubscription(
        billing_status=SubscriberBillingStatus.cancelled,
        cancel_at_period_end=True,
        current_period_end=NOW + timedelta(days=1),
    )
    entitlement = _entitlement(paid_through=subscription.current_period_end)
    assert entitlement_grants_access(entitlement, now=NOW) is True


def test_grace_period_access_ends_at_deadline():
    entitlement = _entitlement(
        status=EntitlementAccessStatus.grace_period,
        paid_through=None,
        grace_ends=NOW + timedelta(hours=1),
    )
    assert entitlement_grants_access(entitlement, now=NOW) is True
    assert (
        entitlement_grants_access(
            entitlement,
            now=NOW + timedelta(hours=1, microseconds=1),
        )
        is False
    )


@pytest.mark.parametrize(
    "entitlement",
    [
        _entitlement(status=EntitlementAccessStatus.expired),
        _entitlement(status=EntitlementAccessStatus.suspended),
        _entitlement(status=EntitlementAccessStatus.pending),
        _entitlement(paid_through=None),
        _entitlement(starts_at=None),
        _entitlement(starts_at=datetime(2026, 7, 26, 12, 0)),
    ],
)
def test_non_access_and_invalid_date_states_fail_safely(entitlement):
    assert entitlement_grants_access(entitlement, now=NOW) is False


def test_administrative_revocation_always_denies_access():
    entitlement = _entitlement(revoked=True)
    assert entitlement_grants_access(entitlement, now=NOW) is False


def test_helper_requires_explicit_valid_utc_now():
    entitlement = _entitlement()
    assert (
        entitlement_grants_access(
            entitlement,
            now=datetime(2026, 7, 27, 12, 0),
        )
        is False
    )


def test_non_utc_values_persist_and_reload_as_utc(db_session):
    offset = timezone(timedelta(hours=5, minutes=30))
    starts_at = datetime(2026, 7, 27, 17, 30, tzinfo=offset)
    paid_through = datetime(2026, 7, 28, 17, 30, tzinfo=offset)
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    subscription = _subscription(db_session, subscriber, plan)
    entitlement = _persist_entitlement(
        db_session,
        subscriber,
        subscription,
        plan,
        access_starts_at=starts_at,
        paid_through_at=paid_through,
    )
    db_session.commit()
    entitlement_id = entitlement.id
    db_session.expire_all()

    reloaded = db_session.get(AccessEntitlement, entitlement_id)
    assert reloaded.access_starts_at == NOW
    assert reloaded.access_starts_at.tzinfo == timezone.utc
    assert reloaded.paid_through_at == NOW + timedelta(days=1)
    assert entitlement_grants_access(reloaded, now=starts_at) is True


def test_sqlite_round_trip_preserves_valid_entitlement_access(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    subscription = _subscription(db_session, subscriber, plan)
    entitlement = _persist_entitlement(
        db_session,
        subscriber,
        subscription,
        plan,
    )
    db_session.commit()
    entitlement_id = entitlement.id
    db_session.expire_all()

    reloaded = db_session.get(AccessEntitlement, entitlement_id)
    assert reloaded.access_starts_at.tzinfo == timezone.utc
    assert entitlement_grants_access(reloaded, now=NOW) is True


def test_naive_timestamp_is_rejected_during_persistence(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    subscription = _subscription(db_session, subscriber, plan)
    db_session.add(
        AccessEntitlement(
            subscriber_id=subscriber.id,
            subscriber_subscription_id=subscription.id,
            plan_id=plan.id,
            status=EntitlementAccessStatus.active,
            access_starts_at=datetime(2026, 7, 27, 12, 0),
            paid_through_at=NOW + timedelta(days=1),
        )
    )
    with pytest.raises(StatementError):
        db_session.commit()


def test_naive_explicit_expiration_fails_closed():
    entitlement = _entitlement(expires_at=datetime(2026, 7, 28, 12, 0))
    assert entitlement_grants_access(entitlement, now=NOW) is False


def test_entitlement_deadline_boundaries_are_inclusive():
    active = _entitlement(starts_at=NOW, paid_through=NOW, expires_at=NOW)
    grace = _entitlement(
        status=EntitlementAccessStatus.grace_period,
        starts_at=NOW,
        paid_through=None,
        grace_ends=NOW,
        expires_at=NOW,
    )
    assert entitlement_grants_access(active, now=NOW) is True
    assert entitlement_grants_access(grace, now=NOW) is True
    assert (
        entitlement_grants_access(
            active,
            now=NOW + timedelta(microseconds=1),
        )
        is False
    )
    assert (
        entitlement_grants_access(
            grace,
            now=NOW + timedelta(microseconds=1),
        )
        is False
    )


def test_non_utc_aware_now_is_normalized():
    eastern = timezone(timedelta(hours=-4))
    equivalent_now = datetime(2026, 7, 27, 8, 0, tzinfo=eastern)
    assert entitlement_grants_access(_entitlement(), now=equivalent_now) is True


def test_subscriber_is_independent_from_legacy_user(db_session):
    subscriber = _subscriber(db_session)
    db_session.commit()
    assert db_session.query(Subscriber).filter_by(id=subscriber.id).one()
    assert db_session.query(User).count() == 0


def test_legacy_user_activity_does_not_influence_entitlement(db_session):
    legacy_user = User(
        email="inactive@example.com",
        hashed_password="hash",
        membership_level=MembershipLevel.classic,
        is_active=False,
    )
    db_session.add(legacy_user)
    db_session.commit()
    assert legacy_user.is_active is False
    assert entitlement_grants_access(_entitlement(), now=NOW) is True


def test_new_and_legacy_stripe_records_coexist_without_collision(db_session):
    legacy_user = User(
        email="legacy@example.com",
        hashed_password="hash",
        membership_level=MembershipLevel.classic,
    )
    db_session.add(legacy_user)
    db_session.flush()
    db_session.add(
        Subscription(
            user_id=legacy_user.id,
            stripe_customer_id="cus_shared",
            stripe_subscription_id="sub_shared",
        )
    )
    plan = _plan(db_session)
    subscriber = _subscriber(db_session, customer_id="cus_shared")
    _subscription(
        db_session,
        subscriber,
        plan,
        subscription_id="sub_shared",
    )
    db_session.commit()
    assert db_session.query(Subscription).count() == 1
    assert db_session.query(SubscriberSubscription).count() == 1


def test_access_and_audit_history_helpers_only_append(db_session):
    plan = _plan(db_session)
    subscriber = _subscriber(db_session)
    subscription = _subscription(db_session, subscriber, plan)
    entitlement = AccessEntitlement(
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        plan_id=plan.id,
        status=EntitlementAccessStatus.active,
        access_starts_at=NOW,
        paid_through_at=NOW + timedelta(days=30),
    )
    db_session.add(entitlement)
    db_session.flush()

    first = SubscriptionAccessEvent(
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        entitlement_id=entitlement.id,
        event_type="access_activated",
        new_access_status="active",
        source=SubscriptionEventSource.system,
        occurred_at=NOW,
    )
    second = SubscriptionAccessEvent(
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        entitlement_id=entitlement.id,
        event_type="access_reviewed",
        previous_access_status="active",
        new_access_status="active",
        source=SubscriptionEventSource.admin,
        occurred_at=NOW + timedelta(minutes=1),
    )
    audit = AuditEvent(
        actor_type=AuditActorType.system,
        action="entitlement.created",
        entity_type="access_entitlement",
        entity_id=entitlement.id,
        event_metadata={"source": "test"},
    )
    append_subscription_access_event(db_session, first)
    append_subscription_access_event(db_session, second)
    append_audit_event(db_session, audit)
    db_session.commit()

    events = (
        db_session.query(SubscriptionAccessEvent)
        .order_by(SubscriptionAccessEvent.occurred_at)
        .all()
    )
    assert [event.event_type for event in events] == [
        "access_activated",
        "access_reviewed",
    ]
    assert db_session.query(AuditEvent).count() == 1


def test_email_normalization_preserves_original_contact_value():
    original = "  Subscriber.Name@Example.COM "
    subscriber = Subscriber(
        stripe_customer_id="cus_email",
        stripe_email=original,
        normalized_email=normalize_subscriber_email(original),
    )
    assert subscriber.stripe_email == original
    assert subscriber.normalized_email == "subscriber.name@example.com"


def test_integration_event_supports_retry_state_without_raw_payload(db_session):
    event = IntegrationEvent(
        provider=IntegrationProvider.email,
        external_event_id="delivery-1",
        event_type="delivery.failed",
        processing_status=IntegrationProcessingStatus.retryable_failure,
        processing_attempts=1,
        next_retry_at=NOW + timedelta(minutes=10),
        payload_checksum="a" * 64,
        selected_metadata={"template": "invitation"},
    )
    db_session.add(event)
    db_session.commit()
    assert event.processing_status == IntegrationProcessingStatus.retryable_failure
    assert not hasattr(event, "raw_payload")
