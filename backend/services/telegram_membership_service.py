"""Telegram membership binding and expired-access reconciliation."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from database import SessionLocal
from services.subscriber_domain import entitlement_grants_access
from services.telegram_private_channel_service import (
    TelegramPermanentError,
    TelegramPrivateChannelService,
    TelegramProviderError,
    sanitize_telegram_error,
    telegram_invite_provider_reference,
)
from subscriber_models import (
    AccessEntitlement,
    AccessFulfillmentStatus,
    PlanChannelMapping,
    SubscriberAccessFulfillment,
    SubscriberSubscription,
    TelegramChannel,
    TelegramMembership,
    TelegramMembershipStatus,
)

MEMBERSHIP_PROCESS_DEFAULT_LIMIT = 5
MEMBERSHIP_PROCESS_MAX_LIMIT = 25


@dataclass(frozen=True)
class MembershipReconciliationResult:
    processed: int = 0
    removed: int = 0
    retryable_failures: int = 0
    terminal_failures: int = 0
    retained: int = 0


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def membership_max_attempts() -> int:
    value = int(os.getenv("ACCESS_REMOVAL_MAX_ATTEMPTS", "5"))
    if value <= 0:
        raise ValueError("ACCESS_REMOVAL_MAX_ATTEMPTS is invalid")
    return value


def membership_retry_seconds() -> int:
    value = int(os.getenv("ACCESS_REMOVAL_RETRY_SECONDS", "300"))
    if value <= 0:
        raise ValueError("ACCESS_REMOVAL_RETRY_SECONDS is invalid")
    return value


def membership_claim_lease_seconds() -> int:
    value = int(os.getenv("ACCESS_REMOVAL_CLAIM_LEASE_SECONDS", "900"))
    if value <= 0:
        raise ValueError("ACCESS_REMOVAL_CLAIM_LEASE_SECONDS is invalid")
    return value


def record_chat_member_update(db: Session, *, update: dict, now: datetime) -> bool:
    """Bind a Telegram user to the fulfillment invite used to join the channel."""
    now = _aware_utc(now, "now")
    event = update.get("chat_member")
    if not isinstance(event, dict):
        return False

    chat = event.get("chat") or {}
    new_member = event.get("new_chat_member") or {}
    user = new_member.get("user") or {}
    invite_link = event.get("invite_link") or {}

    telegram_chat_id = chat.get("id")
    telegram_user_id = user.get("id")
    new_status = str(new_member.get("status") or "")

    if not isinstance(telegram_chat_id, int) or not isinstance(telegram_user_id, int):
        return False

    channel = (
        db.query(TelegramChannel)
        .filter(TelegramChannel.telegram_chat_id == telegram_chat_id)
        .first()
    )
    if channel is None:
        return False

    # Telegram may also notify us when a member leaves or is kicked.
    if new_status in {"left", "kicked"}:
        membership = (
            db.query(TelegramMembership)
            .filter(
                TelegramMembership.telegram_channel_id == channel.id,
                TelegramMembership.telegram_user_id == telegram_user_id,
            )
            .first()
        )
        if membership is not None:
            membership.status = TelegramMembershipStatus.removed
            membership.removed_at = now
            membership.processing_claim_id = None
            membership.processing_started_at = None
            membership.next_attempt_at = None
            membership.updated_at = now
            db.commit()
            return True
        return False

    if new_status not in {"member", "administrator", "creator", "restricted"}:
        return False

    raw_invite = invite_link.get("invite_link")
    if not isinstance(raw_invite, str) or not raw_invite.strip():
        # We deliberately refuse to guess subscriber ownership when Telegram does
        # not tell us which AuroRatio invite was used.
        return False

    provider_reference = telegram_invite_provider_reference(raw_invite.strip())
    fulfillment = (
        db.query(SubscriberAccessFulfillment)
        .filter(
            SubscriberAccessFulfillment.provider_invite_reference == provider_reference,
            SubscriberAccessFulfillment.telegram_channel_id == channel.id,
            SubscriberAccessFulfillment.status == AccessFulfillmentStatus.delivered,
        )
        .order_by(SubscriberAccessFulfillment.created_at.desc())
        .first()
    )
    if fulfillment is None:
        return False

    membership = (
        db.query(TelegramMembership)
        .filter(
            TelegramMembership.telegram_channel_id == channel.id,
            TelegramMembership.telegram_user_id == telegram_user_id,
        )
        .first()
    )
    if membership is None:
        membership = TelegramMembership(
            subscriber_id=fulfillment.subscriber_id,
            subscriber_subscription_id=fulfillment.subscriber_subscription_id,
            access_entitlement_id=fulfillment.access_entitlement_id,
            access_fulfillment_id=fulfillment.id,
            telegram_channel_id=channel.id,
            telegram_chat_id=telegram_chat_id,
            telegram_user_id=telegram_user_id,
            status=TelegramMembershipStatus.active,
            joined_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(membership)
    else:
        # Re-subscription/rejoin: bind the same Telegram user to the newest paid
        # fulfillment rather than creating duplicate channel membership rows.
        membership.subscriber_id = fulfillment.subscriber_id
        membership.subscriber_subscription_id = fulfillment.subscriber_subscription_id
        membership.access_entitlement_id = fulfillment.access_entitlement_id
        membership.access_fulfillment_id = fulfillment.id
        membership.telegram_chat_id = telegram_chat_id
        membership.status = TelegramMembershipStatus.active
        membership.joined_at = now
        membership.removed_at = None
        membership.attempt_count = 0
        membership.last_attempt_at = None
        membership.next_attempt_at = None
        membership.processing_claim_id = None
        membership.processing_started_at = None
        membership.last_error_code = None
        membership.last_error_message = None
        membership.updated_at = now

    db.commit()
    return True


def _subscriber_still_has_channel_access(
    db: Session,
    *,
    membership: TelegramMembership,
    now: datetime,
) -> bool:
    """Avoid removing a subscriber who still has valid access to this channel."""

    entitlement_rows = (
        db.query(AccessEntitlement, SubscriberSubscription)
        .join(
            SubscriberSubscription,
            SubscriberSubscription.id == AccessEntitlement.subscriber_subscription_id,
        )
        .join(
            PlanChannelMapping,
            PlanChannelMapping.plan_id == AccessEntitlement.plan_id,
        )
        .filter(
            AccessEntitlement.subscriber_id == membership.subscriber_id,
            PlanChannelMapping.channel_id == membership.telegram_channel_id,
            PlanChannelMapping.is_active.is_(True),
        )
        .all()
    )

    for entitlement, subscription in entitlement_rows:
        evaluation_time = max(
            now,
            subscription.latest_provider_event_created_at or now,
            entitlement.access_starts_at or now,
        )

        if entitlement_grants_access(
            entitlement,
            now=evaluation_time,
        ):
            return True

    return False


def _claim_one(db: Session, *, now: datetime) -> tuple[str, str] | None:
    stale_before = now - timedelta(seconds=membership_claim_lease_seconds())

    candidates = (
        db.query(TelegramMembership)
        .filter(
            TelegramMembership.status.in_(
                [
                    TelegramMembershipStatus.active,
                    TelegramMembershipStatus.removal_pending,
                    TelegramMembershipStatus.retryable_failure,
                    TelegramMembershipStatus.processing,
                ]
            )
        )
        .order_by(TelegramMembership.created_at.asc())
        .all()
    )

    for membership in candidates:
        if membership.status == TelegramMembershipStatus.retryable_failure:
            if membership.next_attempt_at is not None and membership.next_attempt_at > now:
                continue
        elif membership.status == TelegramMembershipStatus.processing:
            if (
                membership.processing_started_at is not None
                and membership.processing_started_at >= stale_before
            ):
                continue

        if _subscriber_still_has_channel_access(db, membership=membership, now=now):
            if membership.status != TelegramMembershipStatus.active:
                membership.status = TelegramMembershipStatus.active
                membership.next_attempt_at = None
                membership.processing_claim_id = None
                membership.processing_started_at = None
                membership.updated_at = now
                db.commit()
            continue

        claim_id = uuid.uuid4().hex
        membership.status = TelegramMembershipStatus.processing
        membership.processing_claim_id = claim_id
        membership.processing_started_at = now
        membership.last_attempt_at = now
        membership.attempt_count += 1
        membership.updated_at = now
        db.commit()
        return membership.id, claim_id

    return None


async def _process_claim(
    membership_id: str,
    claim_id: str,
    *,
    now: datetime,
    session_factory: Callable[[], Session],
    telegram_service: TelegramPrivateChannelService,
) -> TelegramMembershipStatus:
    db = session_factory()
    try:
        membership = (
            db.query(TelegramMembership)
            .filter(
                TelegramMembership.id == membership_id,
                TelegramMembership.processing_claim_id == claim_id,
                TelegramMembership.status == TelegramMembershipStatus.processing,
            )
            .with_for_update()
            .first()
        )
        if membership is None:
            return TelegramMembershipStatus.removed

        if _subscriber_still_has_channel_access(db, membership=membership, now=now):
            membership.status = TelegramMembershipStatus.active
            membership.processing_claim_id = None
            membership.processing_started_at = None
            membership.next_attempt_at = None
            membership.updated_at = now
            db.commit()
            return membership.status

        chat_id = int(membership.telegram_chat_id)
        user_id = int(membership.telegram_user_id)
        db.commit()
    finally:
        db.close()

    try:
        await telegram_service.remove_member(chat_id=chat_id, user_id=user_id)
    except TelegramPermanentError as exc:
        retryable = False
        error_code = getattr(exc, "error_code", "telegram_permanent_error")
        error_message = sanitize_telegram_error(exc)
    except TelegramProviderError as exc:
        retryable = bool(getattr(exc, "retryable", True))
        error_code = getattr(exc, "error_code", "telegram_provider_error")
        error_message = sanitize_telegram_error(exc)
    else:
        db = session_factory()
        try:
            membership = (
                db.query(TelegramMembership)
                .filter(
                    TelegramMembership.id == membership_id,
                    TelegramMembership.processing_claim_id == claim_id,
                )
                .with_for_update()
                .first()
            )
            if membership is None:
                return TelegramMembershipStatus.removed
            membership.status = TelegramMembershipStatus.removed
            membership.removed_at = now
            membership.next_attempt_at = None
            membership.processing_claim_id = None
            membership.processing_started_at = None
            membership.last_error_code = None
            membership.last_error_message = None
            membership.updated_at = now
            db.commit()
            return membership.status
        finally:
            db.close()

    db = session_factory()
    try:
        membership = (
            db.query(TelegramMembership)
            .filter(
                TelegramMembership.id == membership_id,
                TelegramMembership.processing_claim_id == claim_id,
            )
            .with_for_update()
            .first()
        )
        if membership is None:
            return TelegramMembershipStatus.terminal_failure

        if retryable and membership.attempt_count < membership_max_attempts():
            membership.status = TelegramMembershipStatus.retryable_failure
            membership.next_attempt_at = now + timedelta(seconds=membership_retry_seconds())
        else:
            membership.status = TelegramMembershipStatus.terminal_failure
            membership.next_attempt_at = None
        membership.last_error_code = error_code[:100]
        membership.last_error_message = error_message[:500]
        membership.processing_claim_id = None
        membership.processing_started_at = None
        membership.updated_at = now
        db.commit()
        return membership.status
    finally:
        db.close()


async def process_due_membership_removals(
    *,
    limit: int = MEMBERSHIP_PROCESS_DEFAULT_LIMIT,
    now: datetime,
    session_factory: Callable[[], Session] = SessionLocal,
    telegram_service: TelegramPrivateChannelService | None = None,
) -> MembershipReconciliationResult:
    now = _aware_utc(now, "now")
    if limit <= 0 or limit > MEMBERSHIP_PROCESS_MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MEMBERSHIP_PROCESS_MAX_LIMIT}")

    telegram_service = telegram_service or TelegramPrivateChannelService()
    counts = {
        "processed": 0,
        "removed": 0,
        "retryable_failures": 0,
        "terminal_failures": 0,
        "retained": 0,
    }

    for _ in range(limit):
        db = session_factory()
        try:
            claim = _claim_one(db, now=now)
        finally:
            db.close()
        if claim is None:
            break

        membership_id, claim_id = claim
        status = await _process_claim(
            membership_id,
            claim_id,
            now=now,
            session_factory=session_factory,
            telegram_service=telegram_service,
        )
        counts["processed"] += 1
        if status == TelegramMembershipStatus.removed:
            counts["removed"] += 1
        elif status == TelegramMembershipStatus.retryable_failure:
            counts["retryable_failures"] += 1
        elif status == TelegramMembershipStatus.terminal_failure:
            counts["terminal_failures"] += 1
        elif status == TelegramMembershipStatus.active:
            counts["retained"] += 1

    return MembershipReconciliationResult(**counts)
