from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app
from market_data import MarketObservation
from market_models import MarketPriceSnapshot
from routers import market as market_router
from services.market_data_service import store_validated_market_prices


NOW = datetime(2026, 8, 13, 15, 5, tzinfo=timezone.utc)
PRICES = {
    "XAU": Decimal("3350.25"),
    "XAG": Decimal("38.75"),
    "XPT": Decimal("1410.50"),
    "XPD": Decimal("1225.75"),
    "USDCHF": Decimal("0.8125"),
}


def _override_database(db_session):
    def override():
        yield db_session

    return override


def _store(db_session, *, prices=PRICES, source_timestamp=NOW):
    return store_validated_market_prices(
        db_session,
        prices=prices,
        source_timestamp=source_timestamp,
        retrieved_at=NOW + timedelta(minutes=1),
        source="test_provider",
    )


def _observations():
    return {
        instrument: MarketObservation(
            instrument=instrument,
            price=price,
            source_timestamp=NOW,
            retrieved_at=NOW + timedelta(minutes=1),
            currency="USD" if instrument != "USDCHF" else "CHF_PER_USD",
            unit="troy_ounce" if instrument != "USDCHF" else "fx_rate",
            source="test_provider",
        )
        for instrument, price in PRICES.items()
    }


def _freeze_market_validation_clock(monkeypatch):
    import market_data

    class FixtureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = NOW + timedelta(minutes=1)
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)

    # Keep the real freshness/currency/unit validation; align only its clock
    # with the historical fixture used by these scheduler integration tests.
    monkeypatch.setattr(market_data, "datetime", FixtureClock)


def test_market_data_returns_explicit_error_without_valid_snapshot(db_session, monkeypatch):
    monkeypatch.setenv("MARKET_DATA_LOCAL_FILE_FALLBACK", "false")
    app.dependency_overrides[get_db] = _override_database(db_session)
    try:
        response = TestClient(app).get("/market/data")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "No validated market data is available"}


def test_sqlite_local_development_falls_back_to_valid_root_csv(
    db_session,
    monkeypatch,
    tmp_path,
):
    prices_file = tmp_path / "prices_clean.csv"
    prices_file.write_text(
        "Date,XAU,XAG,XPT,XPD,USDCHF\n"
        "2026-08-12,3300,37,1400,1200,0.81\n"
        "2026-08-13,3350,38,1410,1225,0.8125\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MARKET_DATA_LOCAL_FILE_FALLBACK", "true")
    monkeypatch.setattr(market_router, "ROOT_PRICES_FILE", prices_file)
    app.dependency_overrides[get_db] = _override_database(db_session)
    try:
        response = TestClient(app).get("/market/data")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["metals"]["gold"]["priceUSD"] == 3350
    assert payload["metals"]["gold"]["change24h"] == 50


def test_postgresql_never_uses_local_file_fallback(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_LOCAL_FILE_FALLBACK", "true")
    fake_db = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )

    assert market_router._local_file_fallback_enabled(fake_db) is False


def test_market_data_returns_persisted_non_zero_prices_with_existing_contract(db_session):
    previous_prices = {key: value * Decimal("0.99") for key, value in PRICES.items()}
    _store(
        db_session,
        prices=previous_prices,
        source_timestamp=NOW - timedelta(days=1),
    )
    _store(db_session)
    app.dependency_overrides[get_db] = _override_database(db_session)

    try:
        response = TestClient(app).get("/market/data")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"metals", "ratios", "signal", "signalMetal"}
    assert set(payload["metals"]) == {"gold", "silver", "platinum", "palladium"}
    assert set(payload["ratios"]) == {"AU_AG", "AU_PT", "AU_PD"}
    for metal in payload["metals"].values():
        assert set(metal) == {
            "symbol",
            "name",
            "priceUSD",
            "priceCHF",
            "priceEUR",
            "change24h",
            "changePercent",
            "performance",
        }
        assert metal["priceUSD"] > 0
        assert metal["priceCHF"] > 0
        assert metal["priceEUR"] > 0
        assert metal["change24h"] > 0
    assert payload["metals"]["gold"]["priceUSD"] == float(PRICES["XAU"])
    assert payload["ratios"]["AU_AG"] == float(PRICES["XAU"] / PRICES["XAG"])


def test_scheduler_persistence_helper_writes_and_updates_validated_snapshot(db_session):
    import scheduler

    observations = _observations()
    session_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
    )

    database_dialect = scheduler.persist_validated_market_prices(
        observations,
        PRICES,
        session_factory=session_factory,
    )
    updated = dict(PRICES)
    updated["XAU"] = Decimal("3400.00")
    scheduler.persist_validated_market_prices(
        observations,
        updated,
        session_factory=session_factory,
    )

    db_session.expire_all()
    assert db_session.query(MarketPriceSnapshot).count() == 1
    assert database_dialect == "sqlite"
    assert db_session.query(MarketPriceSnapshot).one().xau_usd == Decimal("3400.0000000000")


def test_scheduler_startup_refresh_fetches_validates_and_persists_idempotently(
    db_session,
    monkeypatch,
):
    import scheduler

    _freeze_market_validation_clock(monkeypatch)
    observations = _observations()
    provider_calls = []
    monkeypatch.setattr(
        scheduler,
        "YahooFinanceMarketDataProvider",
        lambda: SimpleNamespace(
            latest_observations=lambda: provider_calls.append("fetch") or observations
        ),
    )
    session_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
    )

    scheduler.refresh_persisted_market_snapshot(session_factory=session_factory)
    scheduler.refresh_persisted_market_snapshot(session_factory=session_factory)

    db_session.expire_all()
    snapshot = db_session.query(MarketPriceSnapshot).one()
    assert provider_calls == ["fetch", "fetch"]
    assert snapshot.source_timestamp.replace(tzinfo=timezone.utc) == NOW
    assert snapshot.xau_usd == Decimal("3350.2500000000")
    assert snapshot.xag_usd == Decimal("38.7500000000")
    assert snapshot.xpt_usd == Decimal("1410.5000000000")
    assert snapshot.xpd_usd == Decimal("1225.7500000000")
    assert snapshot.usd_chf == Decimal("0.8125000000")
    assert db_session.query(MarketPriceSnapshot).count() == 1


def test_scheduler_market_write_failure_does_not_interrupt_signal_workflow(monkeypatch):
    import scheduler

    _freeze_market_validation_clock(monkeypatch)
    observations = _observations()
    monkeypatch.setattr(
        scheduler,
        "YahooFinanceMarketDataProvider",
        lambda: SimpleNamespace(latest_observations=lambda: observations),
    )
    monkeypatch.setattr(scheduler, "load_config", lambda: {})
    monkeypatch.setattr(
        scheduler,
        "persist_validated_market_prices",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    workflow = []
    frame = pd.DataFrame([dict(PRICES)], index=pd.to_datetime(["2026-08-13"]))
    monkeypatch.setattr(
        scheduler,
        "update_prices_csv",
        lambda prices: workflow.append("csv") or frame,
    )
    monkeypatch.setattr(scheduler, "load_state", lambda: {})
    monkeypatch.setattr(
        scheduler,
        "evaluate_confirmed_strategy_decisions",
        lambda *args, **kwargs: (workflow.append("strategy") or {}, [], {}),
    )
    monkeypatch.setattr(scheduler, "save_state", lambda state: workflow.append("state"))

    assert scheduler.run_subscriber_signal_cycle() == 0
    assert workflow == ["csv", "strategy", "state"]


def test_backtest_results_are_packaged_and_keep_existing_contract():
    response = TestClient(app).get("/market/backtest/results")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    payload = response.json()
    assert payload["finalValueCHF"] == 14912254.21571844
    assert payload["initialValueCHF"] == 300000.0
    assert payload["totalSwitches"] == 6
    assert payload["modules"]["goldSilver"]["finalValue"] == 4502687.374867869
    assert payload["modules"]["goldPlatinum"]["finalValue"] == 1485778.2946352428
    assert payload["modules"]["goldPalladium"]["finalValue"] == 8923788.54621533
    assert payload["modules"]["goldSilver"]["name"] == "Gold ↔ Silver"
    assert payload["modules"]["goldPlatinum"]["name"] == "Gold ↔ Platinum"
    assert payload["modules"]["goldPalladium"]["name"] == "Gold ↔ Palladium"
    assert payload["timeframe"] == {"start": "2000", "end": "2025"}
    artifact = market_router.BACKTEST_RESULTS_FILE.read_bytes()
    assert "↔".encode("utf-8") in artifact
    assert b"\\u2194" not in artifact


def test_market_snapshot_migration_applies_to_existing_schema(tmp_path, monkeypatch):
    database_path = tmp_path / "market-data.db"
    database_url = f"sqlite:///{database_path}"
    actual_backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(actual_backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(actual_backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert "market_price_snapshots" in Base.metadata.tables
    command.upgrade(config, "4d2a7151abb7")

    from sqlalchemy import create_engine

    migrated_engine = create_engine(database_url)
    try:
        assert "market_price_snapshots" not in inspect(migrated_engine).get_table_names()
        command.upgrade(config, "head")
        columns = {
            column["name"]
            for column in inspect(migrated_engine).get_columns("market_price_snapshots")
        }
        command.downgrade(config, "4d2a7151abb7")
        assert "market_price_snapshots" not in inspect(migrated_engine).get_table_names()
        command.upgrade(config, "head")
        command.check(config)
    finally:
        migrated_engine.dispose()
    assert columns == {
        "source_timestamp",
        "retrieved_at",
        "source",
        "xau_usd",
        "xag_usd",
        "xpt_usd",
        "xpd_usd",
        "usd_chf",
        "created_at",
    }
