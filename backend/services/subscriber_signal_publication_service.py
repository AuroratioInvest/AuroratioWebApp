"""Admin-controlled durable signal publication for accountless subscribers."""

from __future__ import annotations

import html
import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from services.telegram_private_channel_service import (
    TelegramPermanentError,
    TelegramPrivateChannelService,
    TelegramProviderError,
    TelegramRateLimitError,
    sanitize_telegram_error,
)
from subscriber_models import (
    AuditActorType,
    AuditEvent,
    PlanChannelMapping,
    SignalDeliveryAttemptOutcome,
    SignalPublicationStatus,
    SubscriberSignal,
    SubscriberSignalDeliveryAttempt,
    SubscriberSignalDirection,
    SubscriberSignalPlanTarget,
    SubscriberSignalPublication,
    SubscriberSignalStatus,
    SubscriptionPlan,
    TelegramChannel,
)

logger = logging.getLogger(__name__)

SIGNAL_PUBLICATION_DEFAULT_LIMIT = 1
SIGNAL_PUBLICATION_MAX_LIMIT = 2
SIGNAL_BACKFILL_DEFAULT_LIMIT = 50
SIGNAL_BACKFILL_MAX_LIMIT = 200
SIGNAL_PUBLICATION_MAX_ATTEMPTS = 5
SIGNAL_PUBLICATION_RETRY_SECONDS = 300
SIGNAL_PUBLICATION_CLAIM_LEASE_SECONDS = 900

CLAIMABLE_PUBLICATION_STATUSES = {
    SignalPublicationStatus.pending,
    SignalPublicationStatus.retryable_failure,
}


@dataclass(frozen=True)
class SignalPublicationProcessResult:
    processed: int = 0
    published: int = 0
    retryable_failures: int = 0
    terminal_failures: int = 0
    cancelled: int = 0


@dataclass(frozen=True)
class OperationalTestSignalResult:
    signal_id: str | None
    status: str
    created: bool
    dry_run: bool
    publications_enqueued: int
    would_enqueue_publications: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def publication_max_attempts() -> int:
    raw = os.getenv("SIGNAL_PUBLICATION_MAX_ATTEMPTS", str(SIGNAL_PUBLICATION_MAX_ATTEMPTS))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("SIGNAL_PUBLICATION_MAX_ATTEMPTS is invalid") from exc
    if value <= 0:
        raise ValueError("SIGNAL_PUBLICATION_MAX_ATTEMPTS is invalid")
    return value


def publication_retry_delay_seconds() -> int:
    raw = os.getenv("SIGNAL_PUBLICATION_RETRY_SECONDS", str(SIGNAL_PUBLICATION_RETRY_SECONDS))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("SIGNAL_PUBLICATION_RETRY_SECONDS is invalid") from exc
    if value <= 0:
        raise ValueError("SIGNAL_PUBLICATION_RETRY_SECONDS is invalid")
    return value


def publication_claim_lease_seconds() -> int:
    raw = os.getenv(
        "SIGNAL_PUBLICATION_CLAIM_LEASE_SECONDS",
        str(SIGNAL_PUBLICATION_CLAIM_LEASE_SECONDS),
    )
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("SIGNAL_PUBLICATION_CLAIM_LEASE_SECONDS is invalid") from exc
    if value <= 0:
        raise ValueError("SIGNAL_PUBLICATION_CLAIM_LEASE_SECONDS is invalid")
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
            actor_type=AuditActorType.admin if actor_admin_user_id else AuditActorType.system,
            actor_admin_user_id=actor_admin_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            reason=reason,
            event_metadata=metadata,
            created_at=now,
        )
    )


def _clean_text(value: str | None, field: str, *, max_length: int = 1000) -> str:
    if value is None:
        raise ValueError(f"{field} is required")
    cleaned = " ".join(str(value).strip().split())
    if not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > max_length:
        raise ValueError(f"{field} is too long")
    if any(char in cleaned for char in ["\x00", "\r"]):
        raise ValueError(f"{field} contains invalid characters")
    if "<" in cleaned or ">" in cleaned:
        raise ValueError(f"{field} cannot contain HTML")
    return cleaned


def _validate_targets(values: list[str]) -> list[str]:
    if not isinstance(values, list) or not values:
        raise ValueError("take_profit_targets must contain at least one target")
    if len(values) > 5:
        raise ValueError("take_profit_targets contains too many targets")
    return [_clean_text(value, "take_profit_target", max_length=255) for value in values]


def _validate_plan_ids(db: Session, plan_ids: list[str]) -> list[SubscriptionPlan]:
    if not plan_ids:
        raise ValueError("at least one plan target is required")
    unique_ids = []
    for plan_id in plan_ids:
        cleaned = _clean_text(plan_id, "plan_id", max_length=100)
        if cleaned not in unique_ids:
            unique_ids.append(cleaned)
    plans = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.id.in_(unique_ids))
        .order_by(SubscriptionPlan.id.asc())
        .all()
    )
    if {plan.id for plan in plans} != set(unique_ids):
        raise ValueError("one or more target plans do not exist")
    return plans


def _active_configured_plan_by_code(db: Session, plan_code: str) -> SubscriptionPlan:
    cleaned = _clean_text(plan_code, "plan_code", max_length=100)
    plan = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.code == cleaned)
        .with_for_update()
        .first()
    )
    if (
        plan is None
        or not plan.is_active
        or not plan.is_configured
        or plan.archived_at is not None
    ):
        raise ValueError("Configured test signal plan is unavailable")
    return plan


def _eligible_mapping_rows(db: Session, *, target: SubscriberSignalPlanTarget):
    return (
        db.query(PlanChannelMapping, TelegramChannel, SubscriptionPlan)
        .join(TelegramChannel, TelegramChannel.id == PlanChannelMapping.channel_id)
        .join(SubscriptionPlan, SubscriptionPlan.id == PlanChannelMapping.plan_id)
        .filter(
            PlanChannelMapping.plan_id == target.plan_id,
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


def _operational_test_identity(*, plan_code: str, test_id: str) -> str:
    payload = f"operational-test-signal|{plan_code}|{test_id}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"operational-test-signal:{digest}"


def _assert_operational_test_signal_matches(
    signal: SubscriberSignal,
    *,
    fields: dict[str, Any],
) -> None:
    if (
        signal.status != SubscriberSignalStatus.approved
        or signal.symbol != fields["symbol"]
        or signal.direction != fields["direction"]
        or signal.entry != fields["entry"]
        or signal.stop_loss != fields["stop_loss"]
        or signal.take_profit_targets != fields["take_profit_targets"]
        or signal.analysis != fields["analysis"]
    ):
        raise ValueError("Conflicting operational test signal already exists")


def create_operational_test_signal(
    db: Session,
    *,
    plan_code: str,
    test_id: str,
    dry_run: bool,
    now: datetime,
) -> OperationalTestSignalResult:
    """Create a system-approved operational delivery test signal.

    This is an internal/testing path. It does not require or create a legacy
    user, and it never calls the private-channel provider directly.
    """

    now = _aware_utc(now, "now")
    plan = _active_configured_plan_by_code(db, plan_code)
    cleaned_test_id = _clean_text(test_id, "test_id", max_length=100)
    identity = _operational_test_identity(plan_code=plan.code, test_id=cleaned_test_id)
    fields = {
        "symbol": "TEST",
        "direction": SubscriberSignalDirection.buy,
        "entry": "Test signal — do not trade",
        "stop_loss": "Not applicable",
        "take_profit_targets": ["Not applicable"],
        "analysis": "Operational delivery test only. Do not trade.",
    }

    existing = (
        db.query(SubscriberSignal)
        .filter(SubscriberSignal.strategy_identity == identity)
        .with_for_update()
        .first()
    )
    if existing is not None:
        _assert_operational_test_signal_matches(existing, fields=fields)
        publications = 0 if dry_run else enqueue_publications_for_signal(db, signal=existing, now=now)
        if dry_run:
            db.rollback()
        else:
            db.commit()
        return OperationalTestSignalResult(
            signal_id=existing.id,
            status=existing.status.value,
            created=False,
            dry_run=dry_run,
            publications_enqueued=publications,
            would_enqueue_publications=0,
        )

    target_preview = SubscriberSignalPlanTarget(signal_id="", plan_id=plan.id, created_at=now)
    would_enqueue = len(_eligible_mapping_rows(db, target=target_preview))
    if dry_run:
        db.rollback()
        return OperationalTestSignalResult(
            signal_id=None,
            status="dry_run",
            created=False,
            dry_run=True,
            publications_enqueued=0,
            would_enqueue_publications=would_enqueue,
        )

    signal = SubscriberSignal(
        status=SubscriberSignalStatus.approved,
        symbol=fields["symbol"],
        direction=fields["direction"],
        entry=fields["entry"],
        stop_loss=fields["stop_loss"],
        take_profit_targets=fields["take_profit_targets"],
        analysis=fields["analysis"],
        approved_at=now,
        strategy_identifier="operational-test-signal",
        strategy_version="test-cli-v1",
        strategy_ratio_identifier="TEST",
        strategy_decision_date=now.date().isoformat(),
        strategy_decision_type="OPERATIONAL_DELIVERY_TEST",
        strategy_identity=identity,
        created_at=now,
        updated_at=now,
    )
    try:
        db.add(signal)
        db.flush()
    except IntegrityError:
        db.rollback()
        recovered = (
            db.query(SubscriberSignal)
            .filter(SubscriberSignal.strategy_identity == identity)
            .with_for_update()
            .first()
        )
        if recovered is None:
            raise
        _assert_operational_test_signal_matches(recovered, fields=fields)
        publications = enqueue_publications_for_signal(db, signal=recovered, now=now)
        db.commit()
        return OperationalTestSignalResult(
            signal_id=recovered.id,
            status=recovered.status.value,
            created=False,
            dry_run=False,
            publications_enqueued=publications,
            would_enqueue_publications=0,
        )

    db.add(SubscriberSignalPlanTarget(signal_id=signal.id, plan_id=plan.id, created_at=now))
    db.flush()
    publications = enqueue_publications_for_signal(db, signal=signal, now=now)
    _audit(
        db,
        action="operational_test_signal_created",
        entity_type="subscriber_signal",
        entity_id=signal.id,
        reason="Internal operational test signal created for private-channel delivery validation",
        now=now,
        metadata={
            "plan_code": plan.code,
            "test_id": cleaned_test_id,
            "publications_enqueued": publications,
        },
    )
    db.commit()
    return OperationalTestSignalResult(
        signal_id=signal.id,
        status=signal.status.value,
        created=True,
        dry_run=False,
        publications_enqueued=publications,
        would_enqueue_publications=would_enqueue,
    )


def create_signal_draft(
    db: Session,
    *,
    admin_user_id: str,
    symbol: str,
    direction: SubscriberSignalDirection,
    entry: str,
    stop_loss: str,
    take_profit_targets: list[str],
    analysis: str | None,
    expires_at: datetime | None,
    plan_ids: list[str],
    now: datetime,
) -> SubscriberSignal:
    now = _aware_utc(now, "now")
    expires_at = _aware_utc(expires_at, "expires_at") if expires_at else None
    if expires_at is not None and expires_at <= now:
        raise ValueError("expires_at must be in the future")
    plans = _validate_plan_ids(db, plan_ids)
    signal = SubscriberSignal(
        status=SubscriberSignalStatus.draft,
        symbol=_clean_text(symbol, "symbol", max_length=100).upper(),
        direction=direction,
        entry=_clean_text(entry, "entry"),
        stop_loss=_clean_text(stop_loss, "stop_loss"),
        take_profit_targets=_validate_targets(take_profit_targets),
        analysis=_clean_text(analysis, "analysis", max_length=2000) if analysis else None,
        expires_at=expires_at,
        created_by_admin_user_id=admin_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(signal)
    db.flush()
    for plan in plans:
        db.add(
            SubscriberSignalPlanTarget(
                signal_id=signal.id,
                plan_id=plan.id,
                created_at=now,
            )
        )
    _audit(
        db,
        action="subscriber_signal_draft_created",
        entity_type="subscriber_signal",
        entity_id=signal.id,
        reason="Administrator created subscriber signal draft",
        now=now,
        actor_admin_user_id=admin_user_id,
        metadata={"target_plan_count": len(plans)},
    )
    db.commit()
    return signal


def update_signal_draft(
    db: Session,
    *,
    signal_id: str,
    admin_user_id: str,
    updates: dict[str, Any],
    now: datetime,
) -> SubscriberSignal:
    now = _aware_utc(now, "now")
    signal = db.query(SubscriberSignal).filter_by(id=signal_id).with_for_update().first()
    if signal is None:
        raise LookupError("Signal not found")
    if signal.status != SubscriberSignalStatus.draft:
        raise ValueError("Only draft signals can be updated")
    if "symbol" in updates:
        signal.symbol = _clean_text(updates["symbol"], "symbol", max_length=100).upper()
    if "direction" in updates:
        signal.direction = updates["direction"]
    if "entry" in updates:
        signal.entry = _clean_text(updates["entry"], "entry")
    if "stop_loss" in updates:
        signal.stop_loss = _clean_text(updates["stop_loss"], "stop_loss")
    if "take_profit_targets" in updates:
        signal.take_profit_targets = _validate_targets(updates["take_profit_targets"])
    if "analysis" in updates:
        analysis = updates["analysis"]
        signal.analysis = _clean_text(analysis, "analysis", max_length=2000) if analysis else None
    if "expires_at" in updates:
        expires_at = updates["expires_at"]
        signal.expires_at = _aware_utc(expires_at, "expires_at") if expires_at else None
        if signal.expires_at is not None and signal.expires_at <= now:
            raise ValueError("expires_at must be in the future")
    signal.updated_at = now
    _audit(
        db,
        action="subscriber_signal_draft_updated",
        entity_type="subscriber_signal",
        entity_id=signal.id,
        reason="Administrator updated subscriber signal draft",
        now=now,
        actor_admin_user_id=admin_user_id,
        metadata={"fields": sorted(updates.keys())},
    )
    db.commit()
    return signal


def _record_publication_configuration_gap(
    db: Session,
    *,
    signal: SubscriberSignal,
    target: SubscriberSignalPlanTarget,
    now: datetime,
) -> None:
    _audit(
        db,
        action="signal_publication_configuration_missing",
        entity_type="subscriber_signal",
        entity_id=signal.id,
        reason="No active configured private-channel mapping exists for signal target",
        now=now,
        metadata={"plan_id": target.plan_id},
    )


def enqueue_publications_for_signal(
    db: Session,
    *,
    signal: SubscriberSignal,
    now: datetime,
) -> int:
    now = _aware_utc(now, "now")
    if signal.status != SubscriberSignalStatus.approved:
        return 0
    created = 0
    targets = (
        db.query(SubscriberSignalPlanTarget)
        .filter(SubscriberSignalPlanTarget.signal_id == signal.id)
        .order_by(SubscriberSignalPlanTarget.id.asc())
        .all()
    )
    for target in targets:
        rows = _eligible_mapping_rows(db, target=target)
        if not rows:
            _record_publication_configuration_gap(db, signal=signal, target=target, now=now)
            continue
        for mapping, channel, plan in rows:
            existing = (
                db.query(SubscriberSignalPublication)
                .filter(
                    SubscriberSignalPublication.subscriber_signal_id == signal.id,
                    SubscriberSignalPublication.plan_channel_mapping_id == mapping.id,
                )
                .with_for_update()
                .first()
            )
            if existing is not None:
                if existing.status == SignalPublicationStatus.cancelled:
                    existing.status = SignalPublicationStatus.pending
                    existing.next_attempt_at = now
                    existing.failed_at = None
                    existing.last_error_code = None
                    existing.processing_started_at = None
                    existing.processing_claim_id = None
                    existing.updated_at = now
                continue
            publication = SubscriberSignalPublication(
                subscriber_signal_id=signal.id,
                signal_plan_target_id=target.id,
                plan_channel_mapping_id=mapping.id,
                subscription_plan_id=plan.id,
                telegram_channel_id=channel.id,
                status=SignalPublicationStatus.pending,
                attempt_count=0,
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
            try:
                with db.begin_nested():
                    db.add(publication)
                    db.flush()
                created += 1
                _audit(
                    db,
                    action="signal_publication_enqueued",
                    entity_type="subscriber_signal_publication",
                    entity_id=publication.id,
                    reason="Approved signal queued for private-channel publication",
                    now=now,
                    metadata={"signal_id": signal.id, "plan_code": plan.code},
                )
            except IntegrityError:
                continue
    return created


def approve_signal(
    db: Session,
    *,
    signal_id: str,
    admin_user_id: str,
    now: datetime,
) -> SubscriberSignal:
    now = _aware_utc(now, "now")
    signal = db.query(SubscriberSignal).filter_by(id=signal_id).with_for_update().first()
    if signal is None:
        raise LookupError("Signal not found")
    if signal.status == SubscriberSignalStatus.cancelled:
        raise ValueError("Cancelled signals cannot be approved")
    if signal.status == SubscriberSignalStatus.approved:
        enqueue_publications_for_signal(db, signal=signal, now=now)
        db.commit()
        return signal
    signal.status = SubscriberSignalStatus.approved
    signal.approved_at = now
    signal.approved_by_admin_user_id = admin_user_id
    signal.updated_at = now
    enqueue_publications_for_signal(db, signal=signal, now=now)
    _audit(
        db,
        action="subscriber_signal_approved",
        entity_type="subscriber_signal",
        entity_id=signal.id,
        reason="Administrator approved subscriber signal",
        now=now,
        actor_admin_user_id=admin_user_id,
    )
    db.commit()
    return signal


def cancel_signal(
    db: Session,
    *,
    signal_id: str,
    admin_user_id: str,
    now: datetime,
) -> SubscriberSignal:
    now = _aware_utc(now, "now")
    signal = db.query(SubscriberSignal).filter_by(id=signal_id).with_for_update().first()
    if signal is None:
        raise LookupError("Signal not found")
    if signal.status == SubscriberSignalStatus.cancelled:
        return signal
    signal.status = SubscriberSignalStatus.cancelled
    signal.cancelled_at = now
    signal.cancelled_by_admin_user_id = admin_user_id
    signal.updated_at = now
    updated = (
        db.query(SubscriberSignalPublication)
        .filter(
            SubscriberSignalPublication.subscriber_signal_id == signal.id,
            SubscriberSignalPublication.status.in_(
                [
                    SignalPublicationStatus.pending,
                    SignalPublicationStatus.retryable_failure,
                    SignalPublicationStatus.processing,
                ]
            ),
        )
        .update(
            {
                SubscriberSignalPublication.status: SignalPublicationStatus.cancelled,
                SubscriberSignalPublication.failed_at: now,
                SubscriberSignalPublication.last_error_code: "signal_cancelled",
                SubscriberSignalPublication.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    _audit(
        db,
        action="subscriber_signal_cancelled",
        entity_type="subscriber_signal",
        entity_id=signal.id,
        reason="Administrator cancelled subscriber signal",
        now=now,
        actor_admin_user_id=admin_user_id,
        metadata={"cancelled_publications": updated},
    )
    db.commit()
    return signal


def render_signal_message(signal: SubscriberSignal) -> str:
    """Render a customer-facing bilingual signal without exposing strategy internals."""
    metal_names = {
        "GOLD": ("GOLD", "OR", "🟡"),
        "SILVER": ("SILVER", "ARGENT", "⚪"),
        "PLATINUM": ("PLATINUM", "PLATINE", "⚪"),
        "PALLADIUM": ("PALLADIUM", "PALLADIUM", "⚪"),
    }
    ratio_pairs = {
        "AU_AG": ("GOLD", "SILVER"),
        "AU_PT": ("GOLD", "PLATINUM"),
        "AU_PD": ("GOLD", "PALLADIUM"),
    }

    raw_symbol = (signal.symbol or "").strip().upper()
    ratio_code, _, target_code = raw_symbol.partition(":")
    pair = ratio_pairs.get(ratio_code)

    if target_code in metal_names and pair and target_code in pair:
        source_code = pair[0] if pair[1] == target_code else pair[1]
        target_en, target_fr, target_icon = metal_names[target_code]
        source_en, source_fr, source_icon = metal_names[source_code]
        transition_en = f"{source_icon} {source_en} → {target_icon} {target_en}"
        transition_fr = f"{source_icon} {source_fr} → {target_icon} {target_fr}"
    elif target_code in metal_names:
        target_en, target_fr, target_icon = metal_names[target_code]
        transition_en = f"{target_icon} {target_en}"
        transition_fr = f"{target_icon} {target_fr}"
    else:
        target_en = "PRECIOUS METAL"
        target_fr = "MÉTAL PRÉCIEUX"
        transition_en = target_en
        transition_fr = target_fr

    if signal.direction == SubscriberSignalDirection.sell:
        action_en = f"SELL {target_en}"
        action_fr = f"VENDRE {target_fr}"
    else:
        action_en = f"BUY {target_en}"
        action_fr = f"ACHETER {target_fr}"

    signal_date = (signal.strategy_decision_date or "").strip()
    if signal_date:
        try:
            parsed_date = datetime.strptime(signal_date, "%Y-%m-%d")
            date_en = parsed_date.strftime("%d/%m/%Y")
            date_fr = date_en
        except ValueError:
            date_en = html.escape(signal_date)
            date_fr = date_en
    else:
        event_time = signal.approved_at or signal.created_at
        date_en = event_time.astimezone(timezone.utc).strftime("%d/%m/%Y")
        date_fr = date_en

    return (
        "🔔 AuroRatio Signal\n\n"
        f"{transition_en}\n\n"
        f"Action: {action_en}\n"
        f"Date: {date_en}\n\n"
        "This signal is informational. You remain responsible for reviewing it "
        "and making your own investment decisions.\n\n"
        "────────────\n\n"
        "🔔 Signal AuroRatio\n\n"
        f"{transition_fr}\n\n"
        f"Action : {action_fr}\n"
        f"Date : {date_fr}\n\n"
        "Ce signal est fourni à titre informatif. Vous restez responsable de son "
        "évaluation et de vos propres décisions d’investissement."
    )


def _publication_still_eligible(
    publication: SubscriberSignalPublication,
    *,
    now: datetime,
) -> bool:
    signal = publication.signal
    mapping = publication.plan_channel_mapping
    plan = publication.plan
    channel = publication.channel
    return bool(
        signal
        and signal.status == SubscriberSignalStatus.approved
        and (signal.expires_at is None or signal.expires_at > now)
        and mapping
        and mapping.is_active
        and plan
        and plan.is_active
        and plan.is_configured
        and plan.archived_at is None
        and channel
        and channel.is_active
        and channel.is_configured
        and channel.archived_at is None
        and channel.telegram_chat_id is not None
    )


def _claim_one_due_publication(db: Session, *, now: datetime) -> tuple[str, str] | None:
    stale_before = now - timedelta(seconds=publication_claim_lease_seconds())
    claim_id = uuid.uuid4().hex
    candidate = (
        db.query(SubscriberSignalPublication)
        .filter(
            (
                SubscriberSignalPublication.status.in_(list(CLAIMABLE_PUBLICATION_STATUSES))
                & (
                    (SubscriberSignalPublication.next_attempt_at.is_(None))
                    | (SubscriberSignalPublication.next_attempt_at <= now)
                )
            )
            | (
                (SubscriberSignalPublication.status == SignalPublicationStatus.processing)
                & (SubscriberSignalPublication.processing_started_at < stale_before)
            )
        )
        .order_by(
            SubscriberSignalPublication.next_attempt_at.asc().nullsfirst(),
            SubscriberSignalPublication.created_at.asc(),
            SubscriberSignalPublication.id.asc(),
        )
        .first()
    )
    if candidate is None:
        return None
    current_status = candidate.status
    previous_claim_id = candidate.processing_claim_id
    next_attempt_number = candidate.attempt_count + 1
    claimed = (
        db.query(SubscriberSignalPublication)
        .filter(
            SubscriberSignalPublication.id == candidate.id,
            SubscriberSignalPublication.status == current_status,
            (
                SubscriberSignalPublication.status.in_(list(CLAIMABLE_PUBLICATION_STATUSES))
                | (
                    (SubscriberSignalPublication.status == SignalPublicationStatus.processing)
                    & (SubscriberSignalPublication.processing_started_at < stale_before)
                )
            ),
        )
        .update(
            {
                SubscriberSignalPublication.status: SignalPublicationStatus.processing,
                SubscriberSignalPublication.processing_started_at: now,
                SubscriberSignalPublication.processing_claim_id: claim_id,
                SubscriberSignalPublication.attempt_count: SubscriberSignalPublication.attempt_count + 1,
                SubscriberSignalPublication.last_attempt_at: now,
                SubscriberSignalPublication.last_error_code: None,
                SubscriberSignalPublication.last_error_message: None,
                SubscriberSignalPublication.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    if claimed != 1:
        db.rollback()
        return None
    if current_status == SignalPublicationStatus.processing and previous_claim_id:
        stale_attempt = (
            db.query(SubscriberSignalDeliveryAttempt)
            .filter(
                SubscriberSignalDeliveryAttempt.signal_publication_id == candidate.id,
                SubscriberSignalDeliveryAttempt.processing_claim_id == previous_claim_id,
                SubscriberSignalDeliveryAttempt.outcome == SignalDeliveryAttemptOutcome.processing,
            )
            .with_for_update()
            .first()
        )
        if stale_attempt is not None:
            stale_attempt.outcome = SignalDeliveryAttemptOutcome.abandoned
            stale_attempt.completed_at = now
            stale_attempt.error_code = "processing_lease_expired"
            stale_attempt.error_message = "Processing lease expired before completion"
            stale_attempt.is_retryable = True
    db.add(
        SubscriberSignalDeliveryAttempt(
            signal_publication_id=candidate.id,
            attempt_number=next_attempt_number,
            processing_claim_id=claim_id,
            outcome=SignalDeliveryAttemptOutcome.processing,
            started_at=now,
            created_at=now,
        )
    )
    _audit(
        db,
        action="signal_publication_claimed",
        entity_type="subscriber_signal_publication",
        entity_id=candidate.id,
        reason="Signal publication claimed for processing",
        now=now,
    )
    db.commit()
    return candidate.id, claim_id


def _current_publication_context(
    db: Session,
    *,
    publication_id: str,
    claim_id: str | None = None,
) -> SubscriberSignalPublication | None:
    query = db.query(SubscriberSignalPublication).filter(
        SubscriberSignalPublication.id == publication_id
    )
    if claim_id is not None:
        query = query.filter(SubscriberSignalPublication.processing_claim_id == claim_id)
    return query.with_for_update().first()



def _current_delivery_attempt(
    db: Session,
    *,
    publication_id: str,
    claim_id: str,
) -> SubscriberSignalDeliveryAttempt | None:
    return (
        db.query(SubscriberSignalDeliveryAttempt)
        .filter(
            SubscriberSignalDeliveryAttempt.signal_publication_id == publication_id,
            SubscriberSignalDeliveryAttempt.processing_claim_id == claim_id,
        )
        .with_for_update()
        .first()
    )


def _complete_delivery_attempt(
    db: Session,
    *,
    publication: SubscriberSignalPublication,
    claim_id: str,
    outcome: SignalDeliveryAttemptOutcome,
    now: datetime,
    telegram_chat_id: int | None = None,
    telegram_message_id: int | None = None,
    provider_message_reference: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    is_retryable: bool | None = None,
) -> None:
    attempt = _current_delivery_attempt(
        db, publication_id=publication.id, claim_id=claim_id
    )
    if attempt is None or attempt.outcome != SignalDeliveryAttemptOutcome.processing:
        return
    attempt.outcome = outcome
    attempt.completed_at = now
    attempt.telegram_chat_id = telegram_chat_id
    attempt.telegram_message_id = telegram_message_id
    attempt.provider_message_reference = provider_message_reference
    attempt.error_code = error_code[:100] if error_code else None
    attempt.error_message = error_message[:500] if error_message else None
    attempt.is_retryable = is_retryable


def _mark_publication_failure(
    db: Session,
    *,
    publication: SubscriberSignalPublication,
    claim_id: str,
    error_code: str,
    error_message: str,
    retryable: bool,
    now: datetime,
    retry_after_seconds: int | None = None,
) -> None:
    max_attempts = publication_max_attempts()
    if retryable and publication.attempt_count < max_attempts:
        delay = retry_after_seconds or publication_retry_delay_seconds()
        publication.status = SignalPublicationStatus.retryable_failure
        publication.next_attempt_at = now + timedelta(seconds=delay)
    else:
        publication.status = SignalPublicationStatus.terminal_failure
        publication.next_attempt_at = None
    publication.failed_at = now
    publication.last_error_code = error_code[:100]
    publication.last_error_message = error_message[:500]
    publication.processing_started_at = None
    publication.processing_claim_id = None
    publication.updated_at = now
    _complete_delivery_attempt(
        db,
        publication=publication,
        claim_id=claim_id,
        outcome=(
            SignalDeliveryAttemptOutcome.transient_failure
            if publication.status == SignalPublicationStatus.retryable_failure
            else SignalDeliveryAttemptOutcome.permanent_failure
        ),
        now=now,
        telegram_chat_id=publication.telegram_chat_id,
        error_code=publication.last_error_code,
        error_message=publication.last_error_message,
        is_retryable=publication.status == SignalPublicationStatus.retryable_failure,
    )
    _audit(
        db,
        action="signal_publication_failed",
        entity_type="subscriber_signal_publication",
        entity_id=publication.id,
        reason="Signal publication failed",
        now=now,
        metadata={
            "error_code": publication.last_error_code,
            "retryable": publication.status == SignalPublicationStatus.retryable_failure,
        },
    )


async def process_one_signal_publication(
    publication_id: str,
    *,
    claim_id: str,
    session_factory=SessionLocal,
    telegram_service: TelegramPrivateChannelService | None = None,
    now: datetime,
) -> SignalPublicationStatus:
    now = _aware_utc(now, "now")
    telegram_service = telegram_service or TelegramPrivateChannelService()
    db = session_factory()
    try:
        publication = _current_publication_context(
            db,
            publication_id=publication_id,
            claim_id=claim_id,
        )
        if publication is None:
            return SignalPublicationStatus.cancelled
        if publication.status != SignalPublicationStatus.processing:
            return publication.status
        if not _publication_still_eligible(publication, now=now):
            publication.status = SignalPublicationStatus.cancelled
            publication.failed_at = now
            publication.cancelled_at = now
            publication.last_error_code = "signal_or_channel_inactive"
            publication.last_error_message = "Signal or channel is no longer eligible"
            publication.processing_started_at = None
            publication.processing_claim_id = None
            publication.updated_at = now
            _complete_delivery_attempt(
                db,
                publication=publication,
                claim_id=claim_id,
                outcome=SignalDeliveryAttemptOutcome.abandoned,
                now=now,
                error_code=publication.last_error_code,
                error_message=publication.last_error_message,
                is_retryable=False,
            )
            _audit(
                db,
                action="signal_publication_cancelled",
                entity_type="subscriber_signal_publication",
                entity_id=publication.id,
                reason="Signal publication is no longer eligible before provider call",
                now=now,
            )
            db.commit()
            return publication.status
        chat_id = int(publication.channel.telegram_chat_id)
        publication.telegram_chat_id = chat_id
        attempt = _current_delivery_attempt(
            db, publication_id=publication.id, claim_id=claim_id
        )
        if attempt is not None:
            attempt.telegram_chat_id = chat_id
        message = render_signal_message(publication.signal)
        db.commit()
    finally:
        db.close()

    try:
        published = await telegram_service.publish_text_message(chat_id=chat_id, text=message)
    except TelegramPermanentError as exc:
        db = session_factory()
        try:
            publication = _current_publication_context(
                db,
                publication_id=publication_id,
                claim_id=claim_id,
            )
            if publication and publication.status == SignalPublicationStatus.processing:
                _mark_publication_failure(
                    db,
                    publication=publication,
                    claim_id=claim_id,
                    error_code=getattr(exc, "error_code", "telegram_permanent_error"),
                    error_message=sanitize_telegram_error(exc),
                    retryable=False,
                    now=now,
                )
                db.commit()
                return publication.status
        finally:
            db.close()
        return SignalPublicationStatus.terminal_failure
    except TelegramProviderError as exc:
        db = session_factory()
        try:
            publication = _current_publication_context(
                db,
                publication_id=publication_id,
                claim_id=claim_id,
            )
            if publication and publication.status == SignalPublicationStatus.processing:
                _mark_publication_failure(
                    db,
                    publication=publication,
                    claim_id=claim_id,
                    error_code=getattr(exc, "error_code", "telegram_provider_error"),
                    error_message=sanitize_telegram_error(exc),
                    retryable=True,
                    now=now,
                    retry_after_seconds=getattr(exc, "retry_after_seconds", None),
                )
                _audit(
                    db,
                    action="signal_publication_provider_failed",
                    entity_type="subscriber_signal_publication",
                    entity_id=publication.id,
                    reason="Provider signal publication failed",
                    now=now,
                    metadata={"error": sanitize_telegram_error(exc)},
                )
                db.commit()
                return publication.status
        finally:
            db.close()
        return SignalPublicationStatus.retryable_failure

    db = session_factory()
    try:
        publication = _current_publication_context(
            db,
            publication_id=publication_id,
            claim_id=claim_id,
        )
        if publication is None or publication.status != SignalPublicationStatus.processing:
            return SignalPublicationStatus.cancelled
        publication.status = SignalPublicationStatus.published
        publication.provider_message_reference = published.provider_reference
        publication.telegram_chat_id = chat_id
        publication.telegram_message_id = published.message_id
        publication.published_at = now
        publication.next_attempt_at = None
        publication.processing_started_at = None
        publication.processing_claim_id = None
        publication.last_error_code = None
        publication.last_error_message = None
        publication.updated_at = now
        _complete_delivery_attempt(
            db,
            publication=publication,
            claim_id=claim_id,
            outcome=SignalDeliveryAttemptOutcome.delivered,
            now=now,
            telegram_chat_id=chat_id,
            telegram_message_id=published.message_id,
            provider_message_reference=published.provider_reference,
            is_retryable=False,
        )
        _audit(
            db,
            action="signal_publication_published",
            entity_type="subscriber_signal_publication",
            entity_id=publication.id,
            reason="Signal message accepted by private-channel provider",
            now=now,
        )
        db.commit()
        return publication.status
    finally:
        db.close()


async def process_due_signal_publications(
    *,
    limit: int = SIGNAL_PUBLICATION_DEFAULT_LIMIT,
    session_factory=SessionLocal,
    telegram_service: TelegramPrivateChannelService | None = None,
    now: datetime,
) -> SignalPublicationProcessResult:
    now = _aware_utc(now, "now")
    if limit <= 0 or limit > SIGNAL_PUBLICATION_MAX_LIMIT:
        raise ValueError("Signal publication processing limit is outside the allowed range")
    counts = {
        "processed": 0,
        "published": 0,
        "retryable_failures": 0,
        "terminal_failures": 0,
        "cancelled": 0,
    }
    for _ in range(limit):
        db = session_factory()
        try:
            claim = _claim_one_due_publication(db, now=now)
        finally:
            db.close()
        if not claim:
            break
        publication_id, claim_id = claim
        status = await process_one_signal_publication(
            publication_id,
            claim_id=claim_id,
            session_factory=session_factory,
            telegram_service=telegram_service,
            now=now,
        )
        counts["processed"] += 1
        if status == SignalPublicationStatus.published:
            counts["published"] += 1
        elif status == SignalPublicationStatus.retryable_failure:
            counts["retryable_failures"] += 1
        elif status == SignalPublicationStatus.terminal_failure:
            counts["terminal_failures"] += 1
        elif status == SignalPublicationStatus.cancelled:
            counts["cancelled"] += 1
    return SignalPublicationProcessResult(**counts)


def retry_signal_publication(
    db: Session,
    *,
    publication_id: str,
    admin_user_id: str,
    now: datetime,
) -> SubscriberSignalPublication:
    now = _aware_utc(now, "now")
    publication = (
        db.query(SubscriberSignalPublication)
        .filter_by(id=publication_id)
        .with_for_update()
        .first()
    )
    if publication is None:
        raise LookupError("Publication not found")
    previous_status = publication.status
    previous_attempt_count = publication.attempt_count
    if publication.status == SignalPublicationStatus.processing:
        raise ValueError("Processing publications cannot be manually retried")
    if publication.status == SignalPublicationStatus.pending:
        raise ValueError("Pending publications are already scheduled for delivery")
    if publication.status == SignalPublicationStatus.published:
        _audit(
            db,
            action="signal_publication_manual_retry_ignored",
            entity_type="subscriber_signal_publication",
            entity_id=publication.id,
            reason="Administrator requested retry for an already published signal publication",
            now=now,
            metadata={
                "previous_status": previous_status.value,
                "attempt_count": previous_attempt_count,
            },
            actor_admin_user_id=admin_user_id,
        )
        db.commit()
        return publication
    if publication.signal and publication.signal.status == SubscriberSignalStatus.cancelled:
        raise ValueError("Cancelled signals cannot be retried")
    publication.status = SignalPublicationStatus.pending
    publication.next_attempt_at = now
    publication.processing_started_at = None
    publication.processing_claim_id = None
    publication.failed_at = None
    publication.cancelled_at = None
    publication.last_error_code = None
    publication.last_error_message = None
    publication.updated_at = now
    _audit(
        db,
        action="signal_publication_manual_retry_requested",
        entity_type="subscriber_signal_publication",
        entity_id=publication.id,
        reason="Administrator requested signal publication retry",
        now=now,
        metadata={
            "previous_status": previous_status.value,
            "attempt_count": previous_attempt_count,
            "next_attempt_at": now.isoformat(),
        },
        actor_admin_user_id=admin_user_id,
    )
    db.commit()
    return publication


def backfill_missing_signal_publications(
    db: Session,
    *,
    now: datetime,
    admin_user_id: str,
    signal_id: str | None = None,
    dry_run: bool = True,
    limit: int = SIGNAL_BACKFILL_DEFAULT_LIMIT,
    after_signal_id: str | None = None,
) -> dict:
    now = _aware_utc(now, "now")
    if limit <= 0 or limit > SIGNAL_BACKFILL_MAX_LIMIT:
        raise ValueError("Signal publication backfill limit is outside the allowed range")
    query = db.query(SubscriberSignal).filter(
        SubscriberSignal.status == SubscriberSignalStatus.approved
    )
    if signal_id:
        query = query.filter(SubscriberSignal.id == signal_id)
    elif after_signal_id:
        query = query.filter(SubscriberSignal.id > after_signal_id)
    query = query.order_by(SubscriberSignal.id.asc())
    signals = query.limit(limit + 1).all()
    batch = signals[:limit]
    next_cursor = batch[-1].id if len(signals) > limit and batch and not signal_id else None
    checked = 0
    would_create = 0
    created = 0
    for signal in batch:
        checked += 1
        missing = 0
        targets = (
            db.query(SubscriberSignalPlanTarget)
            .filter(SubscriberSignalPlanTarget.signal_id == signal.id)
            .order_by(SubscriberSignalPlanTarget.id.asc())
            .all()
        )
        for target in targets:
            for mapping, _channel, _plan in _eligible_mapping_rows(db, target=target):
                exists = (
                    db.query(SubscriberSignalPublication.id)
                    .filter(
                        SubscriberSignalPublication.subscriber_signal_id == signal.id,
                        SubscriberSignalPublication.plan_channel_mapping_id == mapping.id,
                    )
                    .first()
                )
                if exists is None:
                    missing += 1
        would_create += missing
        if missing and not dry_run:
            created += enqueue_publications_for_signal(db, signal=signal, now=now)
    if not dry_run:
        _audit(
            db,
            action="signal_publication_backfill_requested",
            entity_type="subscriber_signal_publication",
            entity_id=signal_id or "batch",
            reason="Administrator backfilled missing signal publications",
            now=now,
            metadata={
                "checked": checked,
                "would_create": would_create,
                "created": created,
                "limit": limit,
                "has_more": next_cursor is not None,
            },
            actor_admin_user_id=admin_user_id,
        )
        db.commit()
    return {
        "checked": checked,
        "would_create": would_create,
        "created": created,
        "limit": limit,
        "next_cursor": next_cursor,
    }


def record_manual_signal_processing_requested(
    db: Session,
    *,
    admin_user_id: str,
    limit: int,
    now: datetime,
) -> None:
    now = _aware_utc(now, "now")
    _audit(
        db,
        action="signal_publication_due_processing_requested",
        entity_type="subscriber_signal_publication",
        entity_id="due",
        reason="Administrator requested due signal publication processing",
        now=now,
        metadata={"limit": limit},
        actor_admin_user_id=admin_user_id,
    )
    db.commit()
