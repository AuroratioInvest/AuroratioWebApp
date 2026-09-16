from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.commands import create_test_signal as command
from database import get_db
from main import app
from models import User
from services.subscriber_signal_publication_service import (
    create_operational_test_signal,
)
from subscriber_models import (
    AuditEvent,
    PlanChannelMapping,
    SubscriberSignal,
    SubscriberSignalPlanTarget,
    SubscriberSignalPublication,
    SubscriberSignalStatus,
    SubscriptionPlan,
    TelegramChannel,
)


NOW = datetime(2026, 8, 3, 17, 5, tzinfo=timezone.utc)


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


def _channel(db, *, active=True, configured=True, chat_id=-1004352124491):
    row = TelegramChannel(
        code="signals",
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


def _service_for_session(db_session):
    return SimpleNamespace(
        SessionLocal=lambda: db_session,
        create_operational_test_signal=create_operational_test_signal,
    )


def test_command_refuses_production_before_loading_service(monkeypatch, capsys):
    loaded = []
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr(command, "_load_signal_service", lambda: loaded.append(True))

    assert command.main(["--plan-code", "monthly-signals"]) == 2

    assert loaded == []
    assert "disabled in production" in capsys.readouterr().err


def test_command_creates_approved_test_signal_without_legacy_user(
    db_session,
    monkeypatch,
    capsys,
):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    plan = _plan(db_session)
    _mapping(db_session, plan, _channel(db_session))
    monkeypatch.setattr(command, "_load_signal_service", lambda: _service_for_session(db_session))

    assert command.main(["--plan-code", "monthly-signals"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["created"] is True
    assert payload["status"] == "approved"
    assert payload["publications_enqueued"] == 1
    assert payload["plan_code"] == "monthly-signals"
    assert "telegram" not in json.dumps(payload).lower()
    assert "chat" not in json.dumps(payload).lower()
    assert db_session.query(User).count() == 0
    signal = db_session.get(SubscriberSignal, payload["signal_id"])
    assert signal.status == SubscriberSignalStatus.approved
    assert signal.symbol == "TEST"
    assert signal.entry == "Test signal — do not trade"
    assert signal.stop_loss == "Not applicable"
    assert signal.take_profit_targets == ["Not applicable"]
    assert signal.analysis == "Operational delivery test only. Do not trade."
    assert signal.created_by_admin_user_id is None
    assert signal.approved_by_admin_user_id is None
    assert db_session.query(SubscriberSignalPlanTarget).count() == 1
    assert db_session.query(SubscriberSignalPublication).count() == 1
    assert (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "operational_test_signal_created")
        .count()
        == 1
    )


def test_command_is_idempotent_for_same_test_id(db_session, monkeypatch, capsys):
    plan = _plan(db_session)
    _mapping(db_session, plan, _channel(db_session))
    monkeypatch.setattr(command, "_load_signal_service", lambda: _service_for_session(db_session))

    assert command.main(["--plan-code", "monthly-signals", "--test-id", "local-check"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert command.main(["--plan-code", "monthly-signals", "--test-id", "local-check"]) == 0
    second = json.loads(capsys.readouterr().out)

    assert first["signal_id"] == second["signal_id"]
    assert second["created"] is False
    assert db_session.query(SubscriberSignal).count() == 1
    assert db_session.query(SubscriberSignalPublication).count() == 1


def test_command_dry_run_is_write_free(db_session, monkeypatch, capsys):
    plan = _plan(db_session)
    _mapping(db_session, plan, _channel(db_session))
    audit_count = db_session.query(AuditEvent).count()
    monkeypatch.setattr(command, "_load_signal_service", lambda: _service_for_session(db_session))

    assert command.main(["--plan-code", "monthly-signals", "--dry-run"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["signal_id"] is None
    assert payload["would_enqueue_publications"] == 1
    assert db_session.query(SubscriberSignal).count() == 0
    assert db_session.query(SubscriberSignalPublication).count() == 0
    assert db_session.query(AuditEvent).count() == audit_count


def test_unknown_inactive_or_unconfigured_plan_rejected(db_session):
    cases = [
        ("missing", {}),
        ("inactive", {"active": False}),
        ("unconfigured", {"configured": False}),
        ("archived", {"archived": True}),
    ]
    for plan_code, kwargs in cases:
        if kwargs:
            _plan(db_session, code=plan_code, **kwargs)
        result = create_operational_test_signal
        try:
            result(
                db_session,
                plan_code=plan_code,
                test_id="default",
                dry_run=False,
                now=NOW,
            )
        except ValueError as exc:
            assert "plan is unavailable" in str(exc)
        else:
            raise AssertionError("invalid plan unexpectedly accepted")
        db_session.rollback()


def test_command_does_not_call_provider(db_session, monkeypatch):
    plan = _plan(db_session)
    _mapping(db_session, plan, _channel(db_session))

    def provider_should_not_be_constructed(*args, **kwargs):
        raise AssertionError("provider must not be called by test signal command")

    from services import subscriber_signal_publication_service as publication_service

    monkeypatch.setattr(
        publication_service,
        "TelegramPrivateChannelService",
        provider_should_not_be_constructed,
    )
    monkeypatch.setattr(command, "_load_signal_service", lambda: _service_for_session(db_session))

    assert command.main(["--plan-code", "monthly-signals"]) == 0


def test_command_fatal_failure_is_sanitized_and_closes_session(monkeypatch, capsys):
    class FakeSession:
        def __init__(self):
            self.closed = False
            self.rolled_back = False

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = FakeSession()

    def fail(*args, **kwargs):
        raise RuntimeError("secret-token provider payload")

    service = SimpleNamespace(
        SessionLocal=lambda: session,
        create_operational_test_signal=fail,
    )
    monkeypatch.setattr(command, "_load_signal_service", lambda: service)

    assert command.main(["--plan-code", "monthly-signals"]) == 1

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "test signal creation failed" in combined
    assert "secret-token" not in combined
    assert "provider payload" not in combined
    assert session.rolled_back is True
    assert session.closed is True


def test_no_public_or_admin_endpoint_added_for_test_signal():
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/public/test-signal" not in paths
    assert "/admin/test-signal" not in paths
    assert "/admin/create-test-signal" not in paths
