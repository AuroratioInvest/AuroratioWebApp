"""
services/module_state_service.py

Per-user/per-module bot state for website execution.

Important:
IBKR sees merged real positions.
AuroRatio must track virtual module positions separately:
- M1 = AU/AG module
- M2 = AU/PT module
- M3 = AU/PD module
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import ModuleStatus, UserBotState, UserModulePosition

MODULES = ("M1", "M2", "M3")

MODULE_ALIASES = {
    "module1": "M1",
    "module_1": "M1",
    "MODULE1": "M1",
    "MODULE_1": "M1",
    "AU_AG": "M1",
    "M1": "M1",
    "module2": "M2",
    "module_2": "M2",
    "MODULE2": "M2",
    "MODULE_2": "M2",
    "AU_PT": "M2",
    "M2": "M2",
    "module3": "M3",
    "module_3": "M3",
    "MODULE3": "M3",
    "MODULE_3": "M3",
    "AU_PD": "M3",
    "M3": "M3",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_module(module_name: str) -> str:
    normalized = module_name.strip()
    resolved = MODULE_ALIASES.get(normalized) or MODULE_ALIASES.get(normalized.upper())

    if not resolved:
        raise ValueError(f"Unknown module: {module_name}")

    return resolved


def get_or_create_user_bot_state(db: Session, user_id: str) -> UserBotState:
    state = db.query(UserBotState).filter(UserBotState.user_id == user_id).first()
    if state:
        return state

    # Trading must be disabled by default.
    # It should only be enabled after:
    # - subscription active,
    # - FA authorization active,
    # - IBKR sub-account mapping verified,
    # - admin explicitly enables trading.
    state = UserBotState(
        user_id=user_id,
        trading_enabled=False,
        m1_enabled=True,
        m1_position="GOLD",
        m1_silver_days=0,
        m1_status=ModuleStatus.ok,
        m2_enabled=True,
        m2_position="GOLD",
        m2_platinum_days=0,
        m2_status=ModuleStatus.ok,
        m3_enabled=True,
        m3_position="GOLD",
        m3_palladium_days=0,
        m3_status=ModuleStatus.ok,
        last_updated=utc_now(),
    )
    db.add(state)
    db.flush()
    return state


def get_module_status(state: UserBotState, module_name: str) -> ModuleStatus:
    module = normalize_module(module_name)

    if module == "M1":
        return state.m1_status
    if module == "M2":
        return state.m2_status
    if module == "M3":
        return state.m3_status

    raise ValueError(f"Unknown module: {module_name}")


def set_module_status(
    state: UserBotState,
    module_name: str,
    status: ModuleStatus,
    error_message: str | None = None,
) -> None:
    module = normalize_module(module_name)
    now = utc_now()

    if module == "M1":
        state.m1_status = status
        state.m1_error_message = error_message
        state.m1_last_status_change = now
        if status != ModuleStatus.ok:
            state.m1_last_attempt_at = now

    elif module == "M2":
        state.m2_status = status
        state.m2_error_message = error_message
        state.m2_last_status_change = now
        if status != ModuleStatus.ok:
            state.m2_last_attempt_at = now

    elif module == "M3":
        state.m3_status = status
        state.m3_error_message = error_message
        state.m3_last_status_change = now
        if status != ModuleStatus.ok:
            state.m3_last_attempt_at = now

    else:
        raise ValueError(f"Unknown module: {module_name}")

    state.last_updated = now


def get_module_position(state: UserBotState, module_name: str) -> str:
    module = normalize_module(module_name)

    if module == "M1":
        return state.m1_position
    if module == "M2":
        return state.m2_position
    if module == "M3":
        return state.m3_position

    raise ValueError(f"Unknown module: {module_name}")


def set_module_position(state: UserBotState, module_name: str, metal: str) -> None:
    module = normalize_module(module_name)
    normalized_metal = metal.strip().upper()

    if module == "M1":
        state.m1_position = normalized_metal
        state.m1_last_trade_at = utc_now()
        state.m1_silver_days = 0

    elif module == "M2":
        state.m2_position = normalized_metal
        state.m2_last_trade_at = utc_now()
        state.m2_platinum_days = 0

    elif module == "M3":
        state.m3_position = normalized_metal
        state.m3_last_trade_at = utc_now()
        state.m3_palladium_days = 0

    else:
        raise ValueError(f"Unknown module: {module_name}")

    state.last_updated = utc_now()


def is_module_enabled(state: UserBotState, module_name: str) -> bool:
    module = normalize_module(module_name)

    if module == "M1":
        return bool(state.m1_enabled)
    if module == "M2":
        return bool(state.m2_enabled)
    if module == "M3":
        return bool(state.m3_enabled)

    raise ValueError(f"Unknown module: {module_name}")


def set_module_enabled(state: UserBotState, module_name: str, enabled: bool) -> None:
    module = normalize_module(module_name)

    if module == "M1":
        state.m1_enabled = enabled
    elif module == "M2":
        state.m2_enabled = enabled
    elif module == "M3":
        state.m3_enabled = enabled
    else:
        raise ValueError(f"Unknown module: {module_name}")

    state.last_updated = utc_now()


def increment_retry_count(state: UserBotState, module_name: str) -> int:
    module = normalize_module(module_name)

    if module == "M1":
        state.m1_retry_count = (state.m1_retry_count or 0) + 1
        return state.m1_retry_count

    if module == "M2":
        state.m2_retry_count = (state.m2_retry_count or 0) + 1
        return state.m2_retry_count

    if module == "M3":
        state.m3_retry_count = (state.m3_retry_count or 0) + 1
        return state.m3_retry_count

    raise ValueError(f"Unknown module: {module_name}")


def alert_already_sent(state: UserBotState, module_name: str) -> bool:
    module = normalize_module(module_name)

    if module == "M1":
        return state.m1_alert_sent_at is not None

    if module == "M2":
        return state.m2_alert_sent_at is not None

    if module == "M3":
        return state.m3_alert_sent_at is not None

    raise ValueError(f"Unknown module: {module_name}")


def mark_alert_sent(state: UserBotState, module_name: str) -> None:
    module = normalize_module(module_name)
    now = utc_now()

    if module == "M1":
        state.m1_alert_sent_at = now
    elif module == "M2":
        state.m2_alert_sent_at = now
    elif module == "M3":
        state.m3_alert_sent_at = now
    else:
        raise ValueError(f"Unknown module: {module_name}")

    state.last_updated = now


def reset_module_failure(state: UserBotState, module_name: str) -> None:
    module = normalize_module(module_name)
    now = utc_now()

    if module == "M1":
        state.m1_status = ModuleStatus.ok
        state.m1_error_message = None
        state.m1_retry_count = 0
        state.m1_alert_sent_at = None
        state.m1_last_attempt_at = None
        state.m1_last_status_change = now

    elif module == "M2":
        state.m2_status = ModuleStatus.ok
        state.m2_error_message = None
        state.m2_retry_count = 0
        state.m2_alert_sent_at = None
        state.m2_last_attempt_at = None
        state.m2_last_status_change = now

    elif module == "M3":
        state.m3_status = ModuleStatus.ok
        state.m3_error_message = None
        state.m3_retry_count = 0
        state.m3_alert_sent_at = None
        state.m3_last_attempt_at = None
        state.m3_last_status_change = now

    else:
        raise ValueError(f"Unknown module: {module_name}")

    state.last_updated = now


def get_or_create_module_position(
    db: Session,
    user_id: str,
    module_name: str,
) -> UserModulePosition:
    module = normalize_module(module_name)

    row = (
        db.query(UserModulePosition)
        .filter(UserModulePosition.user_id == user_id)
        .filter(UserModulePosition.module_name == module)
        .first()
    )
    if row:
        return row

    row = UserModulePosition(
        user_id=user_id,
        module_name=module,
        metal="GOLD",
        etf_symbol="SGLN",
        quantity=0.0,
        last_value_chf=0.0,
        is_enabled=True,
        updated_at=utc_now(),
    )
    db.add(row)
    db.flush()
    return row


def get_or_create_all_module_positions(
    db: Session,
    user_id: str,
) -> list[UserModulePosition]:
    return [
        get_or_create_module_position(db, user_id, "M1"),
        get_or_create_module_position(db, user_id, "M2"),
        get_or_create_module_position(db, user_id, "M3"),
    ]


def update_module_position(
    db: Session,
    *,
    user_id: str,
    module_name: str,
    metal: str,
    etf_symbol: str,
    quantity: float,
    value_chf: float | None = None,
    last_fill_price: float | None = None,
    last_sell_order_id: str | None = None,
    last_buy_order_id: str | None = None,
    last_execution_log_id: str | None = None,
) -> UserModulePosition:
    row = get_or_create_module_position(db, user_id, module_name)

    row.metal = metal.strip().upper()
    row.etf_symbol = etf_symbol.strip().upper()
    row.quantity = float(quantity)
    row.last_value_chf = float(value_chf or 0.0)

    if last_fill_price is not None:
        row.last_fill_price = float(last_fill_price)

    if last_sell_order_id is not None:
        row.last_sell_order_id = last_sell_order_id

    if last_buy_order_id is not None:
        row.last_buy_order_id = last_buy_order_id

    if last_execution_log_id is not None:
        row.last_execution_log_id = last_execution_log_id

    row.updated_at = utc_now()
    db.flush()
    return row