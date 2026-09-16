import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from database import get_db
from dependencies import create_access_token
from main import app
from models import MembershipLevel, User
from subscriber_models import (
    AccessEntitlement,
    AccessFulfillmentStatus,
    AuditEvent,
    EntitlementAccessStatus,
    PlanChannelMapping,
    SignalPublicationStatus,
    Subscriber,
    SubscriberAccessFulfillment,
    SubscriberBillingStatus,
    SubscriberSignal,
    SubscriberSignalDirection,
    SubscriberSignalPlanTarget,
    SubscriberSignalPublication,
    SubscriberSignalStatus,
    SubscriberSubscription,
    SubscriptionPlan,
    TelegramChannel,
)


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def _admin(db, *, active=True, email="admin-ops@example.com"):
    row = User(
        email=email,
        hashed_password="x",
        is_active=active,
        membership_level=MembershipLevel.aurum,
    )
    db.add(row)
    db.commit()
    return row


def _customer(db):
    row = User(
        email="customer-ops@example.com",
        hashed_password="x",
        is_active=True,
        membership_level=MembershipLevel.classic,
    )
    db.add(row)
    db.commit()
    return row


def _client(db_session):
    app.dependency_overrides.clear()

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _plan(db, *, id, code, active=True, configured=True, archived=False):
    row = SubscriptionPlan(
        id=id,
        code=code,
        display_name_en=f"{code} EN",
        display_name_fr=f"{code} FR",
        stripe_price_id=f"price_{id}",
        billing_interval="month",
        is_active=active,
        is_configured=configured,
        created_at=NOW,
        updated_at=NOW,
        archived_at=NOW if archived else None,
    )
    db.add(row)
    db.commit()
    return row


def _channel(
    db,
    *,
    id,
    code,
    active=True,
    configured=True,
    target=-100123,
    archived=False,
):
    row = TelegramChannel(
        id=id,
        code=code,
        display_name_en=f"{code} English",
        display_name_fr=f"{code} Français",
        telegram_chat_id=target,
        is_active=active,
        is_configured=configured,
        created_at=NOW,
        updated_at=NOW,
        archived_at=NOW if archived else None,
    )
    db.add(row)
    db.commit()
    return row


def _mapping(db, *, id, plan, channel, active=True):
    row = PlanChannelMapping(
        id=id,
        plan_id=plan.id,
        channel_id=channel.id,
        is_active=active,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


def _subscriber_stack(db, *, plan, index):
    subscriber = Subscriber(
        id=f"subscriber-{index}",
        stripe_customer_id=f"cus_ops_{index}",
        stripe_email=f"subscriber-{index}@example.com",
        normalized_email=f"subscriber-{index}@example.com",
        created_at=NOW,
        updated_at=NOW,
    )
    subscription = SubscriberSubscription(
        id=f"subscriber-subscription-{index}",
        subscriber_id=subscriber.id,
        plan_id=plan.id,
        stripe_subscription_id=f"sub_ops_{index}",
        billing_status=SubscriberBillingStatus.active,
        stripe_status="active",
        current_period_start=NOW - timedelta(days=1),
        current_period_end=NOW + timedelta(days=30),
        created_at=NOW,
        updated_at=NOW,
    )
    entitlement = AccessEntitlement(
        id=f"entitlement-{index}",
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        plan_id=plan.id,
        status=EntitlementAccessStatus.active,
        access_starts_at=NOW,
        paid_through_at=NOW + timedelta(days=30),
        created_at=NOW,
        updated_at=NOW,
    )
    db.add_all([subscriber, subscription, entitlement])
    db.commit()
    return subscriber, subscription, entitlement


def _fulfillment(db, *, status, plan, mapping, channel, index):
    subscriber, subscription, entitlement = _subscriber_stack(
        db,
        plan=plan,
        index=index,
    )
    row = SubscriberAccessFulfillment(
        id=f"fulfillment-{status.value}",
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        access_entitlement_id=entitlement.id,
        subscription_plan_id=plan.id,
        telegram_channel_id=channel.id,
        plan_channel_mapping_id=mapping.id,
        status=status,
        attempt_count=1 if status != AccessFulfillmentStatus.pending else 0,
        next_attempt_at=NOW if status == AccessFulfillmentStatus.retryable_failure else None,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


def _signal_publication(db, *, status, plan, mapping, channel, index):
    signal = SubscriberSignal(
        id=f"signal-{status.value}",
        status=SubscriberSignalStatus.approved,
        symbol=f"XAUUSD{index}",
        direction=SubscriberSignalDirection.buy,
        entry="2400",
        stop_loss="2380",
        take_profit_targets=["2420"],
        approved_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    target = SubscriberSignalPlanTarget(
        id=f"signal-target-{status.value}",
        signal_id=signal.id,
        plan_id=plan.id,
        created_at=NOW,
    )
    publication = SubscriberSignalPublication(
        id=f"publication-{status.value}",
        subscriber_signal_id=signal.id,
        signal_plan_target_id=target.id,
        plan_channel_mapping_id=mapping.id,
        subscription_plan_id=plan.id,
        telegram_channel_id=channel.id,
        status=status,
        attempt_count=1 if status != SignalPublicationStatus.pending else 0,
        next_attempt_at=NOW if status == SignalPublicationStatus.retryable_failure else None,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add_all([signal, target, publication])
    db.commit()
    return publication


def _seed_operations_state(db):
    plan = _plan(db, id="plan-ops", code="monthly-signals")
    inactive_plan = _plan(db, id="plan-inactive", code="inactive-plan", active=False)
    ready = _channel(
        db,
        id="channel-ready",
        code="private-signals",
        target=-100111,
    )
    inactive = _channel(
        db,
        id="channel-inactive",
        code="inactive-channel",
        active=False,
        target=-100222,
    )
    missing_target = _channel(
        db,
        id="channel-missing-target",
        code="missing-target",
        target=None,
    )
    archived = _channel(
        db,
        id="channel-archived",
        code="archived-channel",
        archived=True,
        target=-100333,
    )
    provider_named = _channel(
        db,
        id="channel-provider-name",
        code="telegram-internal",
        target=-100444,
    )
    mapping = _mapping(db, id="mapping-ready", plan=plan, channel=ready)
    _mapping(db, id="mapping-inactive", plan=plan, channel=inactive, active=False)
    _mapping(db, id="mapping-provider-name", plan=inactive_plan, channel=provider_named)

    for index, status in enumerate(AccessFulfillmentStatus):
        _fulfillment(
            db,
            status=status,
            plan=plan,
            mapping=mapping,
            channel=ready,
            index=index,
        )
    for index, status in enumerate(SignalPublicationStatus):
        _signal_publication(
            db,
            status=status,
            plan=plan,
            mapping=mapping,
            channel=ready,
            index=index,
        )
    draft = SubscriberSignal(
        id="signal-draft",
        status=SubscriberSignalStatus.draft,
        symbol="XAGUSD",
        direction=SubscriberSignalDirection.sell,
        entry="30",
        stop_loss="31",
        take_profit_targets=["29"],
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(draft)
    db.commit()


def _assert_no_sensitive_provider_data(payload):
    encoded = json.dumps(payload)
    assert "TELEGRAM_BOT_TOKEN" not in encoded
    assert "secret-token" not in encoded
    assert "-100111" not in encoded
    assert "-100222" not in encoded
    assert "-100333" not in encoded
    assert "-100444" not in encoded
    assert "invite" not in encoded.lower()
    assert "stripe_" not in encoded.lower()
    assert "telegram" not in encoded.lower()


def test_private_channel_operations_requires_active_admin(db_session):
    admin = _admin(db_session)
    inactive_admin = _admin(
        db_session,
        active=False,
        email="inactive-admin-ops@example.com",
    )
    customer = _customer(db_session)
    client = _client(db_session)

    assert client.get("/admin/private-channel-operations/overview").status_code == 401
    assert (
        client.get(
            "/admin/private-channel-operations/overview",
            headers=_auth(customer),
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/admin/private-channel-operations/overview",
            headers=_auth(inactive_admin),
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/admin/private-channel-operations/channel-configuration",
            headers=_auth(inactive_admin),
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/private-channel-operations/overview",
            headers=_auth(admin),
        ).status_code
        == 404
    )
    app.dependency_overrides.clear()


def test_overview_returns_safe_aggregate_counts_and_credential_status(
    db_session,
    monkeypatch,
):
    _seed_operations_state(db_session)
    admin = _admin(db_session)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "configured-for-tests")
    before_audit_count = db_session.query(AuditEvent).count()

    client = _client(db_session)
    response = client.get(
        "/admin/private-channel-operations/overview",
        headers=_auth(admin),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_credentials_configured"] is True
    assert payload["private_channel_counts"] == {
        "total": 5,
        "active": 3,
        "configured": 4,
        "ready": 2,
    }
    assert payload["active_plan_channel_mapping_count"] == 2
    assert payload["approved_signal_count"] == len(SignalPublicationStatus)
    assert payload["draft_signal_count"] == 1
    assert payload["access_fulfillment_counts"] == {
        status.value: 1 for status in AccessFulfillmentStatus
    }
    assert payload["signal_publication_counts"] == {
        status.value: 1 for status in SignalPublicationStatus
    }
    _assert_no_sensitive_provider_data(payload)
    assert db_session.query(AuditEvent).count() == before_audit_count
    app.dependency_overrides.clear()


def test_overview_reports_missing_provider_credentials(db_session, monkeypatch):
    admin = _admin(db_session)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    client = _client(db_session)
    response = client.get(
        "/admin/private-channel-operations/overview",
        headers=_auth(admin),
    )

    assert response.status_code == 200
    assert response.json()["provider_credentials_configured"] is False
    app.dependency_overrides.clear()


def test_channel_configuration_is_bounded_deterministic_and_provider_neutral(
    db_session,
):
    _seed_operations_state(db_session)
    admin = _admin(db_session)
    before_audit_count = db_session.query(AuditEvent).count()

    client = _client(db_session)
    first = client.get(
        "/admin/private-channel-operations/channel-configuration?limit=2",
        headers=_auth(admin),
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["limit"] == 2
    assert first_payload["has_more"] is True
    assert len(first_payload["items"]) == 2
    assert [item["private_channel_id"] for item in first_payload["items"]] == [
        "channel-archived",
        "channel-inactive",
    ]

    second = client.get(
        "/admin/private-channel-operations/channel-configuration",
        params={"limit": 10, "after_channel_id": first_payload["next_cursor"]},
        headers=_auth(admin),
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert [item["private_channel_id"] for item in second_payload["items"]] == [
        "channel-missing-target",
        "channel-provider-name",
        "channel-ready",
    ]

    provider_named = next(
        item for item in second_payload["items"]
        if item["private_channel_id"] == "channel-provider-name"
    )
    assert provider_named["channel_code"] == "Private Channel-internal"
    assert provider_named["has_provider_target"] is True
    assert provider_named["is_ready"] is True
    assert provider_named["mappings"] == [
        {
            "mapping_id": "mapping-provider-name",
            "plan_id": "plan-inactive",
            "plan_code": "inactive-plan",
            "plan_display_name_en": "inactive-plan EN",
            "plan_display_name_fr": "inactive-plan FR",
            "is_active": True,
        }
    ]

    ready = next(
        item for item in second_payload["items"]
        if item["private_channel_id"] == "channel-ready"
    )
    assert ready["is_active"] is True
    assert ready["is_configured"] is True
    assert ready["is_archived"] is False
    assert ready["has_provider_target"] is True
    assert ready["is_ready"] is True

    _assert_no_sensitive_provider_data(first_payload)
    _assert_no_sensitive_provider_data(second_payload)
    assert db_session.query(AuditEvent).count() == before_audit_count
    app.dependency_overrides.clear()


def test_channel_configuration_rejects_unbounded_limits(db_session):
    admin = _admin(db_session)
    client = _client(db_session)

    response = client.get(
        "/admin/private-channel-operations/channel-configuration?limit=101",
        headers=_auth(admin),
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()
