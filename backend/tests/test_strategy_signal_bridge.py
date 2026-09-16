from __future__ import annotations

import asyncio
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from market_data import (
    MarketDataValidationError,
    MarketObservation,
    validate_strategy_observations,
)
from services import strategy_signal_bridge_service as bridge_service
from services.strategy_signal_bridge_service import (
    ingest_confirmed_strategy_decision,
    strategy_identity,
)
from services.subscriber_signal_publication_service import process_due_signal_publications
from strategy_decisions import (
    STRATEGY_IDENTIFIER,
    STRATEGY_VERSION,
    StrategyDecisionCandidate,
    evaluate_confirmed_strategy_decisions,
)
from subscriber_models import (
    AuditEvent,
    PlanChannelMapping,
    SignalPublicationStatus,
    SubscriberSignal,
    SubscriberSignalDirection,
    SubscriberSignalPublication,
    SubscriberSignalStatus,
    SubscriptionPlan,
    TelegramChannel,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]
PHASE_9_REVISION = "c3d9e1f7a204"
STRATEGY_REVISION = "e5a9c1d2b340"
NOW = datetime(2026, 8, 3, 17, 5, tzinfo=timezone.utc)


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _config() -> dict:
    return {
        "security_limits": {"trade_delay_days": 2},
        "ratios": {
            "silver": {"buy": 80.0, "sell": 40.0},
            "platinum": {"buy": 2.0, "sell": 0.45},
            "palladium": {"buy": 4.0, "sell": 0.9},
        },
    }


def _state(position: str = "GOLD") -> dict:
    return {
        "module1": {"position": position, "silver_days": 0, "history": []},
        "module2": {"position": "GOLD", "platinum_days": 0, "history": []},
        "module3": {"position": "GOLD", "palladium_days": 0, "history": []},
    }


def _prices(*, silver_ratio: Decimal = Decimal("80.0")) -> pd.DataFrame:
    xau = Decimal("2400.0")
    xag = xau / silver_ratio
    return pd.DataFrame(
        [
            {
                "XAU": float(xau),
                "XAG": float(xag),
                "XPT": 1300.0,
                "XPD": 900.0,
                "USDCHF": 0.91,
            },
            {
                "XAU": float(xau),
                "XAG": float(xag),
                "XPT": 1300.0,
                "XPD": 900.0,
                "USDCHF": 0.91,
            },
        ],
        index=pd.to_datetime(["2026-08-02", "2026-08-03"]),
    )


def _candidate(
    *,
    ratio_identifier: str = "AU_AG",
    decision_date: date = date(2026, 8, 3),
    decision_type: str = "GOLD_TO_SILVER",
    from_metal: str = "GOLD",
    to_metal: str = "SILVER",
) -> StrategyDecisionCandidate:
    return StrategyDecisionCandidate(
        strategy_identifier=STRATEGY_IDENTIFIER,
        strategy_version=STRATEGY_VERSION,
        module="module1",
        ratio_identifier=ratio_identifier,
        decision_date=decision_date,
        source_data_timestamp=NOW,
        from_metal=from_metal,
        to_metal=to_metal,
        decision_type=decision_type,
        ratio_value=Decimal("80.1234"),
        prices=MappingProxyType(
            {
                "XAU": Decimal("2400"),
                "XAG": Decimal("29.95"),
                "XPT": Decimal("1200"),
                "XPD": Decimal("900"),
                "USDCHF": Decimal("0.91"),
            }
        ),
        consecutive_days=2,
    )


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


def _session_factory(db_session):
    return sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)


def test_existing_ratio_confirmation_logic_is_preserved():
    state = _state()
    first_state, first_decisions, _ = evaluate_confirmed_strategy_decisions(
        _prices(),
        state=state,
        config=_config(),
        decision_date=date(2026, 8, 2),
        source_data_timestamp=NOW,
    )
    assert first_decisions == []
    assert first_state["module1"]["silver_days"] == 1

    second_state, second_decisions, ratios = evaluate_confirmed_strategy_decisions(
        _prices(),
        state=first_state,
        config=_config(),
        decision_date=date(2026, 8, 3),
        source_data_timestamp=NOW,
    )
    assert second_state["module1"]["silver_days"] == 2
    assert ratios["AU_AG"] == Decimal("80.0")
    assert len(second_decisions) == 1
    assert second_decisions[0].from_metal == "GOLD"
    assert second_decisions[0].to_metal == "SILVER"
    assert second_decisions[0].ratio_identifier == "AU_AG"


def test_non_qualifying_day_resets_existing_counter():
    state = _state()
    state["module1"]["silver_days"] = 1
    updated_state, decisions, _ = evaluate_confirmed_strategy_decisions(
        _prices(silver_ratio=Decimal("79.99")),
        state=state,
        config=_config(),
        decision_date=date(2026, 8, 3),
        source_data_timestamp=NOW,
    )
    assert decisions == []
    assert updated_state["module1"]["silver_days"] == 0


def test_market_data_validation_rejects_missing_stale_incompatible_and_malformed_data():
    observations = {
        instrument: MarketObservation(
            instrument=instrument,
            price=Decimal("2400") if instrument == "XAU" else Decimal("30"),
            source_timestamp=NOW,
            retrieved_at=NOW,
            currency="USD" if instrument != "USDCHF" else "CHF_PER_USD",
            unit="troy_ounce" if instrument != "USDCHF" else "fx_rate",
            source="test",
        )
        for instrument in ["XAU", "XAG", "XPT", "XPD", "USDCHF"]
    }
    assert validate_strategy_observations(observations, now=NOW)["XAU"] == Decimal("2400")

    missing = dict(observations)
    missing.pop("XPD")
    with pytest.raises(MarketDataValidationError):
        validate_strategy_observations(missing, now=NOW)

    stale = dict(observations)
    stale["XAU"] = MarketObservation(
        **{**stale["XAU"].__dict__, "source_timestamp": NOW - timedelta(days=10)}
    )
    with pytest.raises(MarketDataValidationError):
        validate_strategy_observations(stale, now=NOW)

    incompatible = dict(observations)
    incompatible["XAG"] = MarketObservation(
        **{**incompatible["XAG"].__dict__, "currency": "EUR"}
    )
    with pytest.raises(MarketDataValidationError):
        validate_strategy_observations(incompatible, now=NOW)

    malformed = dict(observations)
    malformed["XPT"] = MarketObservation(**{**malformed["XPT"].__dict__, "price": Decimal("-1")})
    with pytest.raises(MarketDataValidationError):
        validate_strategy_observations(malformed, now=NOW)


def test_strategy_decision_auto_approves_and_enqueues_publication(db_session, monkeypatch):
    monkeypatch.setenv("MONTHLY_SIGNAL_PLAN_CODE", "monthly-signals")
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)

    result = ingest_confirmed_strategy_decision(
        db_session,
        candidate=_candidate(),
        now=NOW,
    )

    signal = db_session.get(SubscriberSignal, result.signal_id)
    assert result.created is True
    assert result.publications_enqueued == 1
    assert signal.status == SubscriberSignalStatus.approved
    assert signal.approved_by_admin_user_id is None
    assert signal.strategy_identity == strategy_identity(_candidate())
    assert signal.symbol == "AU_AG:SILVER"
    assert signal.direction == SubscriberSignalDirection.buy
    assert "manual evaluation and execution" in signal.analysis
    assert "threshold" not in signal.analysis.lower()
    assert db_session.query(SubscriberSignalPublication).count() == 1
    assert db_session.query(SubscriberSignalPublication).one().status == SignalPublicationStatus.pending
    assert (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "strategy_signal_auto_approved")
        .count()
        == 1
    )


def test_strategy_ingestion_does_not_call_provider_during_persistence(
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("MONTHLY_SIGNAL_PLAN_CODE", "monthly-signals")
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)

    def provider_should_not_be_constructed():
        raise AssertionError("provider delivery must not run during persistence")

    from services import subscriber_signal_publication_service as publication_service

    monkeypatch.setattr(
        publication_service,
        "TelegramPrivateChannelService",
        provider_should_not_be_constructed,
    )

    result = ingest_confirmed_strategy_decision(db_session, candidate=_candidate(), now=NOW)

    assert result.created is True
    assert db_session.query(SubscriberSignalPublication).count() == 1


def test_strategy_ingestion_rolls_back_when_publication_enqueue_fails(
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("MONTHLY_SIGNAL_PLAN_CODE", "monthly-signals")
    plan = _plan(db_session)
    _mapping(db_session, plan, _channel(db_session))

    def fail_enqueue(*args, **kwargs):
        raise RuntimeError("simulated enqueue failure")

    monkeypatch.setattr(bridge_service, "enqueue_publications_for_signal", fail_enqueue)

    with pytest.raises(RuntimeError):
        ingest_confirmed_strategy_decision(db_session, candidate=_candidate(), now=NOW)

    assert db_session.query(SubscriberSignal).count() == 0
    assert db_session.query(SubscriberSignalPublication).count() == 0
    assert db_session.query(AuditEvent).count() == 0


def test_strategy_decision_ingestion_is_idempotent_and_conflicts_fail(db_session, monkeypatch):
    monkeypatch.setenv("MONTHLY_SIGNAL_PLAN_CODE", "monthly-signals")
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    candidate = _candidate()

    first = ingest_confirmed_strategy_decision(db_session, candidate=candidate, now=NOW)
    second = ingest_confirmed_strategy_decision(db_session, candidate=candidate, now=NOW)

    assert first.signal_id == second.signal_id
    assert second.created is False
    assert db_session.query(SubscriberSignal).count() == 1
    assert db_session.query(SubscriberSignalPublication).count() == 1

    signal = db_session.get(SubscriberSignal, first.signal_id)
    signal.entry = "Conflicting canonical content"
    db_session.commit()
    with pytest.raises(ValueError):
        ingest_confirmed_strategy_decision(db_session, candidate=candidate, now=NOW)


def test_integration_derives_targets_from_trusted_active_plans(db_session, monkeypatch):
    monkeypatch.setenv("SUBSCRIBER_SIGNAL_PLAN_CODES", "monthly-signals,inactive")
    active = _plan(db_session, code="monthly-signals")
    _plan(db_session, code="inactive", active=False)
    _mapping(db_session, active, _channel(db_session))

    with pytest.raises(ValueError):
        ingest_confirmed_strategy_decision(db_session, candidate=_candidate(), now=NOW)


def test_existing_durable_publication_processor_delivers_later(db_session, monkeypatch):
    monkeypatch.setenv("MONTHLY_SIGNAL_PLAN_CODE", "monthly-signals")
    plan = _plan(db_session)
    channel = _channel(db_session)
    _mapping(db_session, plan, channel)
    ingest_confirmed_strategy_decision(db_session, candidate=_candidate(), now=NOW)

    from services import subscriber_signal_publication_service as publication_service

    class FakePublisher:
        def __init__(self):
            self.messages = []

        async def publish_text_message(self, *, chat_id: int, text: str):
            self.messages.append((chat_id, text))
            from services.telegram_private_channel_service import TelegramPublishedMessage

            return TelegramPublishedMessage(provider_reference="message:1", message_id=1)

    fake = FakePublisher()
    monkeypatch.setattr(
        publication_service,
        "TelegramPrivateChannelService",
        lambda: fake,
    )

    result = asyncio.run(
        process_due_signal_publications(
            limit=1,
            now=NOW,
            session_factory=_session_factory(db_session),
        )
    )

    assert result.published == 1
    assert len(fake.messages) == 1
    assert "making your own investment decisions" in fake.messages[0][1]


def test_strategy_identity_migration_round_trip_and_constraints(tmp_path, monkeypatch):
    database_path = tmp_path / "strategy-identity.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _alembic_config(database_url)

    command.upgrade(config, PHASE_9_REVISION)
    command.upgrade(config, STRATEGY_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        signal_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='subscriber_signals'"
        ).fetchone()[0]
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list('subscriber_signals')")
        }
        assert "strategy_identity" in signal_sql
        assert "ck_subscriber_signal_strategy_identity_nonempty" in signal_sql
        assert "ix_subscriber_signals_strategy_lookup" in indexes
        connection.execute(
            """
            INSERT INTO subscriber_signals (
                id, status, symbol, direction, entry, stop_loss, take_profit_targets,
                strategy_identity, strategy_decision_date, created_at, updated_at
            ) VALUES (
                'strategy-signal-1', 'approved', 'AU_AG:SILVER', 'buy',
                'entry', 'stop', '["target"]', 'strategy-id', '2026-08-03',
                '2026-08-03 17:05:00+00:00', '2026-08-03 17:05:00+00:00'
            )
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_signals (
                    id, status, symbol, direction, entry, stop_loss, take_profit_targets,
                    strategy_identity, strategy_decision_date, created_at, updated_at
                ) VALUES (
                    'strategy-signal-2', 'approved', 'AU_AG:SILVER', 'buy',
                    'entry', 'stop', '["target"]', 'strategy-id', '2026-08-03',
                    '2026-08-03 17:05:00+00:00', '2026-08-03 17:05:00+00:00'
                )
                """
            )
    finally:
        connection.close()

    command.downgrade(config, PHASE_9_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info('subscriber_signals')")
        }
        alembic_revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    finally:
        connection.close()
    assert "strategy_identity" not in columns
    assert alembic_revision == PHASE_9_REVISION

    command.upgrade(config, "head")
    command.check(config)
