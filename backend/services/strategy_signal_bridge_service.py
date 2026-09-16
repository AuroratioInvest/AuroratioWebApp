"""Bridge trusted strategy decisions into subscriber signal publication."""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.subscriber_signal_publication_service import enqueue_publications_for_signal
from strategy_decisions import StrategyDecisionCandidate
from subscriber_models import (
    AuditActorType,
    AuditEvent,
    SubscriberSignal,
    SubscriberSignalDirection,
    SubscriberSignalPlanTarget,
    SubscriberSignalStatus,
    SubscriptionPlan,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategySignalIngestionResult:
    signal_id: str
    strategy_identity: str
    created: bool
    publications_enqueued: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _strategy_plan_codes() -> list[str]:
    raw = (
        os.getenv("SUBSCRIBER_SIGNAL_PLAN_CODES")
        or os.getenv("MONTHLY_SIGNAL_PLAN_CODE")
        or "monthly-signals"
    )
    codes = []
    for part in raw.split(","):
        code = part.strip()
        if code and code not in codes:
            codes.append(code)
    if not codes:
        raise ValueError("No subscriber signal plan codes configured")
    return codes


def _trusted_plans(db: Session) -> list[SubscriptionPlan]:
    codes = _strategy_plan_codes()
    plans = (
        db.query(SubscriptionPlan)
        .filter(
            SubscriptionPlan.code.in_(codes),
            SubscriptionPlan.is_active.is_(True),
            SubscriptionPlan.is_configured.is_(True),
            SubscriptionPlan.archived_at.is_(None),
        )
        .order_by(SubscriptionPlan.code.asc(), SubscriptionPlan.id.asc())
        .all()
    )
    if {plan.code for plan in plans} != set(codes):
        raise ValueError("Configured subscriber signal plan is unavailable")
    return plans


def strategy_identity(candidate: StrategyDecisionCandidate) -> str:
    payload = "|".join(candidate.identity_parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{candidate.strategy_identifier}:{digest}"


def _direction_for(candidate: StrategyDecisionCandidate) -> SubscriberSignalDirection:
    return (
        SubscriberSignalDirection.sell
        if candidate.to_metal == "GOLD"
        else SubscriberSignalDirection.buy
    )


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _canonical_fields(candidate: StrategyDecisionCandidate) -> dict:
    ratio_value = _format_decimal(candidate.ratio_value)
    symbol = f"{candidate.ratio_identifier}:{candidate.to_metal}"
    analysis = (
        f"Relative-value confirmation for {candidate.consecutive_days} consecutive "
        f"trading days. Strategy indicates rotating from {candidate.from_metal} "
        f"to {candidate.to_metal}. Latest {candidate.ratio_identifier} ratio: "
        f"{ratio_value}. This signal is informational and subscribers remain "
        "responsible for manual evaluation and execution."
    )
    return {
        "symbol": symbol,
        "direction": _direction_for(candidate),
        "entry": (
            f"Relative-value signal confirmed on {candidate.decision_date.isoformat()} "
            f"using {candidate.ratio_identifier} ratio {ratio_value}."
        ),
        "stop_loss": "Not supplied by strategy; subscriber manual risk controls required.",
        "take_profit_targets": [
            "Not supplied by strategy; subscriber manual target selection required."
        ],
        "analysis": analysis,
        "expires_at": None,
    }


def _audit(
    db: Session,
    *,
    action: str,
    entity_id: str,
    reason: str,
    now: datetime,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_type=AuditActorType.system,
            action=action,
            entity_type="subscriber_signal",
            entity_id=entity_id,
            reason=reason,
            event_metadata=metadata,
            created_at=now,
        )
    )


def _assert_existing_matches(
    existing: SubscriberSignal,
    *,
    identity: str,
    candidate: StrategyDecisionCandidate,
) -> None:
    fields = _canonical_fields(candidate)
    if (
        existing.strategy_identity != identity
        or existing.strategy_identifier != candidate.strategy_identifier
        or existing.strategy_version != candidate.strategy_version
        or existing.strategy_ratio_identifier != candidate.ratio_identifier
        or existing.strategy_decision_date != candidate.decision_date.isoformat()
        or existing.strategy_decision_type != candidate.decision_type
        or existing.symbol != fields["symbol"]
        or existing.direction != fields["direction"]
        or existing.entry != fields["entry"]
        or existing.stop_loss != fields["stop_loss"]
        or existing.take_profit_targets != fields["take_profit_targets"]
        or existing.analysis != fields["analysis"]
    ):
        raise ValueError("Conflicting strategy decision already exists")


def ingest_confirmed_strategy_decision(
    db: Session,
    *,
    candidate: StrategyDecisionCandidate,
    now: datetime | None = None,
) -> StrategySignalIngestionResult:
    """Persist, auto-approve, and enqueue one trusted confirmed strategy decision."""

    now = _aware_utc(now or utc_now(), "now")
    source_timestamp = _aware_utc(candidate.source_data_timestamp, "source_data_timestamp")
    identity = strategy_identity(candidate)
    try:
        existing = (
            db.query(SubscriberSignal)
            .filter(SubscriberSignal.strategy_identity == identity)
            .with_for_update()
            .first()
        )
        if existing is not None:
            _assert_existing_matches(existing, identity=identity, candidate=candidate)
            publications = enqueue_publications_for_signal(db, signal=existing, now=now)
            db.commit()
            return StrategySignalIngestionResult(
                signal_id=existing.id,
                strategy_identity=identity,
                created=False,
                publications_enqueued=publications,
            )

        plans = _trusted_plans(db)
        fields = _canonical_fields(candidate)
        signal = SubscriberSignal(
            status=SubscriberSignalStatus.approved,
            approved_at=now,
            symbol=fields["symbol"],
            direction=fields["direction"],
            entry=fields["entry"],
            stop_loss=fields["stop_loss"],
            take_profit_targets=fields["take_profit_targets"],
            analysis=fields["analysis"],
            expires_at=fields["expires_at"],
            strategy_identifier=candidate.strategy_identifier,
            strategy_version=candidate.strategy_version,
            strategy_ratio_identifier=candidate.ratio_identifier,
            strategy_decision_date=candidate.decision_date.isoformat(),
            strategy_decision_type=candidate.decision_type,
            strategy_identity=identity,
            created_at=now,
            updated_at=now,
        )
        try:
            db.add(signal)
            db.flush()
        except IntegrityError:
            logger.info("Strategy signal identity already exists during concurrent ingest")
            db.rollback()
            recovered = (
                db.query(SubscriberSignal)
                .filter(SubscriberSignal.strategy_identity == identity)
                .with_for_update()
                .first()
            )
            if recovered is None:
                raise
            _assert_existing_matches(recovered, identity=identity, candidate=candidate)
            publications = enqueue_publications_for_signal(db, signal=recovered, now=now)
            db.commit()
            return StrategySignalIngestionResult(
                signal_id=recovered.id,
                strategy_identity=identity,
                created=False,
                publications_enqueued=publications,
            )

        for plan in plans:
            db.add(
                SubscriberSignalPlanTarget(
                    signal_id=signal.id,
                    plan_id=plan.id,
                    created_at=now,
                )
            )
        db.flush()
        publications = enqueue_publications_for_signal(db, signal=signal, now=now)
        _audit(
            db,
            action="strategy_signal_auto_approved",
            entity_id=signal.id,
            reason="Trusted strategy decision auto-approved for subscriber publication",
            now=now,
            metadata={
                "strategy_identifier": candidate.strategy_identifier,
                "strategy_version": candidate.strategy_version,
                "ratio_identifier": candidate.ratio_identifier,
                "decision_date": candidate.decision_date.isoformat(),
                "decision_type": candidate.decision_type,
                "source_data_timestamp": source_timestamp.isoformat(),
                "target_plan_count": len(plans),
                "publications_enqueued": publications,
            },
        )
        db.commit()
        return StrategySignalIngestionResult(
            signal_id=signal.id,
            strategy_identity=identity,
            created=True,
            publications_enqueued=publications,
        )
    except Exception:
        db.rollback()
        raise
