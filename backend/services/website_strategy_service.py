from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import ModuleStatus, UserModulePosition
from services.ratio_service import get_latest_ratios
from services.module_state_service import (
    get_or_create_user_bot_state,
    get_module_position,
    get_module_status,
)

HYSTERESIS_DAYS = 2
COOLDOWN_DAYS = 2


MODULE_ALIASES = {
    "module1": "M1",
    "module2": "M2",
    "module3": "M3",
    "M1": "M1",
    "M2": "M2",
    "M3": "M3",
}


@dataclass
class ModuleSignal:
    module_name: str
    from_metal: str
    to_metal: str
    ratio_col: str
    ratio_value: float
    reason: str


BUY_RULES = {
    "M1": {
        "ratio_col": "AU_AG",
        "to_metal": "SILVER",
        "counter": "m1_silver_days",
        "threshold": 80.0,
        "enabled_field": "m1_enabled",
        "last_trade_field": "m1_last_trade_at",
    },
    "M2": {
        "ratio_col": "AU_PT",
        "to_metal": "PLATINUM",
        "counter": "m2_platinum_days",
        "threshold": 2.0,
        "enabled_field": "m2_enabled",
        "last_trade_field": "m2_last_trade_at",
    },
    "M3": {
        "ratio_col": "AU_PD",
        "to_metal": "PALLADIUM",
        "counter": "m3_palladium_days",
        "threshold": 4.0,
        "enabled_field": "m3_enabled",
        "last_trade_field": "m3_last_trade_at",
    },
}

SELL_RULES = {
    "M1": {
        "ratio_col": "AU_AG",
        "to_metal": "GOLD",
        "counter": "m1_silver_days",
        "threshold": 40.0,
        "enabled_field": "m1_enabled",
        "last_trade_field": "m1_last_trade_at",
    },
    "M2": {
        "ratio_col": "AU_PT",
        "to_metal": "GOLD",
        "counter": "m2_platinum_days",
        "threshold": 0.45,
        "enabled_field": "m2_enabled",
        "last_trade_field": "m2_last_trade_at",
    },
    "M3": {
        "ratio_col": "AU_PD",
        "to_metal": "GOLD",
        "counter": "m3_palladium_days",
        "threshold": 0.9,
        "enabled_field": "m3_enabled",
        "last_trade_field": "m3_last_trade_at",
    },
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_module(module_name: str) -> str:
    return MODULE_ALIASES.get(module_name, module_name).upper()


def in_cooldown(last_trade_at: datetime | None) -> bool:
    if not last_trade_at:
        return False

    if last_trade_at.tzinfo is None:
        last_trade_at = last_trade_at.replace(tzinfo=timezone.utc)

    return (utc_now() - last_trade_at).days < COOLDOWN_DAYS


def get_virtual_module_metal(
    db: Session,
    user_id: str,
    module_name: str,
    fallback_state_position: str,
) -> str:
    """
    The virtual ledger is the source of truth for FA execution.

    Fallback exists only for old users who may not yet have initialized
    UserModulePosition rows.
    """
    normalized_module = normalize_module(module_name)

    ledger_position = (
        db.query(UserModulePosition)
        .filter(
            UserModulePosition.user_id == user_id,
            UserModulePosition.module_name == normalized_module,
        )
        .first()
    )

    if ledger_position:
        return ledger_position.metal.upper()

    return fallback_state_position.upper()


def compute_user_signals(db: Session, user_id: str) -> list[ModuleSignal]:
    state = get_or_create_user_bot_state(db, user_id)
    ratios = get_latest_ratios()

    signals: list[ModuleSignal] = []

    if not state.trading_enabled:
        return signals

    # BUY logic: Gold -> secondary metal
    for module_name, rule in BUY_RULES.items():
        if not getattr(state, rule["enabled_field"], True):
            continue

        if get_module_status(state, module_name) != ModuleStatus.ok:
            continue

        state_position = get_module_position(state, module_name)
        position = get_virtual_module_metal(
            db=db,
            user_id=user_id,
            module_name=module_name,
            fallback_state_position=state_position,
        )

        if position != "GOLD":
            continue

        last_trade = getattr(state, rule["last_trade_field"], None)
        if in_cooldown(last_trade):
            continue

        ratio = float(ratios[rule["ratio_col"]])
        counter = int(getattr(state, rule["counter"]) or 0)

        if ratio >= rule["threshold"]:
            counter += 1
        else:
            counter = 0

        setattr(state, rule["counter"], counter)

        if counter == HYSTERESIS_DAYS:
            signals.append(
                ModuleSignal(
                    module_name=module_name,
                    from_metal="GOLD",
                    to_metal=rule["to_metal"],
                    ratio_col=rule["ratio_col"],
                    ratio_value=ratio,
                    reason=(
                        f"{rule['ratio_col']} >= {rule['threshold']} "
                        f"for {counter} days"
                    ),
                )
            )

    # SELL logic: secondary metal -> Gold
    for module_name, rule in SELL_RULES.items():
        if not getattr(state, rule["enabled_field"], True):
            continue

        if get_module_status(state, module_name) != ModuleStatus.ok:
            continue

        state_position = get_module_position(state, module_name)
        position = get_virtual_module_metal(
            db=db,
            user_id=user_id,
            module_name=module_name,
            fallback_state_position=state_position,
        )

        if position == "GOLD":
            continue

        last_trade = getattr(state, rule["last_trade_field"], None)
        if in_cooldown(last_trade):
            continue

        ratio = float(ratios[rule["ratio_col"]])
        counter = int(getattr(state, rule["counter"]) or 0)

        if ratio <= rule["threshold"]:
            counter += 1
        else:
            counter = 0

        setattr(state, rule["counter"], counter)

        if counter == HYSTERESIS_DAYS:
            signals.append(
                ModuleSignal(
                    module_name=module_name,
                    from_metal=position,
                    to_metal="GOLD",
                    ratio_col=rule["ratio_col"],
                    ratio_value=ratio,
                    reason=(
                        f"{rule['ratio_col']} <= {rule['threshold']} "
                        f"for {counter} days"
                    ),
                )
            )

    state.last_updated = utc_now()
    db.commit()

    return signals