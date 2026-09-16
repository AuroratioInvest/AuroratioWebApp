"""Public Stripe Checkout and accountless billing-management services.

Checkout creates only a Stripe-hosted Session. Local subscribers,
subscriptions, and entitlements remain exclusively webhook-driven.

Portal access uses an emailed opaque token. Only a SHA-256 digest is stored.
The exchange claims the token atomically before creating a Stripe Portal
Session; provider failure rolls the claim back so the same link can be retried.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlsplit

import stripe
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.public_urls import (
    PublicAppUrlConfigurationError,
    public_app_origin,
)
from database import SessionLocal
from services.email_service import send_billing_management_links
from services.subscriber_domain import normalize_subscriber_email
from subscriber_models import (
    AuditActorType,
    AuditEvent,
    PortalAccessToken,
    PortalAccessTokenPurpose,
    PortalLinkIssuance,
    Subscriber,
    SubscriberBillingStatus,
    SubscriberSubscription,
    SubscriptionPlan,
)

logger = logging.getLogger(__name__)

ACCOUNTLESS_FLOW_MARKER = "accountless_subscription"
PUBLIC_CHECKOUT_FLOW = "public_signal_checkout"
DEFAULT_MONTHLY_PLAN_CODE = "monthly-signals"
DEFAULT_MONTHLY_PLAN_DISPLAY_NAME_EN = "AuroRatio Monthly Signals"
DEFAULT_MONTHLY_PLAN_DISPLAY_NAME_FR = "Signaux mensuels AuroRatio"
GENERIC_PORTAL_REQUEST_MESSAGE = (
    "If a subscription exists for that email address, "
    "a secure billing-management link will be sent."
)


@dataclass(frozen=True, repr=False)
class PortalDeliveryItem:
    token_id: str
    raw_token: str
    subscriber_id: str
    stripe_customer_id: str
    label: str


@dataclass(frozen=True, repr=False)
class PortalDeliveryBatch:
    correlation_id: str
    to_email: str
    locale: str
    app_origin: str
    items: tuple[PortalDeliveryItem, ...]


class PublicBillingError(Exception):
    pass


class PublicBillingConfigurationError(PublicBillingError):
    pass


class InvalidPublicBillingRequest(PublicBillingError):
    pass


class PublicBillingProviderError(PublicBillingError):
    pass


class PortalTokenRejected(PublicBillingError):
    pass


def _get(value: Any, key: str, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _configured_positive_int(
    name: str,
    default: int,
    *,
    maximum: int | None = None,
) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise PublicBillingConfigurationError(
            f"{name} must be a positive integer"
        ) from exc
    if value <= 0 or (maximum is not None and value > maximum):
        raise PublicBillingConfigurationError(
            f"{name} is outside the supported range"
        )
    return value


def _stripe_secret_key() -> str:
    value = os.getenv("STRIPE_SECRET_KEY")
    if not value or not value.strip():
        raise PublicBillingConfigurationError("STRIPE_SECRET_KEY is not configured")
    return value.strip()


def _monthly_price_id() -> str:
    value = os.getenv("STRIPE_MONTHLY_SIGNAL_PRICE_ID")
    if not value or not value.strip():
        raise PublicBillingConfigurationError(
            "STRIPE_MONTHLY_SIGNAL_PRICE_ID is not configured"
        )
    normalized = value.strip()
    if not normalized.startswith("price_"):
        raise PublicBillingConfigurationError(
            "STRIPE_MONTHLY_SIGNAL_PRICE_ID is invalid"
        )
    return normalized


def configured_monthly_plan_code() -> str:
    value = os.getenv("MONTHLY_SIGNAL_PLAN_CODE", DEFAULT_MONTHLY_PLAN_CODE).strip()
    if not value:
        raise PublicBillingConfigurationError(
            "MONTHLY_SIGNAL_PLAN_CODE is invalid"
        )
    return value


def _is_valid_public_monthly_plan(
    plan: SubscriptionPlan | None,
    *,
    configured_price_id: str,
) -> bool:
    return (
        plan is not None
        and plan.stripe_price_id == configured_price_id
        and plan.billing_interval == "month"
        and plan.is_active is True
        and plan.is_configured is True
        and plan.archived_at is None
    )


def ensure_public_monthly_plan_configured(
    db: Session,
    *,
    now: datetime,
) -> SubscriptionPlan | None:
    """Create the local public monthly plan row from trusted server config.

    This is intentionally local database configuration only. It does not create
    Stripe Products or Prices and it does not overwrite an existing plan row,
    because archived/inactive/mismatched rows should continue to fail closed.
    """
    now = _aware_utc(now, "now")
    configured_code = configured_monthly_plan_code()
    existing = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.code == configured_code)
        .first()
    )
    if existing is not None:
        return existing

    price_id = _monthly_price_id()
    plan = SubscriptionPlan(
        code=configured_code,
        display_name_en=DEFAULT_MONTHLY_PLAN_DISPLAY_NAME_EN,
        display_name_fr=DEFAULT_MONTHLY_PLAN_DISPLAY_NAME_FR,
        stripe_price_id=price_id,
        billing_interval="month",
        is_active=True,
        is_configured=True,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    try:
        db.commit()
        return plan
    except IntegrityError as exc:
        db.rollback()
        recovered = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.code == configured_code)
            .first()
        )
        if _is_valid_public_monthly_plan(
            recovered,
            configured_price_id=price_id,
        ):
            return recovered
        raise exc


def portal_token_ttl_minutes() -> int:
    return _configured_positive_int(
        "PORTAL_ACCESS_TOKEN_TTL_MINUTES",
        15,
        maximum=60,
    )


def portal_link_cooldown_minutes() -> int:
    return _configured_positive_int(
        "PORTAL_LINK_COOLDOWN_MINUTES",
        5,
        maximum=1440,
    )


def portal_request_min_response_ms() -> int:
    raw_value = os.getenv("PORTAL_REQUEST_MIN_RESPONSE_MS", "750")
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise PublicBillingConfigurationError(
            "PORTAL_REQUEST_MIN_RESPONSE_MS must be an integer"
        ) from exc
    if value < 0 or value > 5000:
        raise PublicBillingConfigurationError(
            "PORTAL_REQUEST_MIN_RESPONSE_MS is outside the supported range"
        )
    return value


def _trusted_stripe_url(value: Any, *, hostname: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PublicBillingProviderError("Stripe returned no hosted URL")
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "https"
        or parsed.hostname != hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise PublicBillingProviderError("Stripe returned an unexpected hosted URL")
    return normalized


def _audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    correlation_id: str,
    reason: str,
    metadata: dict | None = None,
    created_at: datetime,
) -> None:
    db.add(
        AuditEvent(
            actor_type=AuditActorType.system,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            event_metadata=metadata,
            correlation_id=correlation_id,
            created_at=created_at,
        )
    )


def _resolve_checkout_plan(
    db: Session,
    *,
    requested_plan_code: str,
) -> tuple[SubscriptionPlan, str]:
    configured_code = configured_monthly_plan_code()
    if requested_plan_code != configured_code:
        raise InvalidPublicBillingRequest("Unsupported subscription plan")

    price_id = _monthly_price_id()
    plans = (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.code == configured_code,
            SubscriptionPlan.stripe_price_id == price_id,
            SubscriptionPlan.is_active.is_(True),
            SubscriptionPlan.is_configured.is_(True),
            SubscriptionPlan.archived_at.is_(None),
        )
        .all()
    )
    if len(plans) != 1:
        raise PublicBillingConfigurationError(
            "The public monthly plan is not configured consistently"
        )
    return plans[0], price_id


def create_public_checkout_session(
    db: Session,
    *,
    plan_code: str,
    locale: str,
    request_id: str,
    now: datetime,
    create_session: Callable[..., Any] | None = None,
) -> str:
    """Create a Stripe Checkout Session without creating local customer state."""
    now = _aware_utc(now, "now")
    try:
        correlation_id = str(uuid.UUID(request_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidPublicBillingRequest("Invalid checkout request identifier") from exc
    if locale not in {"en", "fr"}:
        raise InvalidPublicBillingRequest("Unsupported checkout locale")

    plan, price_id = _resolve_checkout_plan(
        db,
        requested_plan_code=plan_code,
    )
    try:
        app_origin = public_app_origin()
    except PublicAppUrlConfigurationError as exc:
        raise PublicBillingConfigurationError(str(exc)) from exc
    secret_key = _stripe_secret_key()

    _audit(
        db,
        action="checkout_session_requested",
        entity_type="subscription_plan",
        entity_id=plan.id,
        correlation_id=correlation_id,
        reason="Public accountless Checkout Session requested",
        metadata={"plan_code": plan.code, "locale": locale},
        created_at=now,
    )
    db.commit()

    metadata = {
        "subscription_model": ACCOUNTLESS_FLOW_MARKER,
        "checkout_flow": PUBLIC_CHECKOUT_FLOW,
        "plan_code": plan.code,
        "preferred_language": locale,
    }
    creator = create_session or stripe.checkout.Session.create
    try:
        session = creator(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=(
                f"{app_origin}/subscription/success"
                "?session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=f"{app_origin}/subscription/cancelled",
            locale=locale,
            metadata=metadata,
            subscription_data={"metadata": metadata},
            api_key=secret_key,
            idempotency_key=f"public-checkout:{correlation_id}",
        )
        checkout_url = _trusted_stripe_url(
            _get(session, "url"),
            hostname="checkout.stripe.com",
        )
    except PublicBillingProviderError:
        _audit(
            db,
            action="checkout_session_failed",
            entity_type="subscription_plan",
            entity_id=plan.id,
            correlation_id=correlation_id,
            reason="Stripe Checkout returned an invalid hosted URL",
            metadata={"plan_code": plan.code},
            created_at=now,
        )
        db.commit()
        raise
    except stripe.error.StripeError as exc:
        _audit(
            db,
            action="checkout_session_failed",
            entity_type="subscription_plan",
            entity_id=plan.id,
            correlation_id=correlation_id,
            reason="Stripe Checkout provider request failed",
            metadata={"plan_code": plan.code},
            created_at=now,
        )
        db.commit()
        logger.error("Stripe Checkout provider request failed")
        raise PublicBillingProviderError(
            "Stripe Checkout is temporarily unavailable"
        ) from exc
    except Exception as exc:
        _audit(
            db,
            action="checkout_session_failed",
            entity_type="subscription_plan",
            entity_id=plan.id,
            correlation_id=correlation_id,
            reason="Stripe Checkout returned an invalid response",
            metadata={"plan_code": plan.code},
            created_at=now,
        )
        db.commit()
        logger.error("Stripe Checkout returned an invalid response")
        raise PublicBillingProviderError(
            "Stripe Checkout is temporarily unavailable"
        ) from exc

    _audit(
        db,
        action="checkout_session_created",
        entity_type="subscription_plan",
        entity_id=plan.id,
        correlation_id=correlation_id,
        reason="Stripe Checkout Session created",
        metadata={"plan_code": plan.code},
        created_at=now,
    )
    db.commit()
    return checkout_url


def hash_portal_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _create_portal_token(
    db: Session,
    *,
    subscriber: Subscriber,
    stripe_customer_id: str,
    correlation_id: str,
    now: datetime,
) -> tuple[PortalAccessToken, str]:
    expires_at = now + timedelta(minutes=portal_token_ttl_minutes())
    frozen_customer_id = stripe_customer_id.strip()
    if not frozen_customer_id:
        raise PublicBillingProviderError("Could not bind a portal access token")
    for _attempt in range(3):
        raw_token = secrets.token_urlsafe(32)
        token = PortalAccessToken(
            token_hash=hash_portal_token(raw_token),
            subscriber_id=subscriber.id,
            stripe_customer_id=frozen_customer_id,
            purpose=PortalAccessTokenPurpose.customer_portal,
            expires_at=expires_at,
            correlation_id=correlation_id,
            created_at=now,
            updated_at=now,
        )
        try:
            with db.begin_nested():
                db.add(token)
                db.flush()
            return token, raw_token
        except IntegrityError:
            continue
    raise PublicBillingProviderError("Could not create a portal access token")


@dataclass(frozen=True, repr=False)
class _PortalRelationship:
    subscriber_id: str
    stripe_customer_id: str
    subscription_id: str
    plan_name_en: str
    plan_name_fr: str
    billing_status: SubscriberBillingStatus
    stripe_status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    priority_key: tuple


def _sortable_timestamp(value: datetime | None) -> float:
    if value is None:
        return 0
    return _aware_utc(value, "subscription timestamp").timestamp()


def _portal_subscription_priority(
    subscription: SubscriberSubscription,
    *,
    now: datetime,
) -> tuple:
    """Return stable priority: current, payment action, scheduled cancel, history."""
    raw_status = (subscription.stripe_status or "").strip().lower()
    period_end = subscription.current_period_end
    period_is_current = (
        period_end is not None
        and _aware_utc(period_end, "current_period_end") >= now
    )

    if (
        not subscription.cancel_at_period_end
        and (
            subscription.billing_status == SubscriberBillingStatus.active
            or raw_status == "trialing"
        )
    ):
        priority = 0
    elif (
        subscription.billing_status == SubscriberBillingStatus.delinquent
        or raw_status in {"past_due", "unpaid", "incomplete"}
    ):
        priority = 1
    elif subscription.cancel_at_period_end and period_is_current:
        priority = 2
    else:
        priority = 3

    return (
        priority,
        -_sortable_timestamp(period_end),
        -_sortable_timestamp(subscription.created_at),
        subscription.id,
    )


def _resolve_portal_relationships(
    db: Session,
    *,
    normalized_email: str,
    now: datetime,
) -> list[_PortalRelationship]:
    rows = (
        db.query(SubscriberSubscription, Subscriber, SubscriptionPlan)
        .join(
            Subscriber,
            Subscriber.id == SubscriberSubscription.subscriber_id,
        )
        .join(
            SubscriptionPlan,
            SubscriptionPlan.id == SubscriberSubscription.plan_id,
        )
        .filter(
            Subscriber.normalized_email == normalized_email,
            Subscriber.archived_at.is_(None),
            Subscriber.stripe_customer_id.isnot(None),
        )
        .all()
    )

    by_customer: dict[str, _PortalRelationship] = {}
    for subscription, subscriber, plan in rows:
        customer_id = (subscriber.stripe_customer_id or "").strip()
        subscription_id = (subscription.stripe_subscription_id or "").strip()
        if not customer_id or not subscription_id:
            continue
        priority_key = _portal_subscription_priority(subscription, now=now)
        candidate = _PortalRelationship(
            subscriber_id=subscriber.id,
            stripe_customer_id=customer_id,
            subscription_id=subscription_id,
            plan_name_en=plan.display_name_en,
            plan_name_fr=plan.display_name_fr,
            billing_status=subscription.billing_status,
            stripe_status=(subscription.stripe_status or "").strip().lower(),
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            priority_key=priority_key,
        )
        existing = by_customer.get(customer_id)
        if existing is None or priority_key < existing.priority_key:
            by_customer[customer_id] = candidate

    return sorted(
        by_customer.values(),
        key=lambda relationship: (
            relationship.priority_key,
            relationship.subscriber_id,
        ),
    )


def _portal_relationship_label(
    relationship: _PortalRelationship,
    *,
    locale: str,
) -> str:
    plan_name = (
        relationship.plan_name_fr
        if locale == "fr"
        else relationship.plan_name_en
    )
    raw_status = relationship.stripe_status
    if (
        relationship.billing_status == SubscriberBillingStatus.active
        and not relationship.cancel_at_period_end
    ):
        status = "Actif" if locale == "fr" else "Active"
    elif raw_status == "trialing":
        status = "Période d’essai" if locale == "fr" else "Trial"
    elif relationship.billing_status == SubscriberBillingStatus.delinquent:
        status = "Paiement requis" if locale == "fr" else "Payment action required"
    elif relationship.cancel_at_period_end:
        status = (
            "Annulation programmée"
            if locale == "fr"
            else "Cancellation scheduled"
        )
    else:
        status = "Historique" if locale == "fr" else "Historical"

    period_end = relationship.current_period_end
    if period_end is None:
        return f"{plan_name} — {status}"
    date_text = _aware_utc(period_end, "current_period_end").date().isoformat()
    period_text = (
        f"période jusqu’au {date_text}"
        if locale == "fr"
        else f"period through {date_text}"
    )
    return f"{plan_name} — {status} · {period_text}"


def _claim_portal_link_cooldown(
    db: Session,
    *,
    subscriber_id: str,
    now: datetime,
) -> bool:
    next_allowed_at = now + timedelta(minutes=portal_link_cooldown_minutes())
    values = {
        "id": str(uuid.uuid4()),
        "subscriber_id": subscriber_id,
        "last_issued_at": now,
        "next_allowed_at": next_allowed_at,
        "created_at": now,
        "updated_at": now,
    }
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "sqlite":
        statement = sqlite_insert(PortalLinkIssuance).values(**values)
    elif dialect_name == "postgresql":
        statement = postgresql_insert(PortalLinkIssuance).values(**values)
    else:
        raise PublicBillingConfigurationError(
            "Portal-link cooldown requires SQLite or PostgreSQL"
        )

    statement = (
        statement.on_conflict_do_update(
            index_elements=["subscriber_id"],
            set_={
                "last_issued_at": now,
                "next_allowed_at": next_allowed_at,
                "updated_at": now,
            },
            where=PortalLinkIssuance.next_allowed_at <= now,
        )
        .returning(PortalLinkIssuance.subscriber_id)
    )
    return db.execute(statement).scalar_one_or_none() is not None


def _invalidate_expired_portal_tokens(db: Session, *, now: datetime) -> int:
    return (
        db.query(PortalAccessToken)
        .filter(
            PortalAccessToken.purpose
            == PortalAccessTokenPurpose.customer_portal,
            PortalAccessToken.consumed_at.is_(None),
            PortalAccessToken.invalidated_at.is_(None),
            PortalAccessToken.expires_at < now,
        )
        .update(
            {
                PortalAccessToken.invalidated_at: now,
                PortalAccessToken.updated_at: now,
            },
            synchronize_session=False,
        )
    )


def _supersede_portal_tokens(
    db: Session,
    *,
    subscriber_id: str,
    now: datetime,
) -> int:
    return (
        db.query(PortalAccessToken)
        .filter(
            PortalAccessToken.subscriber_id == subscriber_id,
            PortalAccessToken.purpose
            == PortalAccessTokenPurpose.customer_portal,
            PortalAccessToken.consumed_at.is_(None),
            PortalAccessToken.invalidated_at.is_(None),
            PortalAccessToken.delivery_claimed_at.is_(None),
            PortalAccessToken.delivered_at.is_(None),
        )
        .update(
            {
                PortalAccessToken.invalidated_at: now,
                PortalAccessToken.updated_at: now,
            },
            synchronize_session=False,
        )
    )


async def request_portal_access(
    db: Session,
    *,
    email: str,
    locale: str,
    now: datetime,
) -> PortalDeliveryBatch | None:
    """Create a throttled token batch without awaiting an email provider."""
    started_at = time.monotonic()
    now = _aware_utc(now, "now")
    correlation_id = str(uuid.uuid4())
    minimum_delay = portal_request_min_response_ms() / 1000
    normalized_email = normalize_subscriber_email(email)
    if locale not in {"en", "fr"}:
        locale = "en"

    try:
        try:
            app_origin = public_app_origin()
        except PublicAppUrlConfigurationError as exc:
            raise PublicBillingConfigurationError(str(exc)) from exc

        _audit(
            db,
            action="portal_link_requested",
            entity_type="billing_management_request",
            entity_id=correlation_id,
            correlation_id=correlation_id,
            reason="Public accountless billing-management link requested",
            metadata={"locale": locale},
            created_at=now,
        )
        _invalidate_expired_portal_tokens(db, now=now)

        if normalized_email is None:
            db.commit()
            return None

        relationships = _resolve_portal_relationships(
            db,
            normalized_email=normalized_email,
            now=now,
        )
        delivery_items: list[PortalDeliveryItem] = []
        for relationship in relationships:
            if not _claim_portal_link_cooldown(
                db,
                subscriber_id=relationship.subscriber_id,
                now=now,
            ):
                continue

            superseded = _supersede_portal_tokens(
                db,
                subscriber_id=relationship.subscriber_id,
                now=now,
            )
            token, raw_token = _create_portal_token(
                db,
                subscriber=(
                    db.query(Subscriber)
                    .filter(Subscriber.id == relationship.subscriber_id)
                    .one()
                ),
                stripe_customer_id=relationship.stripe_customer_id,
                correlation_id=correlation_id,
                now=now,
            )
            _audit(
                db,
                action="portal_token_created",
                entity_type="portal_access_token",
                entity_id=token.id,
                correlation_id=correlation_id,
                reason="Single-use Customer Portal access token created",
                metadata={
                    "purpose": token.purpose.value,
                    "superseded_tokens": superseded,
                },
                created_at=now,
            )
            delivery_items.append(
                PortalDeliveryItem(
                    token_id=token.id,
                    raw_token=raw_token,
                    subscriber_id=relationship.subscriber_id,
                    stripe_customer_id=relationship.stripe_customer_id,
                    label=_portal_relationship_label(
                        relationship,
                        locale=locale,
                    ),
                )
            )

        if not delivery_items:
            db.commit()
            return None

        db.commit()
        return PortalDeliveryBatch(
            correlation_id=correlation_id,
            to_email=email.strip(),
            locale=locale,
            app_origin=app_origin,
            items=tuple(delivery_items),
        )
    except Exception:
        db.rollback()
        raise
    finally:
        remaining = minimum_delay - (time.monotonic() - started_at)
        if remaining > 0:
            await asyncio.sleep(remaining)


def _token_has_trusted_portal_relationship(
    db: Session,
    *,
    token: PortalAccessToken,
) -> bool:
    frozen_customer_id = (token.stripe_customer_id or "").strip()
    if not frozen_customer_id:
        return False
    return (
        db.query(SubscriberSubscription.id)
        .join(
            Subscriber,
            Subscriber.id == SubscriberSubscription.subscriber_id,
        )
        .filter(
            Subscriber.id == token.subscriber_id,
            Subscriber.archived_at.is_(None),
            Subscriber.stripe_customer_id == frozen_customer_id,
            SubscriberSubscription.subscriber_id == token.subscriber_id,
            SubscriberSubscription.stripe_subscription_id.isnot(None),
        )
        .filter(SubscriberSubscription.stripe_subscription_id != "")
        .first()
        is not None
    )


def _claim_deliverable_portal_tokens(
    db: Session,
    *,
    batch: PortalDeliveryBatch,
    now: datetime,
) -> list[PortalDeliveryItem]:
    if not batch.items:
        return []

    tokens = (
        db.query(PortalAccessToken)
        .filter(PortalAccessToken.id.in_([item.token_id for item in batch.items]))
        .all()
    )
    by_id = {token.id: token for token in tokens}
    deliverable: list[PortalDeliveryItem] = []
    skipped = 0

    for item in batch.items:
        token = by_id.get(item.token_id)
        if (
            token is None
            or token.purpose != PortalAccessTokenPurpose.customer_portal
            or token.subscriber_id != item.subscriber_id
            or token.stripe_customer_id != item.stripe_customer_id
            or token.consumed_at is not None
            or token.invalidated_at is not None
            or token.expires_at < now
            or token.delivery_claimed_at is not None
            or token.delivered_at is not None
            or token.delivery_failed_at is not None
            or not _token_has_trusted_portal_relationship(db, token=token)
        ):
            skipped += 1
            if token is not None:
                _audit(
                    db,
                    action="portal_link_delivery_skipped",
                    entity_type="portal_access_token",
                    entity_id=token.id,
                    correlation_id=batch.correlation_id,
                    reason="Billing-management link was stale before delivery",
                    created_at=now,
                )
            continue

        claimed = (
            db.query(PortalAccessToken)
            .filter(
                PortalAccessToken.id == token.id,
                PortalAccessToken.subscriber_id == item.subscriber_id,
                PortalAccessToken.stripe_customer_id == item.stripe_customer_id,
                PortalAccessToken.purpose
                == PortalAccessTokenPurpose.customer_portal,
                PortalAccessToken.consumed_at.is_(None),
                PortalAccessToken.invalidated_at.is_(None),
                PortalAccessToken.expires_at >= now,
                PortalAccessToken.delivery_claimed_at.is_(None),
                PortalAccessToken.delivered_at.is_(None),
                PortalAccessToken.delivery_failed_at.is_(None),
            )
            .update(
                {
                    PortalAccessToken.delivery_claimed_at: now,
                    PortalAccessToken.updated_at: now,
                },
                synchronize_session=False,
            )
        )
        if claimed == 1:
            deliverable.append(item)
        else:
            skipped += 1

    if skipped and not deliverable:
        _audit(
            db,
            action="portal_link_delivery_skipped",
            entity_type="portal_delivery_batch",
            entity_id=batch.correlation_id,
            correlation_id=batch.correlation_id,
            reason="No current billing-management links remained deliverable",
            created_at=now,
        )

    return deliverable


async def deliver_portal_access_batch(
    batch: PortalDeliveryBatch,
    *,
    deliver_links: Callable[..., Awaitable[bool]] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    now_factory: Callable[[], datetime] | None = None,
) -> None:
    """Process-local post-response delivery; raw tokens never enter persistence."""
    now_factory = now_factory or (lambda: datetime.now(timezone.utc))
    now = _aware_utc(now_factory(), "delivery time")
    try:
        db = session_factory()
    except Exception:
        logger.error("Billing-management delivery outcome database is unavailable")
        return

    try:
        deliverable_items = _claim_deliverable_portal_tokens(
            db,
            batch=batch,
            now=now,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.error("Billing-management delivery claim could not be recorded")
        db.close()
        return

    if not deliverable_items:
        db.close()
        return

    links = [
        {
            "label": item.label,
            "url": (
                f"{batch.app_origin}/manage-subscription/access"
                f"#token={quote(item.raw_token, safe='')}"
            ),
        }
        for item in deliverable_items
    ]
    sender = deliver_links or send_billing_management_links
    try:
        delivered = await sender(
            to_email=batch.to_email,
            links=links,
            locale=batch.locale,
        )
    except Exception:
        delivered = False
        logger.error("Billing-management email delivery raised an error")
    finally:
        links = []

    try:
        token_ids = [item.token_id for item in deliverable_items]
        tokens = (
            db.query(PortalAccessToken)
            .filter(PortalAccessToken.id.in_(token_ids))
            .all()
        )
        by_id = {token.id: token for token in tokens}
        for item in batch.items:
            token = by_id.get(item.token_id)
            if token is None:
                continue
            if delivered:
                token.delivered_at = now
                token.updated_at = now
                _audit(
                    db,
                    action="portal_link_delivered",
                    entity_type="portal_access_token",
                    entity_id=token.id,
                    correlation_id=batch.correlation_id,
                    reason="Billing-management link accepted by email provider",
                    created_at=now,
                )
            else:
                if (
                    token.consumed_at is None
                    and token.invalidated_at is None
                    and token.delivered_at is None
                ):
                    token.delivery_failed_at = now
                    token.invalidated_at = now
                    token.updated_at = now
                _audit(
                    db,
                    action="portal_link_delivery_failed",
                    entity_type="portal_access_token",
                    entity_id=token.id,
                    correlation_id=batch.correlation_id,
                    reason="Billing-management email was not delivered",
                    created_at=now,
                )
        db.commit()
    except Exception:
        db.rollback()
        logger.error("Billing-management delivery outcome could not be recorded")
    finally:
        db.close()


def _record_portal_exchange_rejection(
    db: Session,
    *,
    correlation_id: str,
    entity_id: str,
    reason: str,
    now: datetime,
) -> None:
    _audit(
        db,
        action="portal_token_rejected",
        entity_type="portal_access_token",
        entity_id=entity_id,
        correlation_id=correlation_id,
        reason=reason,
        created_at=now,
    )
    db.commit()


def exchange_portal_access_token(
    db: Session,
    *,
    raw_token: str,
    now: datetime,
    create_portal_session: Callable[..., Any] | None = None,
) -> str:
    """Atomically consume a one-time token and create a Stripe Portal Session."""
    now = _aware_utc(now, "now")
    if not isinstance(raw_token, str) or len(raw_token) < 32:
        correlation_id = str(uuid.uuid4())
        _record_portal_exchange_rejection(
            db,
            correlation_id=correlation_id,
            entity_id=correlation_id,
            reason="Invalid billing-management token",
            now=now,
        )
        raise PortalTokenRejected("Invalid or expired billing-management link")

    try:
        app_origin = public_app_origin()
    except PublicAppUrlConfigurationError as exc:
        raise PublicBillingConfigurationError(str(exc)) from exc
    secret_key = _stripe_secret_key()
    configuration_id = os.getenv("STRIPE_BILLING_PORTAL_CONFIGURATION_ID")
    if configuration_id:
        configuration_id = configuration_id.strip()
        if not configuration_id.startswith("bpc_"):
            raise PublicBillingConfigurationError(
                "STRIPE_BILLING_PORTAL_CONFIGURATION_ID is invalid"
            )

    token_hash = hash_portal_token(raw_token)
    token = (
        db.query(PortalAccessToken)
        .filter(
            PortalAccessToken.token_hash == token_hash,
            PortalAccessToken.purpose
            == PortalAccessTokenPurpose.customer_portal,
        )
        .first()
    )
    if token is None:
        correlation_id = str(uuid.uuid4())
        _record_portal_exchange_rejection(
            db,
            correlation_id=correlation_id,
            entity_id=correlation_id,
            reason="Unknown billing-management token",
            now=now,
        )
        raise PortalTokenRejected("Invalid or expired billing-management link")

    correlation_id = token.correlation_id or str(uuid.uuid4())
    if (
        token.consumed_at is not None
        or token.invalidated_at is not None
        or token.expires_at < now
    ):
        _record_portal_exchange_rejection(
            db,
            correlation_id=correlation_id,
            entity_id=token.id,
            reason="Billing-management token is expired or unavailable",
            now=now,
        )
        raise PortalTokenRejected("Invalid or expired billing-management link")

    frozen_customer_id = (token.stripe_customer_id or "").strip()
    if not _token_has_trusted_portal_relationship(db, token=token):
        token.invalidated_at = now
        token.updated_at = now
        _record_portal_exchange_rejection(
            db,
            correlation_id=correlation_id,
            entity_id=token.id,
            reason="Billing-management token customer relationship is unavailable",
            now=now,
        )
        raise PortalTokenRejected("Invalid or expired billing-management link")

    claimed = (
        db.query(PortalAccessToken)
        .filter(
            PortalAccessToken.id == token.id,
            PortalAccessToken.stripe_customer_id == frozen_customer_id,
            PortalAccessToken.purpose
            == PortalAccessTokenPurpose.customer_portal,
            PortalAccessToken.consumed_at.is_(None),
            PortalAccessToken.invalidated_at.is_(None),
            PortalAccessToken.expires_at >= now,
        )
        .update(
            {
                PortalAccessToken.consumed_at: now,
                PortalAccessToken.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if claimed != 1:
        db.rollback()
        _record_portal_exchange_rejection(
            db,
            correlation_id=correlation_id,
            entity_id=token.id,
            reason="Billing-management token was already claimed",
            now=now,
        )
        raise PortalTokenRejected("Invalid or expired billing-management link")

    subscriber = (
        db.query(Subscriber)
        .filter(Subscriber.id == token.subscriber_id)
        .first()
    )
    if subscriber is None or not frozen_customer_id:
        db.rollback()
        token = db.query(PortalAccessToken).filter_by(id=token.id).one()
        token.invalidated_at = now
        token.updated_at = now
        _record_portal_exchange_rejection(
            db,
            correlation_id=correlation_id,
            entity_id=token.id,
            reason="Subscriber is unavailable for billing management",
            now=now,
        )
        raise PortalTokenRejected("Invalid or expired billing-management link")

    creator = create_portal_session or stripe.billing_portal.Session.create
    portal_kwargs = {
        "customer": frozen_customer_id,
        "return_url": f"{app_origin}/manage-subscription?portal=return",
        "api_key": secret_key,
        "idempotency_key": f"portal-access:{token.id}",
    }
    if configuration_id:
        portal_kwargs["configuration"] = configuration_id

    try:
        portal_session = creator(**portal_kwargs)
        portal_url = _trusted_stripe_url(
            _get(portal_session, "url"),
            hostname="billing.stripe.com",
        )
    except (stripe.error.StripeError, PublicBillingProviderError) as exc:
        db.rollback()
        _audit(
            db,
            action="portal_session_failed",
            entity_type="portal_access_token",
            entity_id=token.id,
            correlation_id=correlation_id,
            reason="Stripe Customer Portal Session creation failed",
            created_at=now,
        )
        db.commit()
        logger.error("Stripe Customer Portal Session creation failed")
        raise PublicBillingProviderError(
            "Secure billing management is temporarily unavailable"
        ) from exc
    except Exception as exc:
        db.rollback()
        _audit(
            db,
            action="portal_session_failed",
            entity_type="portal_access_token",
            entity_id=token.id,
            correlation_id=correlation_id,
            reason="Stripe Customer Portal returned an invalid response",
            created_at=now,
        )
        db.commit()
        logger.error("Stripe Customer Portal returned an invalid response")
        raise PublicBillingProviderError(
            "Secure billing management is temporarily unavailable"
        ) from exc

    _audit(
        db,
        action="portal_token_consumed",
        entity_type="portal_access_token",
        entity_id=token.id,
        correlation_id=correlation_id,
        reason="Single-use billing-management token consumed",
        created_at=now,
    )
    _audit(
        db,
        action="portal_session_created",
        entity_type="subscriber",
        entity_id=subscriber.id,
        correlation_id=correlation_id,
        reason="Stripe Customer Portal Session created",
        created_at=now,
    )
    db.commit()
    return portal_url
