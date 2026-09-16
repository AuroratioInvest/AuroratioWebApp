"""Small deterministic helpers for the accountless subscriber domain."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from subscriber_models import (
    AccessEntitlement,
    AuditEvent,
    EntitlementAccessStatus,
    SubscriptionAccessEvent,
)


def normalize_subscriber_email(email: str | None) -> str | None:
    if email is None:
        return None
    normalized = email.strip().casefold()
    return normalized or None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def entitlement_grants_access(
    entitlement: AccessEntitlement,
    *,
    now: datetime,
) -> bool:
    """Evaluate access without consulting billing state or the system clock.

    Access starts inclusively at ``access_starts_at``. Paid-through, grace, and
    explicit expiration deadlines are also inclusive and deny access only after
    their respective timestamps.
    """
    evaluated_at = _as_utc(now)
    if evaluated_at is None:
        return False

    if (
        entitlement.administratively_revoked
        or entitlement.status == EntitlementAccessStatus.revoked
    ):
        return False

    starts_at = _as_utc(entitlement.access_starts_at)
    if starts_at is None or starts_at > evaluated_at:
        return False

    expires_at = _as_utc(entitlement.expires_at)
    if entitlement.expires_at is not None and expires_at is None:
        return False
    if expires_at is not None and evaluated_at > expires_at:
        return False

    if entitlement.status == EntitlementAccessStatus.active:
        paid_through = _as_utc(entitlement.paid_through_at)
        return paid_through is not None and evaluated_at <= paid_through

    if entitlement.status == EntitlementAccessStatus.grace_period:
        grace_deadline = _as_utc(entitlement.grace_period_ends_at)
        return grace_deadline is not None and evaluated_at <= grace_deadline

    return False


def append_subscription_access_event(
    db: Session,
    event: SubscriptionAccessEvent,
) -> SubscriptionAccessEvent:
    db.add(event)
    return event


def append_audit_event(db: Session, event: AuditEvent) -> AuditEvent:
    db.add(event)
    return event
