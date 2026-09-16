from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.limiter import limiter
from database import get_db
from routers import public_billing
from services.public_billing_service import (
    GENERIC_PORTAL_REQUEST_MESSAGE,
    PortalDeliveryBatch,
    PortalDeliveryItem,
    PublicBillingProviderError,
)


@contextmanager
def _client(db_session):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(public_billing.router, prefix="/public/billing")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client


def test_checkout_endpoint_returns_only_hosted_url(monkeypatch, db_session):
    captured = {}

    def fake_checkout(db, **kwargs):
        captured.update(kwargs)
        return "https://checkout.stripe.com/c/pay/session"

    monkeypatch.setattr(
        public_billing,
        "create_public_checkout_session",
        fake_checkout,
    )

    with _client(db_session) as client:
        response = client.post(
            "/public/billing/checkout-session",
            json={
                "plan_code": "monthly-signals",
                "locale": "en",
                "request_id": "a819f52c-f6b2-4c37-9dd1-f79035a93864",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "url": "https://checkout.stripe.com/c/pay/session"
    }
    assert captured["plan_code"] == "monthly-signals"
    assert "customer_id" not in response.text
    assert "subscription_id" not in response.text


def test_checkout_endpoint_accepts_empty_body_for_single_public_plan(
    monkeypatch,
    db_session,
):
    captured = {}

    def fake_checkout(db, **kwargs):
        captured.update(kwargs)
        return "https://checkout.stripe.com/c/pay/session"

    monkeypatch.setattr(
        public_billing,
        "create_public_checkout_session",
        fake_checkout,
    )

    with _client(db_session) as client:
        response = client.post("/public/billing/checkout-session", json={})

    assert response.status_code == 200
    assert response.json() == {
        "url": "https://checkout.stripe.com/c/pay/session"
    }
    assert captured["plan_code"] == "monthly-signals"
    assert captured["locale"] == "en"
    assert captured["request_id"]


def test_checkout_endpoint_rejects_arbitrary_price_field(monkeypatch, db_session):
    called = False

    def unexpected_checkout(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        public_billing,
        "create_public_checkout_session",
        unexpected_checkout,
    )
    with _client(db_session) as client:
        response = client.post(
            "/public/billing/checkout-session",
            json={
                "plan_code": "monthly-signals",
                "locale": "en",
                "request_id": "a819f52c-f6b2-4c37-9dd1-f79035a93864",
                "price_id": "price_attacker",
            },
        )

    assert response.status_code == 422
    assert called is False


def test_portal_link_endpoint_is_generic_for_success_and_delivery_failure(
    monkeypatch,
    db_session,
):
    async def accepted(db, **kwargs):
        return None

    async def provider_failure(db, **kwargs):
        raise PublicBillingProviderError("email delivery failed")

    monkeypatch.setattr(public_billing, "request_portal_access", accepted)
    with _client(db_session) as client:
        accepted_response = client.post(
            "/public/billing/portal-link",
            json={"email": "known@example.com", "locale": "en"},
        )

    monkeypatch.setattr(public_billing, "request_portal_access", provider_failure)
    with _client(db_session) as client:
        failure_response = client.post(
            "/public/billing/portal-link",
            json={"email": "unknown@example.com", "locale": "en"},
        )

    assert accepted_response.status_code == failure_response.status_code == 202
    assert accepted_response.json() == failure_response.json() == {
        "message": GENERIC_PORTAL_REQUEST_MESSAGE
    }
    assert "customer" not in accepted_response.text


def test_portal_link_schedules_delivery_without_awaiting_provider(
    monkeypatch,
    db_session,
):
    batch = PortalDeliveryBatch(
        correlation_id="correlation-id",
        to_email="known@example.com",
        locale="en",
        app_origin="https://app.auroratio.test",
        items=(
            PortalDeliveryItem(
                token_id="token-id",
                raw_token="t" * 43,
                subscriber_id="subscriber-id",
                stripe_customer_id="cus_test",
                label="Monthly signals — Active",
            ),
        ),
    )
    provider_called = False

    async def accepted(db, **kwargs):
        return batch

    async def delayed_provider(delivery_batch):
        nonlocal provider_called
        provider_called = True

    scheduled = []

    class CapturingBackgroundTasks:
        def add_task(self, function, *args, **kwargs):
            scheduled.append((function, args, kwargs))

    monkeypatch.setattr(public_billing, "request_portal_access", accepted)
    monkeypatch.setattr(
        public_billing,
        "deliver_portal_access_batch",
        delayed_provider,
    )

    response = public_billing.create_portal_link.__wrapped__(
        request=object(),
        body=public_billing.PortalLinkRequest(
            email="known@example.com",
            locale="en",
        ),
        background_tasks=CapturingBackgroundTasks(),
        db=db_session,
    )
    if hasattr(response, "__await__"):
        import asyncio

        response = asyncio.run(response)

    assert response.message == GENERIC_PORTAL_REQUEST_MESSAGE
    assert provider_called is False
    assert scheduled == [(delayed_provider, (batch,), {})]


def test_portal_session_endpoint_accepts_only_token_and_returns_safe_url(
    monkeypatch,
    db_session,
):
    captured = {}

    def fake_exchange(db, **kwargs):
        captured.update(kwargs)
        return "https://billing.stripe.com/p/session/secure"

    monkeypatch.setattr(
        public_billing,
        "exchange_portal_access_token",
        fake_exchange,
    )
    with _client(db_session) as client:
        response = client.post(
            "/public/billing/portal-session",
            json={"token": "t" * 43},
        )
        customer_response = client.post(
            "/public/billing/portal-session",
            json={"token": "t" * 43, "customer_id": "cus_attacker"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "url": "https://billing.stripe.com/p/session/secure"
    }
    assert captured["raw_token"] == "t" * 43
    assert customer_response.status_code == 422
