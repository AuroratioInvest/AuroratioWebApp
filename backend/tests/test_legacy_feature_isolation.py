import pytest
from fastapi.testclient import TestClient

from core.features import (
    legacy_customer_app_enabled,
    parse_boolean_flag,
)
from database import get_db
from dependencies import get_active_user
from main import app
from models import (
    BrokerConnection,
    ConnectionStatus,
    ExecutionLog,
    ExecutionStatus,
    MembershipLevel,
    Position,
    Subscription,
    SubscriptionStatus,
    TradingProvider,
    User,
)
from routers.auth import pwd_context
from services import website_execution_scheduler


def _override_database(db_session):
    def override():
        yield db_session

    return override


def _legacy_user(db_session, *, admin: bool = False) -> User:
    user = User(
        email="admin@example.com" if admin else "legacy@example.com",
        hashed_password=pwd_context.hash("phase-2-password"),
        membership_level=MembershipLevel.aurum if admin else MembershipLevel.classic,
        is_active=True,
        preferred_trading_provider=TradingProvider.disabled,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_feature_defaults_to_disabled_and_parses_common_true_values(monkeypatch):
    monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)

    assert legacy_customer_app_enabled() is False
    assert parse_boolean_flag(None) is False
    assert parse_boolean_flag("") is False
    assert parse_boolean_flag("false") is False
    assert parse_boolean_flag("0") is False

    for value in ("1", "true", "TRUE", " yes ", "on", "ON"):
        assert parse_boolean_flag(value) is True


def test_legacy_customer_endpoint_is_hidden_when_disabled(monkeypatch, db_session):
    monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)
    app.dependency_overrides[get_db] = _override_database(db_session)

    try:
        response = TestClient(app).get("/portfolio/snapshots")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_enabling_feature_does_not_restore_unregistered_legacy_endpoint(monkeypatch, db_session):
    monkeypatch.setenv("LEGACY_CUSTOMER_APP_ENABLED", "true")
    user = _legacy_user(db_session)
    app.dependency_overrides[get_db] = _override_database(db_session)
    app.dependency_overrides[get_active_user] = lambda: user

    try:
        response = TestClient(app).get("/portfolio/snapshots")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("configured_value", [None, "false"])
def test_legacy_stripe_plan_route_is_hidden_unless_explicitly_enabled(
    monkeypatch,
    configured_value,
):
    if configured_value is None:
        monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)
    else:
        monkeypatch.setenv("LEGACY_CUSTOMER_APP_ENABLED", configured_value)

    response = TestClient(app).get("/stripe/plan")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_legacy_stripe_plan_route_remains_unregistered_even_when_enabled(monkeypatch):
    monkeypatch.setenv("LEGACY_CUSTOMER_APP_ENABLED", "true")
    monkeypatch.setenv("SUBSCRIPTION_PRICE", "49")
    monkeypatch.setenv("SUBSCRIPTION_CURRENCY", "EUR")
    monkeypatch.setenv("SUBSCRIPTION_INTERVAL", "month")

    response = TestClient(app).get("/stripe/plan")

    assert response.status_code == 404


def test_disabled_requests_do_not_modify_legacy_records(monkeypatch, db_session):
    monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)
    user = _legacy_user(db_session)
    subscription = Subscription(
        user_id=user.id,
        stripe_customer_id="cus_phase_2",
        stripe_subscription_id="sub_phase_2",
        status=SubscriptionStatus.active,
    )
    connection = BrokerConnection(
        user_id=user.id,
        broker_name="Legacy Broker",
        status=ConnectionStatus.active,
        is_active=True,
    )
    db_session.add_all([subscription, connection])
    db_session.flush()
    db_session.add(
        Position(
            user_id=user.id,
            broker_connection_id=connection.id,
            metal="GOLD",
            etf_symbol="SGLN",
            quantity=2,
        )
    )
    db_session.add(
        ExecutionLog(
            user_id=user.id,
            provider=TradingProvider.ibkr_fa,
            module_name="M1",
            order_id="legacy-order",
            dry_run=False,
            status=ExecutionStatus.success,
        )
    )
    db_session.commit()

    before = {
        "users": db_session.query(User).count(),
        "subscriptions": db_session.query(Subscription).count(),
        "brokers": db_session.query(BrokerConnection).count(),
        "positions": db_session.query(Position).count(),
        "executions": db_session.query(ExecutionLog).count(),
    }
    app.dependency_overrides[get_db] = _override_database(db_session)

    try:
        client = TestClient(app)
        assert client.get("/broker/connections").status_code == 404
        assert client.get("/portfolio/positions").status_code == 404
        assert client.post("/execution/run-me").status_code == 404
    finally:
        app.dependency_overrides.clear()

    after = {
        "users": db_session.query(User).count(),
        "subscriptions": db_session.query(Subscription).count(),
        "brokers": db_session.query(BrokerConnection).count(),
        "positions": db_session.query(Position).count(),
        "executions": db_session.query(ExecutionLog).count(),
    }
    assert after == before


def test_minimal_launch_routes_are_registered_without_customer_app():
    def collect_paths(routes):
        paths = set()
        for route in routes:
            path = getattr(route, "path", None)
            if path is not None:
                paths.add(path)
            nested = getattr(route, "original_router", None)
            include_context = getattr(route, "include_context", None)
            prefix = getattr(include_context, "prefix", "") or ""
            if nested is not None:
                for nested_path in collect_paths(nested.routes):
                    paths.add(f"{prefix}{nested_path}")
        return paths

    paths = collect_paths(app.routes)

    assert "/public/billing/checkout-session" in paths
    assert "/stripe/webhook" in paths
    assert "/contact" in paths
    assert "/market/data" in paths
    assert "/market/backtest/results" in paths

    assert "/auth/login" not in paths
    assert "/auth/signup" not in paths
    assert "/portfolio/snapshots" not in paths
    assert "/broker/connections" not in paths
    assert "/execution/run-now" not in paths
    assert "/trades" not in paths
    assert "/admin/fa/users" not in paths


def test_customer_authentication_route_is_not_registered(monkeypatch, db_session):
    monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)
    _legacy_user(db_session, admin=True)
    app.dependency_overrides[get_db] = _override_database(db_session)

    try:
        client = TestClient(app)
        response = client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "phase-2-password"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_non_admin_login_is_unregistered(
    monkeypatch,
    db_session,
):
    monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)
    _legacy_user(db_session)
    app.dependency_overrides[get_db] = _override_database(db_session)

    try:
        response = TestClient(app).post(
            "/auth/login",
            json={"email": "legacy@example.com", "password": "phase-2-password"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_legacy_admin_endpoint_is_not_registered(monkeypatch, db_session):
    monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)
    app.dependency_overrides[get_db] = _override_database(db_session)

    try:
        response = TestClient(app).get("/admin/fa/users")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_scheduler_does_not_start_or_run_when_legacy_feature_is_disabled(
    monkeypatch,
):
    monkeypatch.delenv("LEGACY_CUSTOMER_APP_ENABLED", raising=False)
    monkeypatch.setenv("AURORATIO_ENABLE_WEBSITE_SCHEDULER", "true")
    monkeypatch.setattr(website_execution_scheduler, "_scheduler", None)

    def unexpected_scheduler(*args, **kwargs):
        raise AssertionError("Scheduler must not be constructed")

    def unexpected_session():
        raise AssertionError("Execution job must not open a database session")

    monkeypatch.setattr(
        website_execution_scheduler,
        "BackgroundScheduler",
        unexpected_scheduler,
    )
    monkeypatch.setattr(
        website_execution_scheduler,
        "SessionLocal",
        unexpected_session,
    )

    website_execution_scheduler.start_execution_scheduler()
    website_execution_scheduler._run_job()

    assert website_execution_scheduler._scheduler is None
