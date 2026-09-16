"""
services/user_bot_state_service.py

Per-user bot/module state helpers.

Why this file exists:
- The current BotState table is global. That is okay for a local MVP, but not for a
  multi-user production product.
- Every subscribed user needs their own module positions, hysteresis counters,
  failure state, retry count, and alert state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from models import UserBotState, ModuleStatus


MODULE_DEFAULTS = {
    "module1": {"position": "GOLD", "counter_name": "silver_days"},
    "module2": {"position": "GOLD", "counter_name": "platinum_days"},
    "module3": {"position": "GOLD", "counter_name": "palladium_days"},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_user_bot_state(db: Session, user_id: str) -> UserBotState:
    state = db.query(UserBotState).filter(UserBotState.user_id == user_id).first()

    if state:
        return state

    state = UserBotState(
        user_id=user_id,
        m1_position="GOLD",
        m1_silver_days=0,
        m1_status=ModuleStatus.ok,
        m2_position="GOLD",
        m2_platinum_days=0,
        m2_status=ModuleStatus.ok,
        m3_position="GOLD",
        m3_palladium_days=0,
        m3_status=ModuleStatus.ok,
        trading_enabled=True,
        last_updated=utc_now(),
    )

    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def get_module_position(state: UserBotState, module_name: str) -> str:
    if module_name == "module1":
        return state.m1_position
    if module_name == "module2":
        return state.m2_position
    if module_name == "module3":
        return state.m3_position
    raise ValueError(f"Unknown module: {module_name}")


def set_module_position(state: UserBotState, module_name: str, metal: str) -> None:
    if module_name == "module1":
        state.m1_position = metal
    elif module_name == "module2":
        state.m2_position = metal
    elif module_name == "module3":
        state.m3_position = metal
    else:
        raise ValueError(f"Unknown module: {module_name}")

    state.last_updated = utc_now()


def get_module_status(state: UserBotState, module_name: str) -> ModuleStatus:
    if module_name == "module1":
        return state.m1_status
    if module_name == "module2":
        return state.m2_status
    if module_name == "module3":
        return state.m3_status
    raise ValueError(f"Unknown module: {module_name}")


def set_module_status(
    state: UserBotState,
    module_name: str,
    status: ModuleStatus,
    error_message: str | None = None,
) -> None:
    now = utc_now()

    if module_name == "module1":
        state.m1_status = status
        state.m1_error_message = error_message
        state.m1_last_status_change = now
    elif module_name == "module2":
        state.m2_status = status
        state.m2_error_message = error_message
        state.m2_last_status_change = now
    elif module_name == "module3":
        state.m3_status = status
        state.m3_error_message = error_message
        state.m3_last_status_change = now
    else:
        raise ValueError(f"Unknown module: {module_name}")

    state.last_updated = now


def increment_module_retry(state: UserBotState, module_name: str) -> int:
    now = utc_now()

    if module_name == "module1":
        state.m1_retry_count = (state.m1_retry_count or 0) + 1
        state.m1_last_attempt_at = now
        return state.m1_retry_count
    if module_name == "module2":
        state.m2_retry_count = (state.m2_retry_count or 0) + 1
        state.m2_last_attempt_at = now
        return state.m2_retry_count
    if module_name == "module3":
        state.m3_retry_count = (state.m3_retry_count or 0) + 1
        state.m3_last_attempt_at = now
        return state.m3_retry_count

    raise ValueError(f"Unknown module: {module_name}")


def reset_module_failure(state: UserBotState, module_name: str) -> None:
    if module_name == "module1":
        state.m1_status = ModuleStatus.ok
        state.m1_error_message = None
        state.m1_retry_count = 0
        state.m1_alert_sent_at = None
    elif module_name == "module2":
        state.m2_status = ModuleStatus.ok
        state.m2_error_message = None
        state.m2_retry_count = 0
        state.m2_alert_sent_at = None
    elif module_name == "module3":
        state.m3_status = ModuleStatus.ok
        state.m3_error_message = None
        state.m3_retry_count = 0
        state.m3_alert_sent_at = None
    else:
        raise ValueError(f"Unknown module: {module_name}")

    state.last_updated = utc_now()


def mark_alert_sent(state: UserBotState, module_name: str) -> None:
    now = utc_now()

    if module_name == "module1":
        state.m1_alert_sent_at = now
    elif module_name == "module2":
        state.m2_alert_sent_at = now
    elif module_name == "module3":
        state.m3_alert_sent_at = now
    else:
        raise ValueError(f"Unknown module: {module_name}")

    state.last_updated = now


def alert_already_sent(state: UserBotState, module_name: str) -> bool:
    if module_name == "module1":
        return state.m1_alert_sent_at is not None
    if module_name == "module2":
        return state.m2_alert_sent_at is not None
    if module_name == "module3":
        return state.m3_alert_sent_at is not None
    raise ValueError(f"Unknown module: {module_name}")
