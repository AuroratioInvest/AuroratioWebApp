import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from dependencies import create_access_token
from main import app
from models import MembershipLevel, User
from services.subscriber_fulfillment_service import (
    enqueue_fulfillment_for_entitlement,
    enqueue_missing_fulfillments_for_active_entitlements,
    process_due_fulfillments,
    process_one_fulfillment,
    request_manual_fulfillment_retry,
)
from services.telegram_private_channel_service import (
    TelegramPermanentError,
    validate_telegram_invite_url,
)
from subscriber_models import (
    AccessEntitlement,
    AccessFulfillmentStatus,
    AuditEvent,
    EntitlementAccessStatus,
    PlanChannelMapping,
    Subscriber,
    SubscriberAccessFulfillment,
    SubscriberBillingStatus,
    SubscriberSubscription,
    SubscriptionPlan,
    TelegramChannel,
)


NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


class FakeTelegramService:
    def __init__(self, *, fail_create=False):
        self.created = []
        self.revoked = []
        self.fail_create = fail_create

    async def create_single_use_invite(self, *, chat_id, name, expires_at):
        if self.fail_create:
            from services.telegram_private_channel_service import TelegramProviderError

            raise TelegramProviderError("timeout for bot token 123456:[redacted]")
        self.created.append(
            {"chat_id": chat_id, "name": name, "expires_at": expires_at}
        )
        from services.telegram_private_channel_service import TelegramInvite

        return TelegramInvite(
            invite_url="https://t.me/+phase7InviteToken",
            provider_reference="tg_invite:testref",
            expires_at=expires_at,
        )

    async def revoke_invite(self, *, chat_id, invite_url):
        self.revoked.append({"chat_id": chat_id, "invite_url": invite_url})
        return True


def _plan(db, *, code="monthly-signals", price_id="price_phase7"):
    plan = SubscriptionPlan(
        code=code,
        display_name_en="Monthly signals",
        display_name_fr="Signaux mensuels",
        stripe_price_id=price_id,
        billing_interval="month",
        is_active=True,
        is_configured=True,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(plan)
    db.commit()
    return plan


def _channel(db, *, active=True, configured=True, chat_id=-1004352124491, code="signals"):
    channel = TelegramChannel(
        code=code,
        display_name_en="Signals",
        display_name_fr="Signaux",
        telegram_chat_id=chat_id,
        is_active=active,
        is_configured=configured,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(channel)
    db.commit()
    return channel


def _mapping(db, plan, channel, *, active=True):
    mapping = PlanChannelMapping(
        plan_id=plan.id,
        channel_id=channel.id,
        is_active=active,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(mapping)
    db.commit()
    return mapping


def _subscriber_stack(db, plan, *, email="subscriber@example.com", suffix="phase7"):
    subscriber = Subscriber(
        stripe_customer_id=f"cus_{suffix}",
        stripe_email=email,
        normalized_email=email,
        preferred_language="en",
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(subscriber)
    db.flush()
    subscription = SubscriberSubscription(
        subscriber_id=subscriber.id,
        plan_id=plan.id,
        stripe_subscription_id=f"sub_{suffix}",
        stripe_status="active",
        billing_status=SubscriberBillingStatus.active,
        current_period_start=NOW - timedelta(days=1),
        current_period_end=NOW + timedelta(days=30),
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(subscription)
    db.flush()
    entitlement = AccessEntitlement(
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        plan_id=plan.id,
        status=EntitlementAccessStatus.active,
        access_starts_at=NOW - timedelta(days=1),
        paid_through_at=NOW + timedelta(days=30),
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(entitlement)
    db.commit()
    return subscriber, subscription, entitlement


def _session_factory(db_session):
    return sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
    )


def test_entitlement_activation_enqueues_fulfillment_idempotently(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    mapping = _mapping(db_session, plan, channel)
    _subscriber, subscription, entitlement = _subscriber_stack(db_session, plan)

    created = enqueue_fulfillment_for_entitlement(
        db_session,
        entitlement=entitlement,
        now=NOW,
    )
    db_session.commit()

    assert created == 1
    row = db_session.query(SubscriberAccessFulfillment).one()
    assert row.subscriber_subscription_id == subscription.id
    assert row.access_entitlement_id == entitlement.id
    assert row.plan_channel_mapping_id == mapping.id
    assert row.telegram_channel_id == channel.id
    assert row.status == AccessFulfillmentStatus.pending

    again = enqueue_fulfillment_for_entitlement(
        db_session,
        entitlement=entitlement,
        now=NOW,
    )
    db_session.commit()
    assert again == 0
    assert db_session.query(SubscriberAccessFulfillment).count() == 1


def test_inactive_mapping_or_channel_is_not_claimable_and_records_gap(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session, active=False)
    _mapping(db_session, plan, channel)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)

    created = enqueue_fulfillment_for_entitlement(
        db_session,
        entitlement=entitlement,
        now=NOW,
    )
    db_session.commit()

    assert created == 0
    assert db_session.query(SubscriberAccessFulfillment).count() == 0
    event = db_session.query(AuditEvent).filter(
        AuditEvent.action == "access_fulfillment_configuration_missing"
    ).one()
    assert event.entity_id == entitlement.id


def test_multiple_active_channel_mappings_create_one_fulfillment_each(db_session):
    plan = _plan(db_session)
    first = _channel(db_session, chat_id=-100111)
    second = _channel(db_session, chat_id=-100222, code="signals-2")
    _mapping(db_session, plan, first)
    _mapping(db_session, plan, second)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)

    created = enqueue_fulfillment_for_entitlement(
        db_session,
        entitlement=entitlement,
        now=NOW,
    )
    db_session.commit()

    assert created == 2
    assert db_session.query(SubscriberAccessFulfillment).count() == 2


def test_fulfillment_unique_constraint_rejects_duplicate_entitlement_mapping(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    mapping = _mapping(db_session, plan, channel)
    subscriber, subscription, entitlement = _subscriber_stack(db_session, plan)

    rows = [
        SubscriberAccessFulfillment(
            subscriber_id=subscriber.id,
            subscriber_subscription_id=subscription.id,
            access_entitlement_id=entitlement.id,
            subscription_plan_id=plan.id,
            telegram_channel_id=channel.id,
            plan_channel_mapping_id=mapping.id,
            status=AccessFulfillmentStatus.pending,
            attempt_count=0,
            created_at=NOW,
            updated_at=NOW,
        ),
        SubscriberAccessFulfillment(
            subscriber_id=subscriber.id,
            subscriber_subscription_id=subscription.id,
            access_entitlement_id=entitlement.id,
            subscription_plan_id=plan.id,
            telegram_channel_id=channel.id,
            plan_channel_mapping_id=mapping.id,
            status=AccessFulfillmentStatus.pending,
            attempt_count=0,
            created_at=NOW,
            updated_at=NOW,
        ),
    ]
    db_session.add_all(rows)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_fulfillment_mapping_identity_rejects_plan_or_channel_mismatch(db_session):
    plan = _plan(db_session)
    other_plan = _plan(db_session, code="other-plan", price_id="price_other")
    channel = _channel(db_session)
    other_channel = _channel(db_session, code="other-channel", chat_id=-100999)
    valid_mapping = _mapping(db_session, plan, channel)
    other_plan_mapping = _mapping(db_session, other_plan, channel)
    other_channel_mapping = _mapping(db_session, plan, other_channel)
    subscriber, subscription, entitlement = _subscriber_stack(db_session, plan)

    valid = SubscriberAccessFulfillment(
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        access_entitlement_id=entitlement.id,
        subscription_plan_id=plan.id,
        telegram_channel_id=channel.id,
        plan_channel_mapping_id=valid_mapping.id,
        status=AccessFulfillmentStatus.pending,
        attempt_count=0,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(valid)
    db_session.commit()

    bad_plan = SubscriberAccessFulfillment(
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        access_entitlement_id=entitlement.id,
        subscription_plan_id=plan.id,
        telegram_channel_id=channel.id,
        plan_channel_mapping_id=other_plan_mapping.id,
        status=AccessFulfillmentStatus.pending,
        attempt_count=0,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(bad_plan)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    bad_channel = SubscriberAccessFulfillment(
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        access_entitlement_id=entitlement.id,
        subscription_plan_id=plan.id,
        telegram_channel_id=channel.id,
        plan_channel_mapping_id=other_channel_mapping.id,
        status=AccessFulfillmentStatus.pending,
        attempt_count=0,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(bad_channel)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_processing_success_marks_delivered_without_persisting_raw_invite(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    db_session.commit()
    sent = []

    async def fake_email(**kwargs):
        sent.append(kwargs)
        return True

    result = asyncio.run(
        process_due_fulfillments(
            session_factory=_session_factory(db_session),
            telegram_service=FakeTelegramService(),
            email_sender=fake_email,
            now=NOW,
        )
    )

    row = db_session.query(SubscriberAccessFulfillment).one()
    assert result.delivered == 1
    assert row.status == AccessFulfillmentStatus.delivered
    assert row.provider_invite_reference == "tg_invite:testref"
    assert row.delivered_at is not None
    assert "phase7InviteToken" not in str(row.provider_invite_reference)
    assert sent[0]["invitations"][0]["url"] == "https://t.me/+phase7InviteToken"
    audit_text = " ".join(
        str(event.event_metadata) for event in db_session.query(AuditEvent).all()
    )
    assert "phase7InviteToken" not in audit_text


def test_email_failure_revokes_invite_and_retries_with_fresh_invite(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    db_session.commit()
    provider = FakeTelegramService()

    async def failing_email(**kwargs):
        return False

    result = asyncio.run(
        process_due_fulfillments(
            session_factory=_session_factory(db_session),
            telegram_service=provider,
            email_sender=failing_email,
            now=NOW,
        )
    )

    row = db_session.query(SubscriberAccessFulfillment).one()
    assert result.retryable_failures == 1
    assert row.status == AccessFulfillmentStatus.retryable_failure
    assert row.last_error_code == "email_delivery_failed"
    assert provider.revoked == [
        {"chat_id": -1004352124491, "invite_url": "https://t.me/+phase7InviteToken"}
    ]


def test_telegram_failure_does_not_call_email(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    db_session.commit()
    called = False

    async def email_sender(**kwargs):
        nonlocal called
        called = True
        return True

    result = asyncio.run(
        process_due_fulfillments(
            session_factory=_session_factory(db_session),
            telegram_service=FakeTelegramService(fail_create=True),
            email_sender=email_sender,
            now=NOW,
        )
    )

    row = db_session.query(SubscriberAccessFulfillment).one()
    assert result.retryable_failures == 1
    assert row.status == AccessFulfillmentStatus.retryable_failure
    assert called is False


def test_stale_claim_cannot_finalize_after_recovery(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    row = db_session.query(SubscriberAccessFulfillment).one()
    row.status = AccessFulfillmentStatus.processing
    row.delivery_claimed_at = NOW
    row.processing_claim_id = "old-claim"
    row.attempt_count = 1
    db_session.commit()
    provider = FakeTelegramService()
    sent = []

    async def fake_email(**kwargs):
        sent.append(kwargs)
        return True

    result = asyncio.run(
        process_due_fulfillments(
            session_factory=_session_factory(db_session),
            telegram_service=provider,
            email_sender=fake_email,
            now=NOW + timedelta(hours=2),
        )
    )
    assert result.delivered == 1

    stale_result = asyncio.run(
        process_one_fulfillment(
            row.id,
            claim_id="old-claim",
            session_factory=_session_factory(db_session),
            telegram_service=FakeTelegramService(),
            email_sender=fake_email,
            now=NOW + timedelta(hours=2, seconds=1),
        )
    )

    refreshed = db_session.query(SubscriberAccessFulfillment).one()
    assert stale_result == AccessFulfillmentStatus.cancelled
    assert refreshed.status == AccessFulfillmentStatus.delivered
    assert len(sent) == 1


def test_inactive_entitlement_before_processing_cancels_without_provider_calls(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    entitlement.status = EntitlementAccessStatus.expired
    entitlement.expires_at = NOW - timedelta(seconds=1)
    db_session.commit()
    provider = FakeTelegramService()

    result = asyncio.run(
        process_due_fulfillments(
            session_factory=_session_factory(db_session),
            telegram_service=provider,
            email_sender=lambda **kwargs: True,
            now=NOW,
        )
    )

    row = db_session.query(SubscriberAccessFulfillment).one()
    assert result.cancelled == 1
    assert row.status == AccessFulfillmentStatus.cancelled
    assert provider.created == []


def test_admin_retry_and_backfill_are_authenticated(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    row = db_session.query(SubscriberAccessFulfillment).one()
    row.status = AccessFulfillmentStatus.retryable_failure
    row.last_error_code = "email_delivery_failed"
    db_session.commit()

    admin = User(
        email="admin@example.com",
        hashed_password="x",
        is_active=True,
        membership_level=MembershipLevel.aurum,
    )
    customer = User(
        email="customer@example.com",
        hashed_password="x",
        is_active=True,
        membership_level=MembershipLevel.classic,
    )
    db_session.add_all([admin, customer])
    db_session.commit()

    def override_db():
        yield db_session

    app.dependency_overrides.clear()
    from database import get_db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    assert client.post(f"/admin/fulfillment/{row.id}/retry").status_code == 401
    customer_token = create_access_token(customer.id)
    assert (
        client.post(
            f"/admin/fulfillment/{row.id}/retry",
            headers={"Authorization": f"Bearer {customer_token}"},
        ).status_code
        == 403
    )
    admin_token = create_access_token(admin.id)
    response = client.post(
        f"/admin/fulfillment/{row.id}/retry",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    app.dependency_overrides.clear()


def test_admin_process_due_requires_active_admin_and_uses_bounded_worker(
    db_session,
    monkeypatch,
):
    admin = User(
        email="admin-process@example.com",
        hashed_password="x",
        is_active=True,
        membership_level=MembershipLevel.aurum,
    )
    inactive_admin = User(
        email="inactive-process@example.com",
        hashed_password="x",
        is_active=False,
        membership_level=MembershipLevel.aurum,
    )
    db_session.add_all([admin, inactive_admin])
    db_session.commit()
    calls = []

    async def fake_process_due_fulfillments(*, limit, now):
        calls.append({"limit": limit, "now": now})
        from services.subscriber_fulfillment_service import FulfillmentProcessResult

        return FulfillmentProcessResult(processed=1, delivered=1)

    monkeypatch.setattr(
        "routers.admin_fulfillment.process_due_fulfillments",
        fake_process_due_fulfillments,
    )

    def override_db():
        yield db_session

    app.dependency_overrides.clear()
    from database import get_db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    assert client.post("/admin/fulfillment/process-due").status_code == 401

    inactive_token = create_access_token(inactive_admin.id)
    assert (
        client.post(
            "/admin/fulfillment/process-due",
            headers={"Authorization": f"Bearer {inactive_token}"},
        ).status_code
        == 403
    )

    admin_token = create_access_token(admin.id)
    response = client.post(
        "/admin/fulfillment/process-due",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "processed": 1,
        "delivered": 1,
        "retryable_failures": 0,
        "terminal_failures": 0,
        "cancelled": 0,
    }
    assert calls[0]["limit"] == 1
    assert (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "access_fulfillment_due_processing_requested")
        .count()
        == 1
    )

    too_large = client.post(
        "/admin/fulfillment/process-due",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"limit": 3},
    )
    assert too_large.status_code == 422
    app.dependency_overrides.clear()


def test_process_due_ignores_non_due_and_delivered_rows(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    due = db_session.query(SubscriberAccessFulfillment).one()

    _subscriber2, _subscription2, entitlement2 = _subscriber_stack(
        db_session,
        plan,
        email="second@example.com",
        suffix="phase7_second",
    )
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement2, now=NOW)
    future = (
        db_session.query(SubscriberAccessFulfillment)
        .filter(SubscriberAccessFulfillment.access_entitlement_id == entitlement2.id)
        .one()
    )
    future.next_attempt_at = NOW + timedelta(days=1)

    _subscriber3, _subscription3, entitlement3 = _subscriber_stack(
        db_session,
        plan,
        email="third@example.com",
        suffix="phase7_third",
    )
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement3, now=NOW)
    delivered = (
        db_session.query(SubscriberAccessFulfillment)
        .filter(SubscriberAccessFulfillment.access_entitlement_id == entitlement3.id)
        .one()
    )
    delivered.status = AccessFulfillmentStatus.delivered
    delivered.delivered_at = NOW
    db_session.commit()

    sent = []

    async def fake_email(**kwargs):
        sent.append(kwargs)
        return True

    result = asyncio.run(
        process_due_fulfillments(
            session_factory=_session_factory(db_session),
            telegram_service=FakeTelegramService(),
            email_sender=fake_email,
            now=NOW,
            limit=10,
        )
    )

    db_session.refresh(due)
    db_session.refresh(future)
    db_session.refresh(delivered)
    assert result.processed == 1
    assert due.status == AccessFulfillmentStatus.delivered
    assert future.status == AccessFulfillmentStatus.pending
    assert delivered.status == AccessFulfillmentStatus.delivered
    assert len(sent) == 1


def test_backfill_is_idempotent_and_does_not_regenerate_delivered(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    _subscriber, _subscription, entitlement = _subscriber_stack(db_session, plan)

    result = enqueue_missing_fulfillments_for_active_entitlements(
        db_session,
        now=NOW,
        dry_run=False,
    )
    assert result["created"] == 1
    row = db_session.query(SubscriberAccessFulfillment).one()
    row.status = AccessFulfillmentStatus.delivered
    db_session.commit()

    result = enqueue_missing_fulfillments_for_active_entitlements(
        db_session,
        now=NOW,
        entitlement_id=entitlement.id,
        dry_run=False,
    )
    assert result["created"] == 0
    assert db_session.query(SubscriberAccessFulfillment).count() == 1


def test_backfill_is_bounded_deterministic_and_dry_run_is_write_free(db_session):
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    entitlements = []
    for index in range(3):
        _subscriber, _subscription, entitlement = _subscriber_stack(
            db_session,
            plan,
            email=f"batch-{index}@example.com",
            suffix=f"batch_{index}",
        )
        entitlements.append(entitlement)
    ordered_ids = sorted(entitlement.id for entitlement in entitlements)

    dry_run = enqueue_missing_fulfillments_for_active_entitlements(
        db_session,
        now=NOW,
        dry_run=True,
        limit=1,
    )
    assert dry_run["checked"] == 1
    assert dry_run["would_create"] == 1
    assert dry_run["created"] == 0
    assert dry_run["limit"] == 1
    assert dry_run["next_cursor"] == ordered_ids[0]
    assert db_session.query(SubscriberAccessFulfillment).count() == 0
    assert (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "access_fulfillment_enqueued")
        .count()
        == 0
    )

    first = enqueue_missing_fulfillments_for_active_entitlements(
        db_session,
        now=NOW,
        dry_run=False,
        limit=1,
    )
    assert first["created"] == 1
    assert first["next_cursor"] == ordered_ids[0]
    second = enqueue_missing_fulfillments_for_active_entitlements(
        db_session,
        now=NOW,
        dry_run=False,
        limit=2,
        after_entitlement_id=first["next_cursor"],
    )
    assert second["created"] == 2
    assert second["next_cursor"] is None

    repeat = enqueue_missing_fulfillments_for_active_entitlements(
        db_session,
        now=NOW,
        dry_run=False,
        limit=3,
    )
    assert repeat["created"] == 0
    assert db_session.query(SubscriberAccessFulfillment).count() == 3

    with pytest.raises(ValueError):
        enqueue_missing_fulfillments_for_active_entitlements(
            db_session,
            now=NOW,
            dry_run=True,
            limit=201,
        )


def test_telegram_invite_url_validation_accepts_only_trusted_invites():
    assert (
        validate_telegram_invite_url("https://t.me/+abcDEF123")
        == "https://t.me/+abcDEF123"
    )
    assert (
        validate_telegram_invite_url("https://telegram.me/joinchat/abcDEF123")
        == "https://telegram.me/joinchat/abcDEF123"
    )
    for value in [
        "http://t.me/+abc",
        "https://t.me:444/+abc",
        "https://telegram.me:444/joinchat/abc",
        "https://evil.test/+abc",
        "https://t.me.attacker.com/+abc",
        "https://sub.t.me/+abc",
        "https://attacker.com/t.me/+abc",
        "https://t.me/somepublicchannel",
        "https://t.me/+",
        "https://telegram.me/joinchat/",
        "https://user:pass@t.me/+abc",
        "https://user@t.me/+abc",
        "https://t.me/+abc?token=leak",
        "https://t.me/+abc#fragment",
        "https://t.me/%ZZ",
        "https://т.me/+abc",
    ]:
        with pytest.raises(TelegramPermanentError):
            validate_telegram_invite_url(value)
