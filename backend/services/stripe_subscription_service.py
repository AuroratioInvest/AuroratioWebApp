"""Stripe ingestion and accountless subscription synchronization.

This module has no fulfillment side effects. It only updates the Phase 3
subscriber, billing, entitlement, integration-event, and access-history tables.

Ordering: every state-changing event retrieves the current Stripe subscription.
The stored provider timestamp is a monotonic observed-event high-water mark, not
a reason to discard a distinct event. Deleted events use their signed object only
when Stripe confirms that the subscription no longer exists.

Grace: a payment failure can enter grace only when persisted access-start and
paid-through dates prove prior paid access. Failure alone never starts access.

Retries: correctable failures remain ``retryable_failure`` after automatic HTTP
redelivery is exhausted and can be replayed internally by authoritative Stripe
Event ID retrieval. Only invalid/contradictory events become permanently failed.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import stripe
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.subscriber_domain import normalize_subscriber_email
from subscriber_models import (
    AccessEntitlement,
    EntitlementAccessStatus,
    IntegrationEvent,
    IntegrationProcessingStatus,
    IntegrationProvider,
    Subscriber,
    SubscriberBillingStatus,
    SubscriberSubscription,
    SubscriptionAccessEvent,
    SubscriptionEventSource,
    SubscriptionPlan,
)

logger = logging.getLogger(__name__)

# PostgreSQL lock order: IntegrationEvent -> SubscriberSubscription ->
# Subscriber -> AccessEntitlement. SubscriptionPlan is configuration-read only.
STRIPE_SYNC_LOCK_ORDER = (
    "integration_event",
    "subscriber_subscription",
    "subscriber",
    "access_entitlement",
)


SUPPORTED_EVENT_TYPES = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.paid",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    }
)

SUBSCRIPTION_EVENT_TYPES = frozenset(
    {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }
)

INVOICE_PAID_EVENT_TYPES = frozenset({"invoice.paid", "invoice.payment_succeeded"})

SECRET_PATTERN = re.compile(
    r"\b(?:sk|rk|whsec)_(?:live|test)?_[A-Za-z0-9_-]+\b|\bwhsec_[A-Za-z0-9_-]+\b"
)


class StripeEventProcessingError(Exception):
    pass


class RetryableStripeEventError(StripeEventProcessingError):
    pass


class PermanentStripeEventError(StripeEventProcessingError):
    pass


class StripeSubscriptionNotFoundError(StripeEventProcessingError):
    pass


class IgnoredStripeEvent(StripeEventProcessingError):
    pass


@dataclass(frozen=True)
class StripeProcessingOutcome:
    status: IntegrationProcessingStatus
    duplicate: bool = False
    retryable: bool = False


def _get(value: Any, key: str, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _nonempty_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PermanentStripeEventError(f"Missing or invalid {field}")
    return value.strip()


def _timestamp(value: Any, field: str, *, required: bool = False) -> datetime | None:
    if value is None:
        if required:
            raise PermanentStripeEventError(f"Missing {field}")
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PermanentStripeEventError(f"Invalid {field}") from exc


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def payment_failure_grace_days() -> int:
    return 3


def processing_retry_seconds() -> int:
    return 300


def processing_max_attempts() -> int:
    return 5


def map_stripe_billing_status(stripe_status: str) -> SubscriberBillingStatus:
    normalized = (stripe_status or "").strip().lower()
    if normalized == "active":
        return SubscriberBillingStatus.active
    if normalized in {"past_due", "unpaid"}:
        return SubscriberBillingStatus.delinquent
    if normalized in {"canceled", "cancelled", "incomplete_expired"}:
        return SubscriberBillingStatus.ended
    if normalized in {"incomplete", "trialing", "paused"}:
        return SubscriberBillingStatus.pending
    return SubscriberBillingStatus.pending


def sanitize_error_text(exc: Exception) -> str:
    text = SECRET_PATTERN.sub("[redacted]", str(exc))
    text = " ".join(text.split())
    return f"{type(exc).__name__}: {text}"[:1000]


def persisted_error_text(exc: Exception) -> str:
    """Return bounded persistence-safe diagnostics without SQL/data parameters."""
    if isinstance(exc, StripeEventProcessingError):
        return sanitize_error_text(exc)
    return f"{type(exc).__name__}: unexpected processing failure"


def selected_event_metadata(event: Any) -> dict:
    event_type = str(_get(event, "type", ""))
    data_object = _get(_get(event, "data", {}), "object", {}) or {}
    metadata = {
        "livemode": bool(_get(event, "livemode", False)),
        "object_id": _get(data_object, "id"),
        "customer_id": _object_id(_get(data_object, "customer")),
        "subscription_id": _object_id(_get(data_object, "subscription")),
    }
    if event_type in SUBSCRIPTION_EVENT_TYPES:
        metadata["subscription_id"] = _get(data_object, "id")
        metadata["price_ids"] = _subscription_price_ids(data_object)
    return {key: value for key, value in metadata.items() if value not in (None, [], "")}


def _object_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return _get(value, "id")


def _subscription_price_ids(subscription_object: Any) -> list[str]:
    items = _get(_get(subscription_object, "items", {}), "data", []) or []
    price_ids = []
    for item in items:
        price_id = _object_id(_get(item, "price"))
        if isinstance(price_id, str) and price_id.strip():
            price_ids.append(price_id.strip())
    return sorted(set(price_ids))


def _subscription_period_timestamps(
    subscription_object: Any,
) -> tuple[datetime | None, datetime | None]:
    period_start = _timestamp(
        _get(subscription_object, "current_period_start"),
        "current_period_start",
    )
    period_end = _timestamp(
        _get(subscription_object, "current_period_end"),
        "current_period_end",
    )
    if period_start is not None or period_end is not None:
        return period_start, period_end

    items = _get(_get(subscription_object, "items", {}), "data", []) or []
    if len(items) != 1:
        return None, None
    item = items[0]
    return (
        _timestamp(_get(item, "current_period_start"), "item.current_period_start"),
        _timestamp(_get(item, "current_period_end"), "item.current_period_end"),
    )


def retrieve_stripe_subscription(subscription_id: str):
    if not stripe.api_key:
        raise RetryableStripeEventError("STRIPE_SECRET_KEY is not configured")
    try:
        return stripe.Subscription.retrieve(subscription_id, expand=["customer"])
    except stripe.error.InvalidRequestError as exc:
        if (
            getattr(exc, "http_status", None) == 404
            or getattr(exc, "code", None) == "resource_missing"
        ):
            raise StripeSubscriptionNotFoundError(
                "Stripe subscription no longer exists"
            ) from exc
        raise RetryableStripeEventError("Stripe subscription retrieval failed") from exc
    except stripe.error.StripeError as exc:
        raise RetryableStripeEventError("Stripe subscription retrieval failed") from exc


def retrieve_stripe_event(event_id: str):
    if not stripe.api_key:
        raise RetryableStripeEventError("STRIPE_SECRET_KEY is not configured")
    try:
        return stripe.Event.retrieve(event_id)
    except stripe.error.StripeError as exc:
        raise RetryableStripeEventError("Stripe event retrieval failed") from exc


def _subscription_id_for_event(event_type: str, data_object: Any) -> str:
    if event_type in SUBSCRIPTION_EVENT_TYPES:
        return _nonempty_identifier(_get(data_object, "id"), "Stripe Subscription ID")
    return _nonempty_identifier(
        _object_id(_get(data_object, "subscription")),
        "Stripe Subscription ID",
    )


def _authoritative_subscription_for_event(
    event_type: str,
    data_object: Any,
    retrieve_subscription: Callable[[str], Any],
):
    subscription_id = _subscription_id_for_event(event_type, data_object)
    try:
        return retrieve_subscription(subscription_id)
    except StripeSubscriptionNotFoundError:
        if event_type == "customer.subscription.deleted":
            return data_object
        raise RetryableStripeEventError(
            "Stripe subscription is temporarily unavailable"
        )
    except RetryableStripeEventError:
        raise
    except Exception as exc:
        raise RetryableStripeEventError("Stripe subscription retrieval failed") from exc


def _contact_hints(data_object: Any, subscription_object: Any) -> dict:
    customer = _get(subscription_object, "customer")
    customer_details = _get(data_object, "customer_details", {}) or {}
    customer_address = (
        _get(customer, "address", {})
        or _get(data_object, "customer_address", {})
        or _get(customer_details, "address", {})
        or {}
    )
    subscription_metadata = _get(subscription_object, "metadata", {}) or {}
    data_metadata = _get(data_object, "metadata", {}) or {}
    email = (
        _get(customer, "email")
        or _get(data_object, "customer_email")
        or _get(customer_details, "email")
        or _get(subscription_metadata, "email")
        or _get(data_metadata, "email")
    )
    return {
        "email": email,
        "billing_country": _get(customer_address, "country"),
        "preferred_language": (
            _get(subscription_metadata, "preferred_language")
            or _get(data_metadata, "preferred_language")
        ),
    }


def _resolve_plan(
    db: Session,
    *,
    price_ids: list[str],
) -> SubscriptionPlan:
    if len(price_ids) != 1:
        raise RetryableStripeEventError(
            "Subscription must contain exactly one configured Stripe Price ID"
        )

    plans = (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.stripe_price_id == price_ids[0],
            SubscriptionPlan.is_active.is_(True),
            SubscriptionPlan.is_configured.is_(True),
            SubscriptionPlan.archived_at.is_(None),
        )
        .all()
    )
    if not plans:
        raise RetryableStripeEventError("No active configured plan for Stripe Price ID")
    if len(plans) != 1:
        raise PermanentStripeEventError("Ambiguous Stripe Price ID plan mapping")
    return plans[0]


def _resolve_subscriber(
    db: Session,
    *,
    customer_id: str,
    contact_hints: dict,
) -> Subscriber:
    subscriber = (
        db.query(Subscriber)
        .filter(Subscriber.stripe_customer_id == customer_id)
        .with_for_update()
        .first()
    )
    if subscriber is None:
        subscriber = Subscriber(stripe_customer_id=customer_id)
        db.add(subscriber)
        db.flush()

    email = contact_hints.get("email")
    if isinstance(email, str) and email.strip():
        subscriber.stripe_email = email
        subscriber.normalized_email = normalize_subscriber_email(email)

    language = contact_hints.get("preferred_language")
    if isinstance(language, str) and language.strip():
        subscriber.preferred_language = language.strip()

    country = contact_hints.get("billing_country")
    if isinstance(country, str) and len(country.strip()) == 2:
        subscriber.billing_country = country.strip().upper()

    return subscriber


def _existing_subscription_lock_query(
    db: Session,
    subscription_id: str,
):
    return (
        db.query(SubscriberSubscription)
        .filter(SubscriberSubscription.stripe_subscription_id == subscription_id)
        .with_for_update()
    )


def _existing_subscription(
    db: Session,
    subscription_id: str,
) -> SubscriberSubscription | None:
    return _existing_subscription_lock_query(db, subscription_id).first()


def _entitlement_snapshot(entitlement: AccessEntitlement) -> tuple:
    return (
        entitlement.status,
        entitlement.access_starts_at,
        entitlement.paid_through_at,
        entitlement.grace_period_ends_at,
        entitlement.expires_at,
    )


def _subscription_snapshot(subscription: SubscriberSubscription) -> tuple:
    return (
        subscription.billing_status,
        subscription.stripe_status,
        subscription.current_period_start,
        subscription.current_period_end,
        subscription.cancel_at_period_end,
        subscription.cancelled_at,
        subscription.ended_at,
    )


def _apply_payment_failure(
    entitlement: AccessEntitlement,
    *,
    failure_at: datetime,
    paid_through: datetime | None,
    grace_days: int,
) -> None:
    """Enter grace only when persisted entitlement dates prove prior paid access."""
    has_prior_paid_access = (
        entitlement.access_starts_at is not None
        and entitlement.paid_through_at is not None
        and entitlement.access_starts_at <= entitlement.paid_through_at
    )
    if not has_prior_paid_access:
        entitlement.grace_period_ends_at = None
        return

    entitlement.status = EntitlementAccessStatus.grace_period
    entitlement.expires_at = None
    if paid_through is not None:
        entitlement.paid_through_at = paid_through

    candidate = failure_at + timedelta(days=grace_days)
    if paid_through is not None and paid_through > candidate:
        candidate = paid_through

    if entitlement.grace_period_ends_at is None:
        entitlement.grace_period_ends_at = candidate
    else:
        existing = entitlement.grace_period_ends_at
        fixed = min(existing, candidate)
        if paid_through is not None and fixed < paid_through:
            fixed = paid_through
        entitlement.grace_period_ends_at = fixed


def _apply_entitlement_state(
    entitlement: AccessEntitlement,
    subscription: SubscriberSubscription,
    *,
    event_created_at: datetime,
    now: datetime,
    payment_outcome: str | None,
    grace_days: int,
) -> None:
    period_start = subscription.current_period_start
    period_end = subscription.current_period_end

    if payment_outcome == "failed":
        subscription.billing_status = SubscriberBillingStatus.delinquent

        if entitlement.administratively_revoked:
            return

        _apply_payment_failure(
            entitlement,
            failure_at=event_created_at,
            paid_through=entitlement.paid_through_at,
            grace_days=grace_days,
        )
        return

    if subscription.billing_status == SubscriberBillingStatus.active:
        if period_end is None:
            raise RetryableStripeEventError(
                "Active Stripe subscription is missing current_period_end"
            )

        entitlement.access_starts_at = (
            entitlement.access_starts_at or period_start or now
        )

        # Only a confirmed payment may extend an existing paid boundary.
        # The initial active subscription still initializes the entitlement.
        if payment_outcome == "paid" or entitlement.paid_through_at is None:
            entitlement.paid_through_at = period_end

        entitlement.grace_period_ends_at = None
        entitlement.expires_at = None

        if not entitlement.administratively_revoked:
            entitlement.status = EntitlementAccessStatus.active

        return

    if subscription.billing_status == SubscriberBillingStatus.delinquent:
        if entitlement.administratively_revoked:
            return

        # Only invoice.payment_failed starts grace.
        return

    if subscription.billing_status == SubscriberBillingStatus.ended:
        # Keep the existing cancellation/ended semantics.
        entitlement.paid_through_at = period_end or entitlement.paid_through_at

        if entitlement.administratively_revoked:
            return

        effective_now = max(
            now,
            subscription.ended_at or now,
        )

        if (
            entitlement.paid_through_at is not None
            and effective_now < entitlement.paid_through_at
        ):
            entitlement.status = EntitlementAccessStatus.active
            entitlement.access_starts_at = (
                entitlement.access_starts_at or period_start or now
            )
            entitlement.expires_at = None
        else:
            entitlement.status = EntitlementAccessStatus.expired
            entitlement.expires_at = entitlement.paid_through_at or effective_now

        entitlement.grace_period_ends_at = None
        return

    if not entitlement.administratively_revoked:
        entitlement.status = EntitlementAccessStatus.pending
        entitlement.grace_period_ends_at = None
        

def _history_event_type(
    event_type: str,
    subscription_before: tuple,
    subscription: SubscriberSubscription,
    entitlement_before: tuple,
    entitlement: AccessEntitlement,
) -> str:
    previous_billing = subscription_before[0]
    previous_access = entitlement_before[0]
    new_billing = subscription.billing_status
    new_access = entitlement.status

    if (
        new_billing == SubscriberBillingStatus.active
        and new_access == EntitlementAccessStatus.active
        and (
            previous_billing == SubscriberBillingStatus.delinquent
            or previous_access == EntitlementAccessStatus.grace_period
        )
    ):
        return "stripe_payment_recovered"
    if (
        new_billing == SubscriberBillingStatus.delinquent
        and (
            previous_billing != SubscriberBillingStatus.delinquent
            or previous_access != new_access
        )
    ):
        return "stripe_payment_failed"
    if (
        new_access == EntitlementAccessStatus.expired
        and previous_access != EntitlementAccessStatus.expired
    ):
        return "stripe_entitlement_expired"
    if (
        new_billing == SubscriberBillingStatus.ended
        and previous_billing != SubscriberBillingStatus.ended
    ):
        return "stripe_subscription_ended"
    if (
        not subscription_before[4]
        and subscription.cancel_at_period_end
    ):
        return "stripe_cancellation_scheduled"
    if subscription_before != _subscription_snapshot(subscription):
        return "stripe_subscription_updated"
    if entitlement_before[0] != entitlement.status:
        return "stripe_access_status_changed"
    return "stripe_subscription_updated"


def synchronize_stripe_subscription(
    db: Session,
    *,
    event: Any,
    now: datetime,
    retrieve_subscription: Callable[[str], Any],
    grace_days: int,
) -> bool:
    now = _aware_utc(now, "now")
    event_id = _nonempty_identifier(_get(event, "id"), "Stripe event ID")
    event_type = _nonempty_identifier(_get(event, "type"), "Stripe event type")
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise IgnoredStripeEvent("Unsupported Stripe event type")

    event_created_at = _timestamp(
        _get(event, "created"),
        "Stripe event creation timestamp",
        required=True,
    )
    data_object = _get(_get(event, "data", {}), "object")
    if data_object is None:
        raise PermanentStripeEventError("Stripe event data.object is missing")

    if event_type == "checkout.session.completed":
        mode = _get(data_object, "mode")
        if mode is None:
            raise PermanentStripeEventError("Checkout session mode is missing")
        if mode != "subscription":
            raise IgnoredStripeEvent("Checkout session is not a subscription")

    subscription_id = _subscription_id_for_event(event_type, data_object)
    # Serialize synchronization for an existing local subscription before
    # retrieving Stripe's current state. This prevents two concurrent workers
    # from retrieving different snapshots and then applying them out of order.
    existing = _existing_subscription(db, subscription_id)

    authoritative = _authoritative_subscription_for_event(
        event_type,
        data_object,
        retrieve_subscription,
    )

    authoritative_subscription_id = _nonempty_identifier(
        _get(authoritative, "id"),
        "Stripe Subscription ID",
    )
    if authoritative_subscription_id != subscription_id:
        raise PermanentStripeEventError(
            "Retrieved Stripe subscription does not match the event subscription"
        )

    customer_id = _object_id(_get(authoritative, "customer"))
    if not customer_id and existing is not None:
        customer_id = existing.subscriber.stripe_customer_id
    customer_id = _nonempty_identifier(customer_id, "Stripe Customer ID")

    price_ids = _subscription_price_ids(authoritative)
    plan = _resolve_plan(
        db,
        price_ids=price_ids,
    )
    subscriber = _resolve_subscriber(
        db,
        customer_id=customer_id,
        contact_hints=_contact_hints(data_object, authoritative),
    )

    if existing is not None and existing.subscriber_id != subscriber.id:
        raise PermanentStripeEventError(
            "Stripe Subscription ID belongs to a different Stripe Customer ID"
        )
    if existing is not None and existing.plan_id != plan.id:
        raise PermanentStripeEventError(
            "Stripe Subscription ID resolved to a different configured plan"
        )

    raw_status = str(_get(authoritative, "status") or "").strip().lower()
    if not raw_status:
        raise PermanentStripeEventError("Stripe subscription status is missing")
    normalized_status = map_stripe_billing_status(raw_status)
    period_start, period_end = _subscription_period_timestamps(authoritative)
    cancellation_at = _timestamp(
        _get(authoritative, "canceled_at")
        or _get(authoritative, "cancelled_at"),
        "cancellation timestamp",
    )
    ended_at = _timestamp(_get(authoritative, "ended_at"), "ended_at")
    cancel_at_period_end = bool(_get(authoritative, "cancel_at_period_end", False))
    payment_outcome = None
    if event_type in INVOICE_PAID_EVENT_TYPES:
        payment_outcome = "paid"
    elif (
        event_type == "invoice.payment_failed"
        and normalized_status == SubscriberBillingStatus.delinquent
    ):
        payment_outcome = "failed"

    if existing is None:
        subscription_before = (
            SubscriberBillingStatus.pending,
            None,
            None,
            None,
            False,
            None,
            None,
        )
        subscription = SubscriberSubscription(
            subscriber_id=subscriber.id,
            plan_id=plan.id,
            stripe_subscription_id=subscription_id,
            stripe_status=raw_status,
            billing_status=normalized_status,
            current_period_start=period_start,
            current_period_end=period_end,
            cancel_at_period_end=cancel_at_period_end,
            cancelled_at=cancellation_at,
            ended_at=ended_at,
            latest_provider_event_created_at=event_created_at,
        )
        db.add(subscription)
        db.flush()
    else:
        subscription = existing
        subscription_before = _subscription_snapshot(subscription)

    subscription.stripe_status = raw_status
    subscription.billing_status = normalized_status
    subscription.current_period_start = period_start
    subscription.current_period_end = period_end
    subscription.cancel_at_period_end = cancel_at_period_end
    subscription.cancelled_at = cancellation_at
    subscription.ended_at = ended_at
    # Diagnostic high-water mark only. Distinct events are always reconciled
    # against Stripe rather than discarded by timestamp.
    latest_event_at = subscription.latest_provider_event_created_at
    if latest_event_at is None or event_created_at > latest_event_at:
        subscription.latest_provider_event_created_at = event_created_at

    entitlement = (
        db.query(AccessEntitlement)
        .filter(AccessEntitlement.subscriber_subscription_id == subscription.id)
        .with_for_update()
        .first()
    )
    if entitlement is None:
        entitlement = AccessEntitlement(
            subscriber_id=subscriber.id,
            subscriber_subscription_id=subscription.id,
            plan_id=plan.id,
            status=EntitlementAccessStatus.pending,
        )
        db.add(entitlement)
        db.flush()

    entitlement_before = _entitlement_snapshot(entitlement)

    entitlement_event_at = event_created_at

    if payment_outcome == "failed" and _get(authoritative, "test_clock"):
        entitlement_event_at = max(
            event_created_at,
            entitlement.paid_through_at or event_created_at,
        )

    _apply_entitlement_state(
        entitlement,
        subscription,
        event_created_at=entitlement_event_at,
        now=now,
        payment_outcome=payment_outcome,
        grace_days=grace_days,
    )

    subscription_after = _subscription_snapshot(subscription)
    entitlement_after = _entitlement_snapshot(entitlement)
    meaningful_change = (
        subscription_before != subscription_after
        or entitlement_before != entitlement_after
    )
    if not meaningful_change:
        return False

    # Phase 7: enqueue durable fulfillment work only. Provider calls and email
    # delivery are processed by the fulfillment worker outside this transaction.
    from services.subscriber_fulfillment_service import (
        enqueue_fulfillment_for_entitlement,
    )
    
    fulfillment_eligibility_at = max(
        now,
        event_created_at,
        entitlement.access_starts_at or now,
    )

    enqueue_fulfillment_for_entitlement(
        db,
        entitlement=entitlement,
        now=now,
        eligibility_at=fulfillment_eligibility_at,
    )

    access_event = SubscriptionAccessEvent(
        subscriber_id=subscriber.id,
        subscriber_subscription_id=subscription.id,
        entitlement_id=entitlement.id,
        event_type=_history_event_type(
            event_type,
            subscription_before,
            subscription,
            entitlement_before,
            entitlement,
        ),
        previous_billing_status=subscription_before[0].value,
        new_billing_status=subscription.billing_status.value,
        previous_access_status=entitlement_before[0].value,
        new_access_status=entitlement.status.value,
        reason=f"Processed verified Stripe event {event_type}",
        source=SubscriptionEventSource.stripe,
        external_event_id=event_id,
        event_metadata={
            "stripe_event_type": event_type,
            "plan_code": plan.code,
            "price_id": plan.stripe_price_id,
            "cancel_at_period_end": subscription.cancel_at_period_end,
        },
        occurred_at=event_created_at,
        recorded_at=now,
    )
    db.add(access_event)
    return True


def _integration_event_for_update(
    db: Session,
    event_id: str,
) -> IntegrationEvent | None:
    return (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.provider == IntegrationProvider.stripe,
            IntegrationEvent.external_event_id == event_id,
        )
        .with_for_update()
        .first()
    )


def _insert_or_get_integration_event(
    db: Session,
    *,
    event: Any,
    payload: bytes,
    received_at: datetime,
    authoritative_replay: bool = False,
) -> tuple[IntegrationEvent, bool]:
    event_id = _nonempty_identifier(_get(event, "id"), "Stripe event ID")
    event_type = _nonempty_identifier(_get(event, "type"), "Stripe event type")
    payload_checksum = hashlib.sha256(payload).hexdigest()
    existing = _integration_event_for_update(db, event_id)
    if existing is not None:
        if (
            not authoritative_replay
            and existing.payload_checksum is not None
            and existing.payload_checksum != payload_checksum
        ):
            raise PermanentStripeEventError(
                "Stripe event ID was redelivered with a different payload"
            )
        return existing, True

    integration_event = IntegrationEvent(
        provider=IntegrationProvider.stripe,
        external_event_id=event_id,
        event_type=event_type,
        provider_created_at=_timestamp(
            _get(event, "created"),
            "Stripe event creation timestamp",
        ),
        received_at=received_at,
        processing_status=IntegrationProcessingStatus.received,
        processing_attempts=0,
        payload_checksum=payload_checksum,
        selected_metadata=selected_event_metadata(event),
    )

    try:
        with db.begin_nested():
            db.add(integration_event)
            db.flush()
    except IntegrityError:
        integration_event = _integration_event_for_update(db, event_id)
        if integration_event is None:
            raise
        if (
            not authoritative_replay
            and integration_event.payload_checksum is not None
            and integration_event.payload_checksum != payload_checksum
        ):
            raise PermanentStripeEventError(
                "Stripe event ID was concurrently recorded with a different payload"
            )
        return integration_event, True

    return integration_event, False


def process_verified_stripe_event(
    db: Session,
    *,
    event: Any,
    payload: bytes,
    now: datetime,
    retrieve_subscription: Callable[[str], Any] | None = None,
    ignore_reason: str | None = None,
    force_retry: bool = False,
    authoritative_replay: bool = False,
) -> StripeProcessingOutcome:
    """Persist and transactionally process one signature-verified Stripe event."""
    now = _aware_utc(now, "now")
    integration_event, duplicate_delivery = _insert_or_get_integration_event(
        db,
        event=event,
        payload=payload,
        received_at=now,
        authoritative_replay=authoritative_replay,
    )

    try:
        max_attempts = processing_max_attempts()
        retry_seconds = processing_retry_seconds()
    except RetryableStripeEventError:
        logger.exception("Invalid Stripe integration retry configuration")
        max_attempts = 5
        retry_seconds = 300

    if integration_event.processing_status in {
        IntegrationProcessingStatus.processed,
        IntegrationProcessingStatus.ignored,
        IntegrationProcessingStatus.permanently_failed,
    }:
        db.commit()
        return StripeProcessingOutcome(
            integration_event.processing_status,
            duplicate=True,
        )

    if (
        integration_event.processing_status
        == IntegrationProcessingStatus.retryable_failure
        and not force_retry
    ):
        if integration_event.processing_attempts >= max_attempts:
            db.commit()
            return StripeProcessingOutcome(
                IntegrationProcessingStatus.retryable_failure,
                duplicate=True,
                retryable=False,
            )
        if (
            integration_event.next_retry_at is not None
            and now < integration_event.next_retry_at
        ):
            db.commit()
            return StripeProcessingOutcome(
                IntegrationProcessingStatus.retryable_failure,
                duplicate=True,
                retryable=True,
            )

    integration_event.processing_status = IntegrationProcessingStatus.processing
    integration_event.processing_attempts += 1
    integration_event.next_retry_at = None
    integration_event.last_error = None
    integration_event.updated_at = now
    db.flush()

    try:
        with db.begin_nested():
            if ignore_reason is not None:
                raise IgnoredStripeEvent(ignore_reason)
            synchronize_stripe_subscription(
                db,
                event=event,
                now=now,
                retrieve_subscription=(
                    retrieve_subscription or retrieve_stripe_subscription
                ),
                grace_days=payment_failure_grace_days(),
            )
            db.flush()
    except IgnoredStripeEvent as exc:
        integration_event.processing_status = IntegrationProcessingStatus.ignored
        integration_event.processed_at = now
        integration_event.last_error = persisted_error_text(exc)
        integration_event.updated_at = now
        db.commit()
        return StripeProcessingOutcome(
            IntegrationProcessingStatus.ignored,
            duplicate=duplicate_delivery,
        )
    except PermanentStripeEventError as exc:
        integration_event.processing_status = (
            IntegrationProcessingStatus.permanently_failed
        )
        integration_event.processed_at = now
        integration_event.last_error = persisted_error_text(exc)
        integration_event.updated_at = now
        db.commit()
        return StripeProcessingOutcome(
            IntegrationProcessingStatus.permanently_failed,
            duplicate=duplicate_delivery,
        )
    except RetryableStripeEventError as exc:
        attempts = integration_event.processing_attempts
        automatic_retry_available = attempts < max_attempts
        integration_event.processing_status = (
            IntegrationProcessingStatus.retryable_failure
        )
        integration_event.processed_at = None
        integration_event.next_retry_at = (
            None
            if not automatic_retry_available
            else now + timedelta(seconds=retry_seconds)
        )
        integration_event.last_error = persisted_error_text(exc)
        integration_event.updated_at = now
        db.commit()
        return StripeProcessingOutcome(
            integration_event.processing_status,
            duplicate=duplicate_delivery,
            retryable=automatic_retry_available,
        )
    except Exception as exc:
        logger.exception(
            "Unexpected Stripe event processing failure for %s",
            integration_event.external_event_id,
        )
        attempts = integration_event.processing_attempts
        automatic_retry_available = attempts < max_attempts
        integration_event.processing_status = (
            IntegrationProcessingStatus.retryable_failure
        )
        integration_event.processed_at = None
        integration_event.next_retry_at = (
            None
            if not automatic_retry_available
            else now + timedelta(seconds=retry_seconds)
        )
        integration_event.last_error = persisted_error_text(exc)
        integration_event.updated_at = now
        db.commit()
        return StripeProcessingOutcome(
            integration_event.processing_status,
            duplicate=duplicate_delivery,
            retryable=automatic_retry_available,
        )

    integration_event.processing_status = IntegrationProcessingStatus.processed
    integration_event.processed_at = now
    integration_event.updated_at = now
    db.commit()
    return StripeProcessingOutcome(
        IntegrationProcessingStatus.processed,
        duplicate=duplicate_delivery,
    )


def replay_stripe_integration_event(
    db: Session,
    *,
    event_id: str,
    now: datetime,
    retrieve_event: Callable[[str], Any] | None = None,
    retrieve_subscription: Callable[[str], Any] | None = None,
) -> StripeProcessingOutcome:
    """Replay a recoverable event using an authoritative Stripe Event lookup.

    Allowed replay transitions are received/processing/retryable_failure to
    processed, retryable_failure, or permanently_failed. Once a concurrent
    processor reaches processed, ignored, or permanently_failed, replay returns
    that terminal result without changing completion or retry metadata.
    """
    now = _aware_utc(now, "now")
    event_id = _nonempty_identifier(event_id, "Stripe event ID")

    def locked_replay_target():
        integration_event = _integration_event_for_update(db, event_id)
        if integration_event is None:
            db.rollback()
            raise PermanentStripeEventError(
                "Stripe IntegrationEvent does not exist"
            )
        if integration_event.processing_status in {
            IntegrationProcessingStatus.processed,
            IntegrationProcessingStatus.ignored,
            IntegrationProcessingStatus.permanently_failed,
        }:
            return integration_event, StripeProcessingOutcome(
                integration_event.processing_status,
                duplicate=True,
            )
        return integration_event, None

    integration_event, terminal_outcome = locked_replay_target()
    if terminal_outcome is not None:
        db.commit()
        return terminal_outcome

    # Do not hold a database row lock while calling Stripe.
    db.commit()
    event_retriever = retrieve_event or retrieve_stripe_event
    try:
        event = event_retriever(event_id)
    except RetryableStripeEventError as exc:
        integration_event, terminal_outcome = locked_replay_target()
        if terminal_outcome is not None:
            db.commit()
            return terminal_outcome
        integration_event.processing_status = (
            IntegrationProcessingStatus.retryable_failure
        )
        integration_event.processing_attempts += 1
        integration_event.next_retry_at = None
        integration_event.processed_at = None
        integration_event.last_error = persisted_error_text(exc)
        integration_event.updated_at = now
        db.commit()
        return StripeProcessingOutcome(
            IntegrationProcessingStatus.retryable_failure,
            duplicate=True,
            retryable=False,
        )

    if _get(event, "id") != event_id:
        integration_event, terminal_outcome = locked_replay_target()
        if terminal_outcome is not None:
            db.commit()
            return terminal_outcome
        integration_event.processing_status = (
            IntegrationProcessingStatus.permanently_failed
        )
        integration_event.processing_attempts += 1
        integration_event.next_retry_at = None
        integration_event.processed_at = now
        integration_event.last_error = persisted_error_text(
            PermanentStripeEventError(
                "Authoritative Stripe Event ID does not match replay request"
            )
        )
        integration_event.updated_at = now
        db.commit()
        return StripeProcessingOutcome(
            IntegrationProcessingStatus.permanently_failed,
            duplicate=True,
        )

    return process_verified_stripe_event(
        db,
        event=event,
        payload=b"",
        now=now,
        retrieve_subscription=retrieve_subscription,
        force_retry=True,
        authoritative_replay=True,
    )
