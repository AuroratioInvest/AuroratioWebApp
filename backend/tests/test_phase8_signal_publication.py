import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from database import get_db
from dependencies import create_access_token
from main import app
from models import MembershipLevel, User
from services.subscriber_signal_publication_service import (
    SIGNAL_PUBLICATION_MAX_LIMIT,
    approve_signal,
    backfill_missing_signal_publications,
    create_signal_draft,
    process_due_signal_publications,
    process_one_signal_publication,
    render_signal_message,
    retry_signal_publication,
    update_signal_draft,
)
from services.telegram_private_channel_service import (
    TelegramPermanentError,
    TelegramProviderError,
    TelegramRateLimitError,
)
from subscriber_models import (
    AuditEvent,
    PlanChannelMapping,
    SignalDeliveryAttemptOutcome,
    SignalPublicationStatus,
    SubscriberSignal,
    SubscriberSignalDeliveryAttempt,
    SubscriberSignalDirection,
    SubscriberSignalPlanTarget,
    SubscriberSignalPublication,
    SubscriberSignalStatus,
    SubscriptionPlan,
    TelegramChannel,
)


NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


class FakeTelegramPublisher:
    def __init__(self, *, error=None):
        self.messages = []
        self.error = error

    async def publish_text_message(self, *, chat_id: int, text: str):
        if self.error:
            raise self.error
        self.messages.append({"chat_id": chat_id, "text": text})
        from services.telegram_private_channel_service import TelegramPublishedMessage

        return TelegramPublishedMessage(provider_reference="tg_message:42", message_id=42)


def _plan(db, *, code="monthly-signals", active=True, configured=True, archived=False):
    row = SubscriptionPlan(
        code=code,
        display_name_en="Monthly signals",
        display_name_fr="Signaux mensuels",
        stripe_price_id=f"price_{code}",
        billing_interval="month",
        is_active=active,
        is_configured=configured,
        archived_at=NOW if archived else None,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


def _channel(db, *, code="signals", active=True, configured=True, chat_id=-1004352124491):
    row = TelegramChannel(
        code=code,
        display_name_en="Signals",
        display_name_fr="Signaux",
        telegram_chat_id=chat_id,
        is_active=active,
        is_configured=configured,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


def _mapping(db, plan, channel, *, active=True):
    row = PlanChannelMapping(
        plan_id=plan.id,
        channel_id=channel.id,
        is_active=active,
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


def _admin(db, *, active=True, email="admin-phase8@example.com"):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return existing
    row = User(
        email=email,
        hashed_password="x",
        is_active=active,
        membership_level=MembershipLevel.aurum,
    )
    db.add(row)
    db.commit()
    return row


def _admin_id(db):
    return _admin(db, email="admin@example.com").id


def _draft(db, plan, *, symbol="XAUUSD"):
    return create_signal_draft(
        db,
        admin_user_id=_admin_id(db),
        symbol=symbol,
        direction=SubscriberSignalDirection.buy,
        entry="2410.00",
        stop_loss="2390.00",
        take_profit_targets=["2430.00", "2450.00"],
        analysis="Range breakout",
        expires_at=NOW + timedelta(hours=4),
        plan_ids=[plan.id],
        now=NOW,
    )


def _approved_publication(db):
    plan = _plan(db)
    channel = _channel(db)
    mapping = _mapping(db, plan, channel)
    signal = _draft(db, plan)
    approve_signal(db, signal_id=signal.id, admin_user_id=_admin_id(db), now=NOW)
    publication = db.query(SubscriberSignalPublication).one()
    return plan, channel, mapping, signal, publication


def _session_factory(db_session):
    return sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)


def test_admin_can_create_update_and_approve_signal_with_publications(db_session):
    plan = _plan(db_session)
    first = _channel(db_session)
    second = _channel(db_session, code="signals-2", chat_id=-100222)
    _mapping(db_session, plan, first)
    _mapping(db_session, plan, second)

    signal = _draft(db_session, plan, symbol="xagusd")
    assert signal.status == SubscriberSignalStatus.draft
    assert signal.symbol == "XAGUSD"

    updated = update_signal_draft(
        db_session,
        signal_id=signal.id,
        admin_user_id=_admin_id(db_session),
        updates={"analysis": "Re-test of resistance"},
        now=NOW + timedelta(minutes=1),
    )
    assert updated.analysis == "Re-test of resistance"

    approved = approve_signal(
        db_session,
        signal_id=signal.id,
        admin_user_id=_admin_id(db_session),
        now=NOW + timedelta(minutes=2),
    )
    assert approved.status == SubscriberSignalStatus.approved
    assert db_session.query(SubscriberSignalPublication).count() == 2

    approve_signal(
        db_session,
        signal_id=signal.id,
        admin_user_id=_admin_id(db_session),
        now=NOW + timedelta(minutes=3),
    )
    assert db_session.query(SubscriberSignalPublication).count() == 2


def test_signal_validation_rejects_html_and_invalid_targets(db_session):
    plan = _plan(db_session)
    with pytest.raises(ValueError):
        create_signal_draft(
            db_session,
            admin_user_id=_admin_id(db_session),
            symbol="<script>",
            direction=SubscriberSignalDirection.buy,
            entry="2410",
            stop_loss="2390",
            take_profit_targets=["2430"],
            analysis=None,
            expires_at=None,
            plan_ids=[plan.id],
            now=NOW,
        )

    with pytest.raises(ValueError):
        create_signal_draft(
            db_session,
            admin_user_id=_admin_id(db_session),
            symbol="XAUUSD",
            direction=SubscriberSignalDirection.buy,
            entry="2410",
            stop_loss="2390",
            take_profit_targets=["2430"],
            analysis=None,
            expires_at=NOW - timedelta(minutes=1),
            plan_ids=[plan.id],
            now=NOW,
        )
    with pytest.raises(ValueError):
        create_signal_draft(
            db_session,
            admin_user_id=_admin_id(db_session),
            symbol="XAUUSD",
            direction=SubscriberSignalDirection.buy,
            entry="2410",
            stop_loss="2390",
            take_profit_targets=[],
            analysis=None,
            expires_at=None,
            plan_ids=[plan.id],
            now=NOW,
        )


def test_approval_with_no_active_mapping_is_observable_and_backfillable(db_session):
    plan = _plan(db_session)
    signal = _draft(db_session, plan)
    admin_user_id = _admin_id(db_session)

    approve_signal(db_session, signal_id=signal.id, admin_user_id=admin_user_id, now=NOW)

    assert db_session.query(SubscriberSignalPublication).count() == 0
    assert (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "signal_publication_configuration_missing")
        .count()
        == 1
    )

    _mapping(db_session, plan, _channel(db_session))
    dry = backfill_missing_signal_publications(
        db_session,
        now=NOW,
        admin_user_id=admin_user_id,
        dry_run=True,
        limit=10,
    )
    assert dry["would_create"] == 1
    assert db_session.query(SubscriberSignalPublication).count() == 0

    result = backfill_missing_signal_publications(
        db_session,
        now=NOW,
        admin_user_id=admin_user_id,
        dry_run=False,
        limit=10,
    )
    assert result["created"] == 1
    assert db_session.query(SubscriberSignalPublication).count() == 1
    audit = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "signal_publication_backfill_requested")
        .one()
    )
    assert audit.actor_admin_user_id == admin_user_id
    assert audit.event_metadata == {
        "checked": 1,
        "would_create": 1,
        "created": 1,
        "limit": 10,
        "has_more": False,
    }


def test_inactive_plan_mapping_and_channel_are_excluded(db_session):
    active_plan = _plan(db_session)
    inactive_plan = _plan(db_session, code="inactive", active=False)
    inactive_mapping_plan = _plan(db_session, code="inactive-mapping")
    inactive_channel_plan = _plan(db_session, code="inactive-channel")

    _mapping(db_session, active_plan, _channel(db_session))
    _mapping(db_session, inactive_plan, _channel(db_session, code="inactive-plan-channel", chat_id=-1002))
    _mapping(
        db_session,
        inactive_mapping_plan,
        _channel(db_session, code="inactive-mapping-channel", chat_id=-1003),
        active=False,
    )
    _mapping(
        db_session,
        inactive_channel_plan,
        _channel(db_session, code="inactive-channel", active=False, chat_id=-1004),
    )

    signal = create_signal_draft(
        db_session,
        admin_user_id=_admin_id(db_session),
        symbol="XAUUSD",
        direction=SubscriberSignalDirection.sell,
        entry="2400",
        stop_loss="2420",
        take_profit_targets=["2380"],
        analysis=None,
        expires_at=None,
        plan_ids=[
            active_plan.id,
            inactive_plan.id,
            inactive_mapping_plan.id,
            inactive_channel_plan.id,
        ],
        now=NOW,
    )
    approve_signal(db_session, signal_id=signal.id, admin_user_id=_admin_id(db_session), now=NOW)

    assert db_session.query(SubscriberSignalPublication).count() == 1
    assert db_session.query(SubscriberSignalPublication).one().subscription_plan_id == active_plan.id


def test_database_rejects_mismatched_signal_target_mapping_plan_and_channel(db_session):
    plan = _plan(db_session)
    other_plan = _plan(db_session, code="other")
    channel = _channel(db_session)
    other_channel = _channel(db_session, code="other-channel", chat_id=-100333)
    mapping = _mapping(db_session, plan, channel)
    signal = _draft(db_session, plan)
    target = db_session.query(SubscriberSignalPlanTarget).one()

    bad_plan = SubscriberSignalPublication(
        subscriber_signal_id=signal.id,
        signal_plan_target_id=target.id,
        plan_channel_mapping_id=mapping.id,
        subscription_plan_id=other_plan.id,
        telegram_channel_id=channel.id,
        status=SignalPublicationStatus.pending,
        attempt_count=0,
        next_attempt_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(bad_plan)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    bad_channel = SubscriberSignalPublication(
        subscriber_signal_id=signal.id,
        signal_plan_target_id=target.id,
        plan_channel_mapping_id=mapping.id,
        subscription_plan_id=plan.id,
        telegram_channel_id=other_channel.id,
        status=SignalPublicationStatus.pending,
        attempt_count=0,
        next_attempt_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(bad_channel)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_worker_claims_and_publishes_once(db_session):
    _plan_row, channel, _mapping_row, _signal, publication = _approved_publication(db_session)
    service = FakeTelegramPublisher()

    result = asyncio.run(
        process_due_signal_publications(
            limit=1,
            session_factory=_session_factory(db_session),
            telegram_service=service,
            now=NOW,
        )
    )

    assert result.processed == 1
    assert result.published == 1
    db_session.expire_all()
    row = db_session.get(SubscriberSignalPublication, publication.id)
    assert row.status == SignalPublicationStatus.published
    assert row.provider_message_reference == "tg_message:42"
    assert row.telegram_chat_id == channel.telegram_chat_id
    assert row.telegram_message_id == 42
    assert row.last_attempt_at == NOW
    attempt = db_session.query(SubscriberSignalDeliveryAttempt).one()
    assert attempt.attempt_number == 1
    assert attempt.outcome == SignalDeliveryAttemptOutcome.delivered
    assert attempt.telegram_chat_id == channel.telegram_chat_id
    assert attempt.telegram_message_id == 42
    assert attempt.provider_message_reference == "tg_message:42"
    assert attempt.completed_at == NOW
    assert service.messages == [{"chat_id": channel.telegram_chat_id, "text": service.messages[0]["text"]}]
    assert "making your own investment decisions" in service.messages[0]["text"]
    assert "subscriber" not in service.messages[0]["text"].lower()

    second = asyncio.run(
        process_due_signal_publications(
            limit=1,
            session_factory=_session_factory(db_session),
            telegram_service=service,
            now=NOW,
        )
    )
    assert second.processed == 0
    assert len(service.messages) == 1


def test_worker_retryable_terminal_and_rate_limit_failures(db_session):
    _plan_row, _channel, _mapping_row, _signal, publication = _approved_publication(db_session)

    result = asyncio.run(
        process_due_signal_publications(
            limit=1,
            session_factory=_session_factory(db_session),
            telegram_service=FakeTelegramPublisher(error=TelegramRateLimitError("rate", retry_after_seconds=17)),
            now=NOW,
        )
    )
    assert result.retryable_failures == 1
    db_session.expire_all()
    row = db_session.get(SubscriberSignalPublication, publication.id)
    assert row.status == SignalPublicationStatus.retryable_failure
    assert row.next_attempt_at == NOW + timedelta(seconds=17)
    assert row.last_error_message == "rate"
    first_attempt = (
        db_session.query(SubscriberSignalDeliveryAttempt)
        .filter_by(signal_publication_id=publication.id, attempt_number=1)
        .one()
    )
    assert first_attempt.outcome == SignalDeliveryAttemptOutcome.transient_failure
    assert first_attempt.error_code == "telegram_rate_limited"
    assert first_attempt.error_message == "rate"
    assert first_attempt.is_retryable is True

    row.next_attempt_at = NOW
    db_session.commit()
    result = asyncio.run(
            process_due_signal_publications(
                limit=1,
                session_factory=_session_factory(db_session),
                telegram_service=FakeTelegramPublisher(
                    error=TelegramPermanentError("missing permission")
                ),
                now=NOW,
            )
        )
    assert result.terminal_failures == 1
    db_session.expire_all()
    terminal_row = db_session.get(SubscriberSignalPublication, publication.id)
    assert terminal_row.status == SignalPublicationStatus.terminal_failure
    second_attempt = (
        db_session.query(SubscriberSignalDeliveryAttempt)
        .filter_by(signal_publication_id=publication.id, attempt_number=2)
        .one()
    )
    assert second_attempt.outcome == SignalDeliveryAttemptOutcome.permanent_failure
    assert second_attempt.error_message == "missing permission"
    assert second_attempt.is_retryable is False


def test_stale_claim_recovery_rejects_stale_worker_finalization(db_session, monkeypatch):
    _plan_row, _channel, _mapping_row, _signal, publication = _approved_publication(db_session)
    publication.status = SignalPublicationStatus.processing
    publication.processing_claim_id = "stale"
    publication.processing_started_at = NOW + timedelta(minutes=1)
    publication.attempt_count = 1
    db_session.add(
        SubscriberSignalDeliveryAttempt(
            signal_publication_id=publication.id,
            attempt_number=1,
            processing_claim_id="stale",
            outcome=SignalDeliveryAttemptOutcome.processing,
            started_at=NOW + timedelta(minutes=1),
            created_at=NOW + timedelta(minutes=1),
        )
    )
    db_session.commit()
    monkeypatch.setenv("SIGNAL_PUBLICATION_CLAIM_LEASE_SECONDS", "10")
    later = NOW + timedelta(hours=1)

    service = FakeTelegramPublisher()
    result = asyncio.run(
        process_due_signal_publications(
            limit=1,
            session_factory=_session_factory(db_session),
            telegram_service=service,
            now=later,
        )
    )
    assert result.published == 1
    db_session.expire_all()
    row = db_session.get(SubscriberSignalPublication, publication.id)
    assert row.processing_claim_id is None
    assert row.status == SignalPublicationStatus.published
    attempts = (
        db_session.query(SubscriberSignalDeliveryAttempt)
        .filter_by(signal_publication_id=publication.id)
        .order_by(SubscriberSignalDeliveryAttempt.attempt_number)
        .all()
    )
    assert [attempt.outcome for attempt in attempts] == [
        SignalDeliveryAttemptOutcome.abandoned,
        SignalDeliveryAttemptOutcome.delivered,
    ]
    assert attempts[0].error_code == "processing_lease_expired"
    assert attempts[1].attempt_number == 2

    stale_status = asyncio.run(
        process_one_signal_publication(
            publication.id,
            claim_id="stale",
            session_factory=_session_factory(db_session),
            telegram_service=FakeTelegramPublisher(),
            now=later,
        )
    )
    assert stale_status == SignalPublicationStatus.cancelled


def test_inactive_signal_before_provider_call_cancels_without_publish(db_session):
    _plan_row, _channel, _mapping_row, signal, publication = _approved_publication(db_session)
    signal.status = SubscriberSignalStatus.cancelled
    db_session.commit()

    result = asyncio.run(
        process_due_signal_publications(
            limit=1,
            session_factory=_session_factory(db_session),
            telegram_service=FakeTelegramPublisher(),
            now=NOW,
        )
    )

    assert result.cancelled == 1
    db_session.expire_all()
    cancelled_row = db_session.get(SubscriberSignalPublication, publication.id)
    assert cancelled_row.status == SignalPublicationStatus.cancelled
    assert cancelled_row.cancelled_at == NOW
    attempt = db_session.query(SubscriberSignalDeliveryAttempt).one()
    assert attempt.outcome == SignalDeliveryAttemptOutcome.abandoned
    assert attempt.error_code == "signal_or_channel_inactive"


def test_expired_signal_before_provider_call_cancels_without_publish(db_session):
    _plan_row, _channel, _mapping_row, signal, publication = _approved_publication(db_session)
    signal.expires_at = NOW + timedelta(minutes=1)
    db_session.commit()

    result = asyncio.run(
        process_due_signal_publications(
            limit=1,
            session_factory=_session_factory(db_session),
            telegram_service=FakeTelegramPublisher(),
            now=NOW + timedelta(minutes=2),
        )
    )

    assert result.cancelled == 1
    db_session.expire_all()
    cancelled_row = db_session.get(SubscriberSignalPublication, publication.id)
    assert cancelled_row.status == SignalPublicationStatus.cancelled
    assert cancelled_row.cancelled_at == NOW + timedelta(minutes=2)
    attempt = db_session.query(SubscriberSignalDeliveryAttempt).one()
    assert attempt.outcome == SignalDeliveryAttemptOutcome.abandoned
    assert attempt.error_code == "signal_or_channel_inactive"


def test_rendering_is_deterministic_hides_internal_fields_and_is_provider_neutral(db_session):
    plan = _plan(db_session)
    signal = create_signal_draft(
        db_session,
        admin_user_id=_admin_id(db_session),
        symbol="XAUUSD",
        direction=SubscriberSignalDirection.buy,
        entry="2400 & wait",
        stop_loss="2390",
        take_profit_targets=["2410"],
        analysis="Manual review only",
        expires_at=None,
        plan_ids=[plan.id],
        now=NOW,
    )

    message = render_signal_message(signal)
    assert render_signal_message(signal) == message
    assert "2400 & wait" not in message
    assert "2390" not in message
    assert "Manual review only" not in message
    assert "Telegram" not in message
    assert "Stripe" not in message
    assert signal.id not in message
    assert "making your own investment decisions" in message


def test_admin_signal_routes_are_protected_bounded_and_safe(db_session, monkeypatch):
    admin = _admin(db_session)
    inactive = _admin(db_session, active=False, email="inactive-phase8@example.com")
    calls = []

    async def fake_process_due_signal_publications(*, limit, now):
        calls.append({"limit": limit, "now": now})
        from services.subscriber_signal_publication_service import SignalPublicationProcessResult

        return SignalPublicationProcessResult(processed=1, published=1)

    monkeypatch.setattr(
        "routers.admin_signal_publications.process_due_signal_publications",
        fake_process_due_signal_publications,
    )

    def override_db():
        yield db_session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)

    assert client.post("/admin/signal-publications/process-due").status_code == 401

    inactive_token = create_access_token(inactive.id)
    assert (
        client.post(
            "/admin/signal-publications/process-due",
            headers={"Authorization": f"Bearer {inactive_token}"},
        ).status_code
        == 403
    )

    token = create_access_token(admin.id)
    response = client.post(
        "/admin/signal-publications/process-due",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "processed": 1,
        "published": 1,
        "retryable_failures": 0,
        "terminal_failures": 0,
        "cancelled": 0,
    }
    assert calls[0]["limit"] == 1
    assert (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "signal_publication_due_processing_requested")
        .count()
        == 1
    )

    too_large = client.post(
        "/admin/signal-publications/process-due",
        headers={"Authorization": f"Bearer {token}"},
        json={"limit": SIGNAL_PUBLICATION_MAX_LIMIT + 1},
    )
    assert too_large.status_code == 422
    app.dependency_overrides.clear()


def test_admin_backfill_is_bounded_dry_run_write_free_and_paginated(db_session):
    admin_user_id = _admin_id(db_session)
    plan = _plan(db_session)
    _mapping(db_session, plan, _channel(db_session))
    signals = [_draft(db_session, plan, symbol=f"XAUUSD{i}") for i in range(3)]
    for signal in signals:
        approve_signal(db_session, signal_id=signal.id, admin_user_id=_admin_id(db_session), now=NOW)
    db_session.query(SubscriberSignalPublication).delete()
    audit_count = db_session.query(AuditEvent).count()
    db_session.commit()

    dry = backfill_missing_signal_publications(
        db_session,
        now=NOW,
        admin_user_id=admin_user_id,
        dry_run=True,
        limit=2,
    )
    assert dry["checked"] == 2
    assert dry["would_create"] == 2
    assert dry["created"] == 0
    assert dry["next_cursor"] is not None
    assert db_session.query(SubscriberSignalPublication).count() == 0
    assert db_session.query(AuditEvent).count() == audit_count

    first = backfill_missing_signal_publications(
        db_session,
        now=NOW,
        admin_user_id=admin_user_id,
        dry_run=False,
        limit=2,
    )
    second = backfill_missing_signal_publications(
        db_session,
        now=NOW,
        admin_user_id=admin_user_id,
        dry_run=False,
        limit=2,
        after_signal_id=first["next_cursor"],
    )
    assert first["created"] == 2
    assert second["created"] == 1
    assert db_session.query(SubscriberSignalPublication).count() == 3
    audits = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "signal_publication_backfill_requested")
        .order_by(AuditEvent.created_at.asc())
        .all()
    )
    assert len(audits) == 2
    assert all(audit.actor_admin_user_id == admin_user_id for audit in audits)


def test_retry_restrictions_do_not_regenerate_published_or_cancelled_signals(db_session):
    _plan_row, _channel, _mapping_row, signal, publication = _approved_publication(db_session)
    publication.status = SignalPublicationStatus.published
    publication.published_at = NOW
    db_session.commit()

    same = retry_signal_publication(
        db_session,
        publication_id=publication.id,
        admin_user_id=_admin_id(db_session),
        now=NOW,
    )
    assert same.status == SignalPublicationStatus.published

    publication.status = SignalPublicationStatus.cancelled
    signal.status = SubscriberSignalStatus.cancelled
    db_session.commit()
    with pytest.raises(ValueError):
        retry_signal_publication(
            db_session,
            publication_id=publication.id,
            admin_user_id=_admin_id(db_session),
            now=NOW,
        )


def test_telegram_publish_request_shape_and_errors(monkeypatch):
    from services.telegram_private_channel_service import (
        TelegramPrivateChannelService,
        TelegramPublishedMessage,
    )

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {"message_id": 123}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: FakeClient())

    result = asyncio.run(
        TelegramPrivateChannelService().publish_text_message(
            chat_id=-100123,
            text="AuroRatio signal",
        )
    )

    assert isinstance(result, TelegramPublishedMessage)
    assert result.provider_reference == "tg_message:123"
    assert captured["url"].endswith("/bot123:secret/sendMessage")
    assert captured["json"] == {
        "chat_id": -100123,
        "text": "AuroRatio signal",
        "disable_web_page_preview": True,
    }


def test_admin_can_inspect_publication_and_paginated_attempt_history(db_session):
    admin = _admin(db_session, email="admin-phase9-inspect@example.com")
    _plan_row, _channel_row, _mapping_row, _signal, publication = _approved_publication(db_session)
    first = SubscriberSignalDeliveryAttempt(
        signal_publication_id=publication.id,
        attempt_number=1,
        processing_claim_id="claim-1",
        outcome=SignalDeliveryAttemptOutcome.transient_failure,
        started_at=NOW,
        completed_at=NOW,
        error_code="telegram_provider_error",
        error_message="temporary failure",
        is_retryable=True,
        created_at=NOW,
    )
    second = SubscriberSignalDeliveryAttempt(
        signal_publication_id=publication.id,
        attempt_number=2,
        processing_claim_id="claim-2",
        outcome=SignalDeliveryAttemptOutcome.delivered,
        started_at=NOW + timedelta(minutes=1),
        completed_at=NOW + timedelta(minutes=1),
        telegram_chat_id=-1004352124491,
        telegram_message_id=42,
        provider_message_reference="tg_message:42",
        is_retryable=False,
        created_at=NOW + timedelta(minutes=1),
    )
    db_session.add_all([first, second])
    db_session.commit()

    def override_db():
        yield db_session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    detail = client.get(f"/admin/signal-publications/{publication.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == publication.id

    attempts = client.get(
        f"/admin/signal-publications/{publication.id}/attempts?limit=1",
        headers=headers,
    )
    assert attempts.status_code == 200
    assert [item["attempt_number"] for item in attempts.json()["items"]] == [2]
    assert attempts.json()["items"][0]["provider_message_reference"] == "tg_message:42"

    older = client.get(
        f"/admin/signal-publications/{publication.id}/attempts?before_attempt_number=2",
        headers=headers,
    )
    assert older.status_code == 200
    assert [item["attempt_number"] for item in older.json()["items"]] == [1]
    assert older.json()["items"][0]["error_code"] == "telegram_provider_error"

    missing = client.get("/admin/signal-publications/missing/attempts", headers=headers)
    assert missing.status_code == 404
    app.dependency_overrides.clear()


def test_manual_retry_audit_contains_previous_delivery_state(db_session):
    admin_user_id = _admin_id(db_session)
    _plan_row, _channel_row, _mapping_row, _signal, publication = _approved_publication(db_session)
    publication.status = SignalPublicationStatus.terminal_failure
    publication.attempt_count = 3
    publication.failed_at = NOW
    publication.last_error_code = "telegram_permanent_error"
    publication.last_error_message = "sanitized"
    db_session.commit()

    retried = retry_signal_publication(
        db_session,
        publication_id=publication.id,
        admin_user_id=admin_user_id,
        now=NOW + timedelta(minutes=5),
    )
    assert retried.status == SignalPublicationStatus.pending
    audit = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "signal_publication_manual_retry_requested")
        .order_by(AuditEvent.created_at.desc())
        .first()
    )
    assert audit.actor_admin_user_id == admin_user_id
    assert audit.event_metadata == {
        "previous_status": "terminal_failure",
        "attempt_count": 3,
        "next_attempt_at": (NOW + timedelta(minutes=5)).isoformat(),
    }


def test_manual_retry_rejects_pending_and_processing_publications(db_session):
    admin_user_id = _admin_id(db_session)
    _plan_row, _channel_row, _mapping_row, _signal, publication = _approved_publication(db_session)

    with pytest.raises(ValueError, match="already scheduled"):
        retry_signal_publication(
            db_session,
            publication_id=publication.id,
            admin_user_id=admin_user_id,
            now=NOW,
        )

    publication.status = SignalPublicationStatus.processing
    publication.processing_started_at = NOW
    publication.processing_claim_id = "active-claim"
    db_session.commit()

    with pytest.raises(ValueError, match="cannot be manually retried"):
        retry_signal_publication(
            db_session,
            publication_id=publication.id,
            admin_user_id=admin_user_id,
            now=NOW + timedelta(minutes=1),
        )

    db_session.refresh(publication)
    assert publication.status == SignalPublicationStatus.processing
    assert publication.processing_claim_id == "active-claim"
    assert publication.processing_started_at == NOW


def test_admin_publication_listing_filters_and_exposes_delivery_metadata(db_session):
    admin = _admin(db_session, email="admin-phase9-list@example.com")
    plan, channel, _mapping_row, signal, publication = _approved_publication(db_session)
    publication.status = SignalPublicationStatus.terminal_failure
    publication.attempt_count = 2
    publication.last_attempt_at = NOW
    publication.failed_at = NOW
    publication.telegram_chat_id = channel.telegram_chat_id
    publication.telegram_message_id = 77
    publication.last_error_code = "telegram_permanent_error"
    publication.last_error_message = "sanitized failure"
    db_session.commit()

    def override_db():
        yield db_session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(
        "/admin/signal-publications",
        params={
            "status": "terminal_failure",
            "signal_id": signal.id,
            "plan_id": plan.id,
            "limit": 1,
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_more"] is False
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"] == publication.id
    assert item["last_attempt_at"] == NOW.isoformat()
    assert item["telegram_chat_id"] == channel.telegram_chat_id
    assert item["telegram_message_id"] == 77
    assert item["last_error_message"] == "sanitized failure"

    no_match = client.get(
        "/admin/signal-publications",
        params={"signal_id": "missing"},
        headers=headers,
    )
    assert no_match.status_code == 200
    assert no_match.json() == {"items": [], "has_more": False}
    app.dependency_overrides.clear()
