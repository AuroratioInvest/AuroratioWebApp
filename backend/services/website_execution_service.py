"""
services/website_execution_service.py

Website execution engine for AuroRatio.

Architecture:
- SnapTrade = portfolio display / optional read-only sync
- IBKR FA = future production execution
- Virtual module ledger = mandatory accounting layer

IBKR sees merged real positions.
AuroRatio tracks module ownership internally:
    M1 = AU/AG = Gold/Silver module
    M2 = AU/PT = Gold/Platinum module
    M3 = AU/PD = Gold/Palladium module
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from models import (
    ExecutionLog,
    ExecutionStatus,
    ModuleStatus,
    Subscription,
    SubscriptionStatus,
    TradeLog,
    TradeStatus,
    TradingProvider,
    User,
)
from services.fa_execution_service import (
    FAModuleSwitchRequest,
    execute_module_switch,
)
from services.fa_service import is_user_eligible_for_fa_execution
from services.module_state_service import (
    alert_already_sent,
    get_or_create_all_module_positions,
    get_or_create_user_bot_state,
    increment_retry_count,
    mark_alert_sent,
    reset_module_failure,
    set_module_position,
    set_module_status,
)
from services.notification_service import send_admin_alert
from services.portfolio_service import sync_positions_from_snaptrade
from services.website_strategy_service import ModuleSignal, compute_user_signals

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def execution_mode() -> str:
    """
    Modes:
    - disabled: never execute
    - dry_run: full FA logic, logs only, no IBKR order
    - live: IBKR FA live execution, blocked unless AURORATIO_ALLOW_LIVE_TRADING=true
    """
    return os.getenv("AURORATIO_EXECUTION_MODE", "dry_run").strip().lower()


def can_place_orders() -> bool:
    return (
        execution_mode() == "live"
        and os.getenv("AURORATIO_ALLOW_LIVE_TRADING", "false").lower() == "true"
    )


def is_dry_run() -> bool:
    return not can_place_orders()


def get_active_trading_users(db: Session) -> list[User]:
    return (
        db.query(User)
        .join(Subscription, Subscription.user_id == User.id)
        .filter(User.is_active == True)
        .filter(User.trading_enabled == True)
        .filter(Subscription.status == SubscriptionStatus.active)
        .all()
    )


def mark_execution_failed(
    db: Session,
    log: ExecutionLog,
    reason: str,
    raw: Any | None = None,
) -> None:
    log.status = ExecutionStatus.failed
    log.error_message = reason
    log.raw_response = str(raw)[:5000] if raw is not None else None
    log.finished_at = utc_now()
    db.commit()


def mark_execution_success(
    db: Session,
    log: ExecutionLog,
    raw: Any | None = None,
) -> None:
    log.status = ExecutionStatus.success
    log.raw_response = str(raw)[:5000] if raw is not None else log.raw_response
    log.finished_at = log.finished_at or utc_now()
    db.commit()


def _fail_module_once(
    db: Session,
    *,
    user: User,
    signal: ModuleSignal,
    reason: str,
    log: ExecutionLog | None = None,
) -> None:
    state = get_or_create_user_bot_state(db, user.id)

    if log:
        mark_execution_failed(db, log, reason)

    retry_count = increment_retry_count(state, signal.module_name)
    set_module_status(state, signal.module_name, ModuleStatus.cash_manual_review, reason)

    db.add(
        TradeLog(
            user_id=user.id,
            provider=TradingProvider.ibkr_fa,
            module_name=signal.module_name,
            from_metal=signal.from_metal,
            to_metal=signal.to_metal,
            ratio_col=signal.ratio_col,
            ratio_value=signal.ratio_value,
            quantity=0,
            status=TradeStatus.failed,
            error_message=reason,
        )
    )

    if not alert_already_sent(state, signal.module_name):
        send_admin_alert(
            subject=f"AuroRatio — {signal.module_name} requires manual review",
            body=(
                f"User: {user.email} ({user.id})\n"
                f"Module: {signal.module_name}\n"
                f"Signal: {signal.from_metal} → {signal.to_metal}\n"
                f"Reason: {reason}\n"
                f"Retry count: {retry_count}\n\n"
                "The module is now CASH_MANUAL_REVIEW and will not trade again until reset."
            ),
        )
        mark_alert_sent(state, signal.module_name)

    db.commit()


def _sync_snaptrade_for_display_only(db: Session, user: User) -> None:
    if os.getenv("AURORATIO_SYNC_SNAPTRADE_BEFORE_EXECUTION", "false").lower() != "true":
        return

    try:
        from snaptrade_client import SnapTrade

        snaptrade = SnapTrade(
            consumer_key=os.getenv("SNAPTRADE_CONSUMER_KEY"),
            client_id=os.getenv("SNAPTRADE_CLIENT_ID"),
        )

        sync_positions_from_snaptrade(db, user.id, snaptrade)

    except Exception:
        logger.exception(
            "SnapTrade display sync failed for user=%s. Continuing FA execution.",
            user.id,
        )


def execute_signal_for_user(
    db: Session,
    *,
    user: User,
    signal: ModuleSignal,
) -> bool:
    if execution_mode() == "disabled":
        return True

    if execution_mode() == "live" and not can_place_orders():
        _fail_module_once(
            db,
            user=user,
            signal=signal,
            reason="Live execution blocked: AURORATIO_ALLOW_LIVE_TRADING is not true",
        )
        return False

    request = FAModuleSwitchRequest(
        user=user,
        module_name=signal.module_name,
        from_metal=signal.from_metal,
        to_metal=signal.to_metal,
        ratio_col=signal.ratio_col,
        ratio_value=signal.ratio_value,
        dry_run=is_dry_run(),
    )

    result = execute_module_switch(db, request)
    log = result.execution_log

    if result.skipped:
        return True

    if log.status == ExecutionStatus.success:
        state = get_or_create_user_bot_state(db, user.id)

        set_module_position(state, signal.module_name, signal.to_metal)
        reset_module_failure(state, signal.module_name)

        db.add(
            TradeLog(
                user_id=user.id,
                provider=TradingProvider.ibkr_fa,
                module_name=signal.module_name,
                from_metal=signal.from_metal,
                to_metal=signal.to_metal,
                ratio_col=signal.ratio_col,
                ratio_value=signal.ratio_value,
                quantity=log.to_quantity or log.units or 0,
                sell_order_id=log.sell_order_id,
                buy_order_id=log.buy_order_id,
                status=TradeStatus.success,
                raw_response=log.raw_response,
            )
        )

        db.commit()
        return True

    _fail_module_once(
        db,
        user=user,
        signal=signal,
        reason=log.error_message or result.message,
        log=log,
    )
    return False


def run_website_execution(db: Session, *, user_id: str | None = None) -> dict:
    users_query = get_active_trading_users(db)
    users = [user for user in users_query if user_id is None or user.id == user_id]

    summary = {
        "mode": execution_mode(),
        "dry_run": is_dry_run(),
        "provider": "ibkr_fa",
        "users_checked": len(users),
        "signals": 0,
        "executed": 0,
        "failed": 0,
        "skipped": 0,
        "started_at": utc_now().isoformat(),
    }

    for user in users:
        try:
            state = get_or_create_user_bot_state(db, user.id)
            get_or_create_all_module_positions(db, user.id)
            db.commit()

            if not state.trading_enabled:
                summary["skipped"] += 1
                continue

            if not is_user_eligible_for_fa_execution(db, user):
                summary["skipped"] += 1
                continue

            _sync_snaptrade_for_display_only(db, user)

            signals = compute_user_signals(db, user.id)
            summary["signals"] += len(signals)

            for signal in signals:
                ok = execute_signal_for_user(
                    db=db,
                    user=user,
                    signal=signal,
                )

                if ok:
                    summary["executed"] += 1
                else:
                    summary["failed"] += 1

        except Exception:
            db.rollback()
            logger.exception("Execution loop failed for user=%s", user.id)
            summary["failed"] += 1

    summary["finished_at"] = utc_now().isoformat()
    return summary