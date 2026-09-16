import importlib
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

with patch.dict(
    sys.modules,
    {
        "schedule": SimpleNamespace(),
        "yfinance": SimpleNamespace(),
        "broker": SimpleNamespace(Broker=object),
        "pandas": SimpleNamespace(
            DataFrame=object,
            Timestamp=lambda value: value,
            concat=lambda values: values[0],
            read_csv=lambda *args, **kwargs: SimpleNamespace(index=[]),
        ),
    },
):
    standalone_scheduler = importlib.import_module("scheduler")
from database import get_db
from dependencies import create_access_token
from main import app
from models import MembershipLevel, TradingProvider, User
from routers.auth import pwd_context


def _override_database(db_session):
    def override():
        yield db_session

    return override


def _user(db_session, email: str, membership: MembershipLevel, *, active: bool) -> User:
    user = User(
        email=email,
        hashed_password=pwd_context.hash("phase-2-password"),
        membership_level=membership,
        is_active=active,
        preferred_trading_provider=TradingProvider.disabled,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/fa/users"),
        ("post", "/admin/fa/users/target-user/disable-trading"),
    ],
)
def test_fa_routes_require_authentication(method, path, db_session):
    app.dependency_overrides[get_db] = _override_database(db_session)
    try:
        response = getattr(TestClient(app), method)(path)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("membership", "active", "expected"),
    [
        (MembershipLevel.classic, True, 404),
        (MembershipLevel.aurum, False, 404),
        (MembershipLevel.aurum, True, 404),
    ],
)
def test_fa_read_requires_active_admin(
    membership,
    active,
    expected,
    db_session,
):
    caller = _user(db_session, f"read-{membership.value}-{active}@example.com", membership, active=active)
    app.dependency_overrides[get_db] = _override_database(db_session)
    try:
        response = TestClient(app).get("/admin/fa/users", headers=_headers(caller))
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == expected


@pytest.mark.parametrize(
    ("membership", "active", "expected"),
    [
        (MembershipLevel.classic, True, 404),
        (MembershipLevel.aurum, False, 404),
        (MembershipLevel.aurum, True, 404),
    ],
)
def test_fa_mutation_requires_active_admin(
    membership,
    active,
    expected,
    db_session,
):
    caller = _user(
        db_session,
        f"mutation-{membership.value}-{active}@example.com",
        membership,
        active=active,
    )
    target = _user(
        db_session,
        f"target-{membership.value}-{active}@example.com",
        MembershipLevel.classic,
        active=True,
    )
    app.dependency_overrides[get_db] = _override_database(db_session)
    try:
        response = TestClient(app).post(
            f"/admin/fa/users/{target.id}/disable-trading",
            headers=_headers(caller),
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == expected


def test_disabled_normal_scheduler_runs_timezone_aware_catch_up(monkeypatch):
    monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)
    monkeypatch.setattr(standalone_scheduler, "CSV_PATH", standalone_scheduler.__file__)
    monkeypatch.setattr(
        standalone_scheduler,
        "business_now",
        lambda: datetime(2026, 8, 13, 17, 6, tzinfo=standalone_scheduler.BUSINESS_TZ),
    )
    monkeypatch.setattr(
        standalone_scheduler.pd,
        "read_csv",
        lambda *args, **kwargs: SimpleNamespace(index=[]),
    )
    subscriber_cycles = []
    monkeypatch.setattr(
        standalone_scheduler,
        "refresh_persisted_market_snapshot",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(
        standalone_scheduler,
        "run_daily_cycle",
        lambda: pytest.fail("Compatibility wrapper should not be scheduled directly"),
    )
    monkeypatch.setattr(
        standalone_scheduler,
        "run_subscriber_signal_cycle",
        lambda: subscriber_cycles.append("subscriber"),
    )
    monkeypatch.setattr(
        standalone_scheduler.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with pytest.raises(KeyboardInterrupt):
        standalone_scheduler.start_scheduler()

    assert subscriber_cycles == ["subscriber"]


def test_disabled_now_entry_runs_subscriber_cycle_without_broker(monkeypatch):
    monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)
    calls = []
    monkeypatch.setattr(standalone_scheduler, "CSV_PATH", standalone_scheduler.__file__)
    monkeypatch.setattr(
        standalone_scheduler,
        "run_daily_cycle",
        lambda: pytest.fail("Compatibility wrapper should not be used by --now"),
    )
    monkeypatch.setattr(
        standalone_scheduler,
        "run_subscriber_signal_cycle",
        lambda: calls.append("subscriber"),
    )

    assert standalone_scheduler.main(["--now"]) == 0
    assert calls == ["subscriber"]


def test_scheduler_no_longer_exposes_legacy_broker_cycle():
    assert not hasattr(standalone_scheduler, "run_legacy_daily_cycle")
    assert "broker" not in standalone_scheduler.run_daily_cycle.__code__.co_names
    assert "broker" not in standalone_scheduler.run_subscriber_signal_cycle.__code__.co_names


def test_enabled_now_still_runs_subscriber_cycle(monkeypatch):
    monkeypatch.setenv("LEGACY_CUSTOMER_APP_ENABLED", "true")
    calls = []
    monkeypatch.setattr(standalone_scheduler, "CSV_PATH", standalone_scheduler.__file__)
    monkeypatch.setattr(standalone_scheduler, "run_daily_cycle", lambda: pytest.fail("Legacy cycle may not run"))
    monkeypatch.setattr(standalone_scheduler, "run_subscriber_signal_cycle", lambda: calls.append("subscriber"))

    assert standalone_scheduler.main(["--now"]) == 0
    assert calls == ["subscriber"]


def test_enabled_normal_scheduler_runs_same_timezone_aware_catch_up(monkeypatch):
    monkeypatch.setenv("LEGACY_CUSTOMER_APP_ENABLED", "true")
    cycles = []
    startup_refreshes = []
    monkeypatch.setattr(standalone_scheduler, "CSV_PATH", standalone_scheduler.__file__)
    monkeypatch.setattr(
        standalone_scheduler,
        "business_now",
        lambda: datetime(2026, 8, 13, 17, 6, tzinfo=standalone_scheduler.BUSINESS_TZ),
    )
    monkeypatch.setattr(
        standalone_scheduler.pd,
        "read_csv",
        lambda *args, **kwargs: SimpleNamespace(index=[]),
    )
    monkeypatch.setattr(
        standalone_scheduler,
        "refresh_persisted_market_snapshot",
        lambda: startup_refreshes.append("market"),
    )
    monkeypatch.setattr(standalone_scheduler, "run_daily_cycle", lambda: pytest.fail("Legacy cycle may not run"))
    monkeypatch.setattr(standalone_scheduler, "run_subscriber_signal_cycle", lambda: cycles.append("subscriber"))
    monkeypatch.setattr(
        standalone_scheduler.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with pytest.raises(KeyboardInterrupt):
        standalone_scheduler.start_scheduler()

    assert cycles == ["subscriber"]
    assert startup_refreshes == ["market"]
