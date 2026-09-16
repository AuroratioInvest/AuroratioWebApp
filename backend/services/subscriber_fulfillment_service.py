"""Durable private-channel fulfillment for accountless subscribers.

Stripe webhooks enqueue local work only. Provider calls happen here, outside the
webhook transaction, and can be retried safely by workers or authenticated
administrator actions.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from services.email_service import send_private_access_instructions
from services.subscriber_domain import entitlement_grants_access
from services.telegram_private_channel_service import (
    TelegramInvite,
    TelegramPermanentError,
    TelegramPrivateChannelService,
    TelegramProviderError,
    sanitize_telegram_error,
)
from subscriber_models import (
    AccessEntitlement,
    AccessFulfillmentStatus,
    AuditActorType,
    AuditEvent,
    EntitlementAccessStatus,
    PlanChannelMapping,
    Subscriber,
    SubscriberAccessFulfillment,
    SubscriberSubscription,
    SubscriptionPlan,
    TelegramChannel,
)

logger = logging.getLogger(__name__)


CLAIMABLE_STATUSES = {
    AccessFulfillmentStatus.pending,
    AccessFulfillmentStatus.retryable_failure,
}
TERMINAL_STATUSES = {
    AccessFulfillmentStatus.delivered,
    AccessFulfillmentStatus.terminal_failure,
    AccessFulfillmentStatus.cancelled,
}
FULFILLMENT_BACKFILL_DEFAULT_LIMIT = 50
FULFILLMENT_BACKFILL_MAX_LIMIT = 200
FULFILLMENT_PROCESS_DEFAULT_LIMIT = 1
FULFILLMENT_PROCESS_MAX_LIMIT = 2


@dataclass(frozen=True)
class FulfillmentProcessResult:
    processed: int = 0
    delivered: int = 0
    retryable_failures: int = 0
    terminal_failures: int = 0
    cancelled: int = 0


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def fulfillment_max_attempts() -> int:
    raw = os.getenv("ACCESS_FULFILLMENT_MAX_ATTEMPTS", "5")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("ACCESS_FULFILLMENT_MAX_ATTEMPTS is invalid") from exc
    if value <= 0:
        raise ValueError("ACCESS_FULFILLMENT_MAX_ATTEMPTS is invalid")
    return value


def fulfillment_retry_delay_seconds() -> int:
    raw = os.getenv("ACCESS_FULFILLMENT_RETRY_SECONDS", "300")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("ACCESS_FULFILLMENT_RETRY_SECONDS is invalid") from exc
    if value <= 0:
        raise ValueError("ACCESS_FULFILLMENT_RETRY_SECONDS is invalid")
    return value


def fulfillment_claim_lease_seconds() -> int:
    raw = os.getenv("ACCESS_FULFILLMENT_CLAIM_LEASE_SECONDS", "900")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("ACCESS_FULFILLMENT_CLAIM_LEASE_SECONDS is invalid") from exc
    if value <= 0:
        raise ValueError("ACCESS_FULFILLMENT_CLAIM_LEASE_SECONDS is invalid")
    return value


def telegram_invite_ttl_hours() -> int:
    raw = os.getenv("TELEGRAM_INVITE_TTL_HOURS", "24")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("TELEGRAM_INVITE_TTL_HOURS is invalid") from exc
    if value <= 0 or value > 168:
        raise ValueError("TELEGRAM_INVITE_TTL_HOURS is invalid")
    return value


def _audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    reason: str,
    now: datetime,
    metadata: dict | None = None,
    actor_admin_user_id: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_type=AuditActorType.admin
            if actor_admin_user_id
            else AuditActorType.system,
            actor_admin_user_id=actor_admin_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            event_metadata=metadata,
            created_at=now,
        )
    )


def _record_mapping_configuration_gap(
    db: Session,
    *,
    entitlement: AccessEntitlement,
    now: datetime,
) -> None:
    _audit(
        db,
        action="access_fulfillment_configuration_missing",
        entity_type="access_entitlement",
        entity_id=entitlement.id,
        reason="No active configured private-channel mapping exists",
        now=now,
        metadata={"plan_id": entitlement.plan_id},
    )


def _eligible_mappings(db: Session, *, entitlement: AccessEntitlement):
    return (
        db.query(PlanChannelMapping, TelegramChannel, SubscriptionPlan)
        .join(TelegramChannel, TelegramChannel.id == PlanChannelMapping.channel_id)
        .join(SubscriptionPlan, SubscriptionPlan.id == PlanChannelMapping.plan_id)
        .filter(
            PlanChannelMapping.plan_id == entitlement.plan_id,
            PlanChannelMapping.is_active.is_(True),
            TelegramChannel.is_active.is_(True),
            TelegramChannel.is_configured.is_(True),
            TelegramChannel.archived_at.is_(None),
            TelegramChannel.telegram_chat_id.isnot(None),
            SubscriptionPlan.is_active.is_(True),
            SubscriptionPlan.is_configured.is_(True),
            SubscriptionPlan.archived_at.is_(None),
        )
        .order_by(PlanChannelMapping.created_at.asc(), PlanChannelMapping.id.asc())
        .all()
    )


def _cancel_undelivered_for_entitlement(
    db: Session,
    *,
    entitlement: AccessEntitlement,
    now: datetime,
) -> int:
    updated = (
        db.query(SubscriberAccessFulfillment)
        .filter(
            SubscriberAccessFulfillment.access_entitlement_id == entitlement.id,
            SubscriberAccessFulfillment.delivered_at.is_(None),
            SubscriberAccessFulfillment.status.in_(
                [
                    AccessFulfillmentStatus.pending,
                    AccessFulfillmentStatus.processing,
                    AccessFulfillmentStatus.retryable_failure,
                ]
            ),
        )
        .update(
            {
                SubscriberAccessFulfillment.status: AccessFulfillmentStatus.cancelled,
                SubscriberAccessFulfillment.failed_at: now,
                SubscriberAccessFulfillment.last_error_code: "entitlement_inactive",
                SubscriberAccessFulfillment.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if updated:
        _audit(
            db,
            action="access_fulfillment_cancelled",
            entity_type="access_entitlement",
            entity_id=entitlement.id,
            reason="Entitlement no longer grants access before delivery",
            now=now,
            metadata={"cancelled_records": updated},
        )
    return updated


def enqueue_fulfillment_for_entitlement(
    db: Session,
    *,
    entitlement: AccessEntitlement,
    now: datetime,
    eligibility_at: datetime | None = None,
) -> int:
    """Create missing fulfillment records for an access-granting entitlement."""
    now = _aware_utc(now, "now")
    eligibility_at = _aware_utc(eligibility_at or now, "eligibility_at")

    if not entitlement_grants_access(entitlement, now=eligibility_at):
        return _cancel_undelivered_for_entitlement(
            db,
            entitlement=entitlement,
            now=now,
        )
    
    mappings = _eligible_mappings(db, entitlement=entitlement)
    if not mappings:
        _record_mapping_configuration_gap(db, entitlement=entitlement, now=now)
        return 0

    created = 0
    for mapping, channel, plan in mappings:
        existing = (
            db.query(SubscriberAccessFulfillment)
            .filter(
                SubscriberAccessFulfillment.access_entitlement_id == entitlement.id,
                SubscriberAccessFulfillment.plan_channel_mapping_id == mapping.id,
            )
            .with_for_update()
            .first()
        )
        if existing is not None:
            if existing.delivered_at is not None:
                continue
            if existing.status == AccessFulfillmentStatus.cancelled:
                existing.status = AccessFulfillmentStatus.pending
                existing.next_attempt_at = now
                existing.failed_at = None
                existing.last_error_code = None
                existing.delivery_claimed_at = None
                existing.processing_claim_id = None
                existing.updated_at = now
            continue

        fulfillment = SubscriberAccessFulfillment(
            subscriber_id=entitlement.subscriber_id,
            subscriber_subscription_id=entitlement.subscriber_subscription_id,
            access_entitlement_id=entitlement.id,
            subscription_plan_id=plan.id,
            telegram_channel_id=channel.id,
            plan_channel_mapping_id=mapping.id,
            status=AccessFulfillmentStatus.pending,
            attempt_count=0,
            next_attempt_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            with db.begin_nested():
                db.add(fulfillment)
                db.flush()
            created += 1
            _audit(
                db,
                action="access_fulfillment_enqueued",
                entity_type="subscriber_access_fulfillment",
                entity_id=fulfillment.id,
                reason="Entitlement grants private-channel access",
                now=now,
                metadata={
                    "entitlement_id": entitlement.id,
                    "plan_code": plan.code,
                    "channel_code": channel.code,
                },
            )
        except IntegrityError:
            continue
    return created


def enqueue_missing_fulfillments_for_active_entitlements(
    db: Session,
    *,
    now: datetime,
    entitlement_id: str | None = None,
    dry_run: bool = False,
    limit: int = FULFILLMENT_BACKFILL_DEFAULT_LIMIT,
    after_entitlement_id: str | None = None,
) -> dict:
    now = _aware_utc(now, "now")
    if limit <= 0 or limit > FULFILLMENT_BACKFILL_MAX_LIMIT:
        raise ValueError("Backfill limit is outside the allowed range")
    query = db.query(AccessEntitlement).filter(
        AccessEntitlement.status.in_(
            [
                EntitlementAccessStatus.active,
                EntitlementAccessStatus.grace_period,
            ]
        ),
        AccessEntitlement.administratively_revoked.is_(False),
    )
    if entitlement_id:
        query = query.filter(AccessEntitlement.id == entitlement_id)
    elif after_entitlement_id:
        query = query.filter(AccessEntitlement.id > after_entitlement_id)
    query = query.order_by(AccessEntitlement.id.asc())
    entitlements = query.limit(limit + 1).all()
    batch = entitlements[:limit]
    has_more = len(entitlements) > limit
    next_cursor = batch[-1].id if has_more and batch and not entitlement_id else None

    checked = 0
    would_create = 0
    created = 0
    for entitlement in batch:
        if not entitlement_grants_access(entitlement, now=now):
            continue
        checked += 1
        missing = 0
        for mapping, _channel, _plan in _eligible_mappings(db, entitlement=entitlement):
            exists = (
                db.query(SubscriberAccessFulfillment.id)
                .filter(
                    SubscriberAccessFulfillment.access_entitlement_id == entitlement.id,
                    SubscriberAccessFulfillment.plan_channel_mapping_id == mapping.id,
                )
                .first()
            )
            if exists is None:
                missing += 1
        would_create += missing
        if missing and not dry_run:
            created += enqueue_fulfillment_for_entitlement(
                db,
                entitlement=entitlement,
                now=now,
            )
    if not dry_run:
        db.commit()
    return {
        "checked": checked,
        "would_create": would_create,
        "created": created,
        "limit": limit,
        "next_cursor": next_cursor,
    }


def _claim_one_due_fulfillment(db: Session, *, now: datetime) -> tuple[str, str] | None:
    stale_before = now - timedelta(seconds=fulfillment_claim_lease_seconds())
    claim_id = uuid.uuid4().hex
    candidate = (
        db.query(SubscriberAccessFulfillment)
        .filter(
            SubscriberAccessFulfillment.delivered_at.is_(None),
            (
                SubscriberAccessFulfillment.status.in_(list(CLAIMABLE_STATUSES))
                & (
                    (SubscriberAccessFulfillment.next_attempt_at.is_(None))
                    | (SubscriberAccessFulfillment.next_attempt_at <= now)
                )
            )
            | (
                (SubscriberAccessFulfillment.status == AccessFulfillmentStatus.processing)
                & (SubscriberAccessFulfillment.delivery_claimed_at < stale_before)
            )
        )
        .order_by(
            SubscriberAccessFulfillment.next_attempt_at.asc().nullsfirst(),
            SubscriberAccessFulfillment.created_at.asc(),
            SubscriberAccessFulfillment.id.asc(),
        )
        .first()
    )
    if candidate is None:
        return None

    current_status = candidate.status
    claimed = (
        db.query(SubscriberAccessFulfillment)
        .filter(
            SubscriberAccessFulfillment.id == candidate.id,
            SubscriberAccessFulfillment.delivered_at.is_(None),
            SubscriberAccessFulfillment.status == current_status,
            (
                SubscriberAccessFulfillment.status.in_(list(CLAIMABLE_STATUSES))
                | (
                    (SubscriberAccessFulfillment.status == AccessFulfillmentStatus.processing)
                    & (SubscriberAccessFulfillment.delivery_claimed_at < stale_before)
                )
            ),
        )
        .update(
            {
                SubscriberAccessFulfillment.status: AccessFulfillmentStatus.processing,
                SubscriberAccessFulfillment.delivery_claimed_at: now,
                SubscriberAccessFulfillment.processing_claim_id: claim_id,
                SubscriberAccessFulfillment.last_attempt_at: now,
                SubscriberAccessFulfillment.attempt_count: SubscriberAccessFulfillment.attempt_count + 1,
                SubscriberAccessFulfillment.last_error_code: None,
                SubscriberAccessFulfillment.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if claimed != 1:
        return None
    _audit(
        db,
        action="access_fulfillment_claimed",
        entity_type="subscriber_access_fulfillment",
        entity_id=candidate.id,
        reason="Private-channel fulfillment claimed for processing",
        now=now,
    )
    db.commit()
    return candidate.id, claim_id


def _mark_failure(
    db: Session,
    *,
    fulfillment: SubscriberAccessFulfillment,
    error_code: str,
    retryable: bool,
    now: datetime,
) -> None:
    max_attempts = fulfillment_max_attempts()
    if retryable and fulfillment.attempt_count < max_attempts:
        fulfillment.status = AccessFulfillmentStatus.retryable_failure
        fulfillment.next_attempt_at = now + timedelta(seconds=fulfillment_retry_delay_seconds())
    elif retryable:
        fulfillment.status = AccessFulfillmentStatus.terminal_failure
        fulfillment.next_attempt_at = None
    else:
        fulfillment.status = AccessFulfillmentStatus.terminal_failure
        fulfillment.next_attempt_at = None
    fulfillment.failed_at = now
    fulfillment.last_error_code = error_code[:100]
    fulfillment.delivery_claimed_at = None
    fulfillment.processing_claim_id = None
    fulfillment.updated_at = now
    _audit(
        db,
        action="access_fulfillment_failed",
        entity_type="subscriber_access_fulfillment",
        entity_id=fulfillment.id,
        reason="Private-channel fulfillment failed",
        now=now,
        metadata={
            "error_code": fulfillment.last_error_code,
            "retryable": retryable and fulfillment.status == AccessFulfillmentStatus.retryable_failure,
        },
    )


def _current_fulfillment_context(
    db: Session,
    *,
    fulfillment_id: str,
    claim_id: str | None = None,
) -> SubscriberAccessFulfillment | None:
    query = (
        db.query(SubscriberAccessFulfillment)
        .filter(SubscriberAccessFulfillment.id == fulfillment_id)
    )
    if claim_id is not None:
        query = query.filter(SubscriberAccessFulfillment.processing_claim_id == claim_id)
    return query.with_for_update().first()


def _fulfillment_still_eligible(
    fulfillment: SubscriberAccessFulfillment,
    *,
    now: datetime,
) -> bool:
    entitlement = fulfillment.entitlement
    mapping = fulfillment.plan_channel_mapping
    channel = fulfillment.channel
    plan = fulfillment.plan

    if not all([entitlement, mapping, channel, plan]):
        return False

    eligibility_at = max(
        now,
        entitlement.access_starts_at or now,
    )

    return (
        entitlement_grants_access(entitlement, now=eligibility_at)
        and mapping.is_active
        and channel.is_active
        and channel.is_configured
        and channel.archived_at is None
        and channel.telegram_chat_id is not None
        and plan.is_active
        and plan.is_configured
        and plan.archived_at is None
    )


async def process_one_fulfillment(
    fulfillment_id: str,
    *,
    claim_id: str,
    session_factory: Callable[[], Session] = SessionLocal,
    telegram_service: TelegramPrivateChannelService | None = None,
    email_sender: Callable[..., Awaitable[bool]] = send_private_access_instructions,
    now: datetime,
) -> AccessFulfillmentStatus:
    now = _aware_utc(now, "now")
    telegram_service = telegram_service or TelegramPrivateChannelService()

    db = session_factory()
    try:
        fulfillment = _current_fulfillment_context(
            db,
            fulfillment_id=fulfillment_id,
            claim_id=claim_id,
        )
        if fulfillment is None:
            return AccessFulfillmentStatus.cancelled
        if fulfillment.delivered_at is not None:
            return AccessFulfillmentStatus.delivered
        if fulfillment.status != AccessFulfillmentStatus.processing:
            return fulfillment.status
        if not _fulfillment_still_eligible(fulfillment, now=now):
            fulfillment.status = AccessFulfillmentStatus.cancelled
            fulfillment.failed_at = now
            fulfillment.last_error_code = "entitlement_inactive"
            fulfillment.delivery_claimed_at = None
            fulfillment.processing_claim_id = None
            fulfillment.updated_at = now
            _audit(
                db,
                action="access_fulfillment_cancelled",
                entity_type="subscriber_access_fulfillment",
                entity_id=fulfillment.id,
                reason="Entitlement no longer grants access before invite creation",
                now=now,
            )
            db.commit()
            return fulfillment.status

        channel = fulfillment.channel
        chat_id = int(channel.telegram_chat_id)
        invite_expires_at = now + timedelta(hours=telegram_invite_ttl_hours())
        invite_name = f"AuroRatio {fulfillment.id[:8]}"
        db.commit()
    finally:
        db.close()

    invite: TelegramInvite | None = None
    try:
        invite = await telegram_service.create_single_use_invite(
            chat_id=chat_id,
            name=invite_name,
            expires_at=invite_expires_at,
        )
    except TelegramPermanentError as exc:
        db = session_factory()
        try:
            fulfillment = _current_fulfillment_context(
                db,
                fulfillment_id=fulfillment_id,
                claim_id=claim_id,
            )
            if fulfillment and fulfillment.status == AccessFulfillmentStatus.processing:
                _mark_failure(
                    db,
                    fulfillment=fulfillment,
                    error_code=getattr(exc, "error_code", "telegram_permanent_error"),
                    retryable=False,
                    now=now,
                )
                db.commit()
                return fulfillment.status
        finally:
            db.close()
        return AccessFulfillmentStatus.terminal_failure
    except TelegramProviderError as exc:
        db = session_factory()
        try:
            fulfillment = _current_fulfillment_context(
                db,
                fulfillment_id=fulfillment_id,
                claim_id=claim_id,
            )
            if fulfillment and fulfillment.status == AccessFulfillmentStatus.processing:
                _mark_failure(
                    db,
                    fulfillment=fulfillment,
                    error_code=getattr(exc, "error_code", "telegram_provider_error"),
                    retryable=True,
                    now=now,
                )
                _audit(
                    db,
                    action="access_fulfillment_provider_create_failed",
                    entity_type="subscriber_access_fulfillment",
                    entity_id=fulfillment.id,
                    reason="Telegram invite creation failed",
                    now=now,
                    metadata={"error": sanitize_telegram_error(exc)},
                )
                db.commit()
                return fulfillment.status
        finally:
            db.close()
        return AccessFulfillmentStatus.retryable_failure

    # Persist safe invite metadata, then re-read eligibility before sending.
    db = session_factory()
    try:
        fulfillment = _current_fulfillment_context(
            db,
            fulfillment_id=fulfillment_id,
            claim_id=claim_id,
        )
        if fulfillment is None or fulfillment.status != AccessFulfillmentStatus.processing:
            return AccessFulfillmentStatus.cancelled
        if fulfillment.delivered_at is not None:
            return AccessFulfillmentStatus.delivered
        fulfillment.provider_invite_reference = invite.provider_reference
        fulfillment.invite_expires_at = invite.expires_at
        fulfillment.updated_at = now
        _audit(
            db,
            action="access_fulfillment_invite_created",
            entity_type="subscriber_access_fulfillment",
            entity_id=fulfillment.id,
            reason="Provider invite created for private-channel fulfillment",
            now=now,
            metadata={"invite_expires_at": invite.expires_at.isoformat()},
        )
        if not _fulfillment_still_eligible(fulfillment, now=now):
            revoked = await telegram_service.revoke_invite(
                chat_id=int(fulfillment.channel.telegram_chat_id),
                invite_url=invite.invite_url,
            )
            fulfillment.status = AccessFulfillmentStatus.cancelled
            fulfillment.failed_at = now
            fulfillment.last_error_code = "entitlement_inactive"
            fulfillment.delivery_claimed_at = None
            fulfillment.processing_claim_id = None
            fulfillment.updated_at = now
            _audit(
                db,
                action="access_fulfillment_cancelled",
                entity_type="subscriber_access_fulfillment",
                entity_id=fulfillment.id,
                reason="Entitlement no longer grants access before email delivery",
                now=now,
                metadata={"provider_invite_revoked": revoked},
            )
            db.commit()
            return fulfillment.status
        subscriber = fulfillment.subscriber
        plan = fulfillment.plan
        locale = subscriber.preferred_language if subscriber.preferred_language in {"en", "fr"} else "en"
        email = subscriber.stripe_email or subscriber.normalized_email
        plan_label = plan.display_name_fr if locale == "fr" else plan.display_name_en
        # Keep ownership locked through provider acceptance and its durable
        # acknowledgement. A stale-lease worker or manual retry must not send
        # between the provider response and the delivered_at commit.
        db.flush()
        delivered = False
        if email:
            try:
                delivered = await email_sender(
                    to_email=email,
                    invitations=[
                        {
                            "label": plan_label,
                            "url": invite.invite_url,
                            "expires_at": invite.expires_at,
                        }
                    ],
                    locale=locale,
                )
            except Exception:
                logger.error("Private access email delivery raised an error")

        if delivered:
            fulfillment.status = AccessFulfillmentStatus.delivered
            fulfillment.delivered_at = now
            fulfillment.next_attempt_at = None
            fulfillment.delivery_claimed_at = None
            fulfillment.processing_claim_id = None
            fulfillment.last_error_code = None
            fulfillment.updated_at = now
            _audit(
                db,
                action="access_fulfillment_delivered",
                entity_type="subscriber_access_fulfillment",
                entity_id=fulfillment.id,
                reason="Private-channel invitation email accepted by provider",
                now=now,
            )
        else:
            revoked = await telegram_service.revoke_invite(
                chat_id=int(fulfillment.channel.telegram_chat_id),
                invite_url=invite.invite_url,
            )
            _mark_failure(
                db,
                fulfillment=fulfillment,
                error_code="email_delivery_failed",
                retryable=True,
                now=now,
            )
            _audit(
                db,
                action="access_fulfillment_invite_revocation_attempted",
                entity_type="subscriber_access_fulfillment",
                entity_id=fulfillment.id,
                reason="Invite revocation attempted after email delivery failure",
                now=now,
                metadata={"provider_invite_revoked": revoked},
            )
        db.commit()
        return fulfillment.status
    finally:
        db.close()


async def process_due_fulfillments(
    *,
    limit: int = FULFILLMENT_PROCESS_DEFAULT_LIMIT,
    session_factory: Callable[[], Session] = SessionLocal,
    telegram_service: TelegramPrivateChannelService | None = None,
    email_sender: Callable[..., Awaitable[bool]] = send_private_access_instructions,
    now: datetime,
) -> FulfillmentProcessResult:
    now = _aware_utc(now, "now")
    result = FulfillmentProcessResult()
    counts = {
        "processed": 0,
        "delivered": 0,
        "retryable_failures": 0,
        "terminal_failures": 0,
        "cancelled": 0,
    }
    for _ in range(limit):
        db = session_factory()
        try:
            claim = _claim_one_due_fulfillment(db, now=now)
        finally:
            db.close()
        if not claim:
            break
        fulfillment_id, claim_id = claim
        status = await process_one_fulfillment(
            fulfillment_id,
            claim_id=claim_id,
            session_factory=session_factory,
            telegram_service=telegram_service,
            email_sender=email_sender,
            now=now,
        )
        counts["processed"] += 1
        if status == AccessFulfillmentStatus.delivered:
            counts["delivered"] += 1
        elif status == AccessFulfillmentStatus.retryable_failure:
            counts["retryable_failures"] += 1
        elif status == AccessFulfillmentStatus.terminal_failure:
            counts["terminal_failures"] += 1
        elif status == AccessFulfillmentStatus.cancelled:
            counts["cancelled"] += 1
    return FulfillmentProcessResult(**counts)


def record_manual_due_processing_requested(
    db: Session,
    *,
    admin_user_id: str,
    limit: int,
    now: datetime,
) -> None:
    now = _aware_utc(now, "now")
    _audit(
        db,
        action="access_fulfillment_due_processing_requested",
        entity_type="subscriber_access_fulfillment",
        entity_id="due",
        reason="Administrator requested due fulfillment processing",
        now=now,
        metadata={"limit": limit},
        actor_admin_user_id=admin_user_id,
    )
    db.commit()


def request_manual_fulfillment_retry(
    db: Session,
    *,
    fulfillment_id: str,
    admin_user_id: str,
    now: datetime,
) -> SubscriberAccessFulfillment:
    now = _aware_utc(now, "now")
    fulfillment = (
        db.query(SubscriberAccessFulfillment)
        .filter(SubscriberAccessFulfillment.id == fulfillment_id)
        .with_for_update()
        .first()
    )
    if fulfillment is None:
        raise LookupError("Fulfillment not found")
    if (
        fulfillment.delivered_at is not None
        or fulfillment.status == AccessFulfillmentStatus.delivered
        or (
            fulfillment.status == AccessFulfillmentStatus.processing
            and fulfillment.delivery_claimed_at is not None
            and fulfillment.delivery_claimed_at
            >= now - timedelta(seconds=fulfillment_claim_lease_seconds())
        )
    ):
        return fulfillment
    fulfillment.status = AccessFulfillmentStatus.pending
    fulfillment.next_attempt_at = now
    fulfillment.delivery_claimed_at = None
    fulfillment.processing_claim_id = None
    fulfillment.failed_at = None
    fulfillment.last_error_code = None
    fulfillment.updated_at = now
    _audit(
        db,
        action="access_fulfillment_manual_retry_requested",
        entity_type="subscriber_access_fulfillment",
        entity_id=fulfillment.id,
        reason="Administrator requested fulfillment retry",
        now=now,
        actor_admin_user_id=admin_user_id,
    )
    db.commit()
    return fulfillment
