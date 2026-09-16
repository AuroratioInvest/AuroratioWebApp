"""
state.py — Bot State Management
=================================
Manages the three independent module states in state.json.
Each module tracks one metal pair independently.

Production strategy values come from config.yaml.

Optional environment-variable overrides are supported only when
AURORATIO_ENABLE_STRATEGY_TEST_OVERRIDES=true. This allows controlled Railway
tests without committing fake strategy thresholds to config.yaml.
"""

import copy
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")

DEFAULT_STATE = {
    "module1": {"position": "GOLD", "silver_days": 0, "history": []},
    "module2": {"position": "GOLD", "platinum_days": 0, "history": []},
    "module3": {"position": "GOLD", "palladium_days": 0, "history": []},
}

_TEST_OVERRIDE_FLAG = "AURORATIO_ENABLE_STRATEGY_TEST_OVERRIDES"

_TEST_RATIO_ENV = {
    ("silver", "buy"): "AURORATIO_TEST_SILVER_BUY_RATIO",
    ("silver", "sell"): "AURORATIO_TEST_SILVER_SELL_RATIO",
    ("platinum", "buy"): "AURORATIO_TEST_PLATINUM_BUY_RATIO",
    ("platinum", "sell"): "AURORATIO_TEST_PLATINUM_SELL_RATIO",
    ("palladium", "buy"): "AURORATIO_TEST_PALLADIUM_BUY_RATIO",
    ("palladium", "sell"): "AURORATIO_TEST_PALLADIUM_SELL_RATIO",
}


def _test_overrides_enabled() -> bool:
    return os.getenv(_TEST_OVERRIDE_FLAG, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _optional_positive_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None

    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")

    return value


def _optional_positive_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None

    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")

    return value


def _effective_trade_delay_days(config: dict) -> int:
    configured = int(config["security_limits"]["trade_delay_days"])

    if not _test_overrides_enabled():
        return configured

    override = _optional_positive_int("AURORATIO_TEST_TRADE_DELAY_DAYS")
    return override if override is not None else configured


def _effective_ratios(config: dict) -> dict:
    """
    Return strategy ratio thresholds without mutating the config object.

    In normal operation this is an exact copy of config["ratios"].
    Test-only Railway overrides are applied only when the explicit test flag
    is enabled.
    """
    thresholds = copy.deepcopy(config["ratios"])

    if not _test_overrides_enabled():
        return thresholds

    for (metal, side), env_name in _TEST_RATIO_ENV.items():
        override = _optional_positive_float(env_name)
        if override is not None:
            thresholds[metal][side] = override

    return thresholds


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        state = copy.deepcopy(DEFAULT_STATE)
        save_state(state)
        return state

    with open(STATE_FILE, encoding="utf-8") as f:
        state = json.load(f)

    # Migrate old single-module state if needed.
    if "current_position" in state:
        state = _migrate_old_state(state)
        save_state(state)

    return state


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _migrate_old_state(old: dict) -> dict:
    """Migrate from single-module to three-module state format."""
    pos = old.get("current_position", "GOLD")
    return {
        "module1": {
            "position": pos if pos in ("GOLD", "SILVER") else "GOLD",
            "silver_days": old.get("silver_days", 0),
            "history": old.get("history", []),
        },
        "module2": {
            "position": pos if pos in ("GOLD", "PLATINUM") else "GOLD",
            "platinum_days": old.get("platinum_days", 0),
            "history": [],
        },
        "module3": {
            "position": pos if pos in ("GOLD", "PALLADIUM") else "GOLD",
            "palladium_days": old.get("palladium_days", 0),
            "history": [],
        },
    }


def update_counters(state: dict, ratios: dict, config: dict) -> dict:
    """Update hysteresis counters for all three modules."""
    t = _effective_ratios(config)

    # Module 1 — Gold ↔ Silver
    m1 = state["module1"]
    pos = m1["position"]
    if pos == "GOLD" and ratios["AU_AG"] >= t["silver"]["buy"]:
        m1["silver_days"] += 1
    elif pos == "SILVER" and ratios["AU_AG"] <= t["silver"]["sell"]:
        m1["silver_days"] += 1
    else:
        m1["silver_days"] = 0

    # Module 2 — Gold ↔ Platinum
    m2 = state["module2"]
    pos = m2["position"]
    if pos == "GOLD" and ratios["AU_PT"] >= t["platinum"]["buy"]:
        m2["platinum_days"] += 1
    elif pos == "PLATINUM" and ratios["AU_PT"] <= t["platinum"]["sell"]:
        m2["platinum_days"] += 1
    else:
        m2["platinum_days"] = 0

    # Module 3 — Gold ↔ Palladium
    m3 = state["module3"]
    pos = m3["position"]
    if pos == "GOLD" and ratios["AU_PD"] >= t["palladium"]["buy"]:
        m3["palladium_days"] += 1
    elif pos == "PALLADIUM" and ratios["AU_PD"] <= t["palladium"]["sell"]:
        m3["palladium_days"] += 1
    else:
        m3["palladium_days"] = 0

    return state


def check_signals(state: dict, config: dict) -> dict:
    """
    Check all three modules for confirmed signals.

    Returns dict of module -> target metal (or None).
    Example: {"module1": "SILVER", "module2": None, "module3": None}
    """
    confirmation_days = _effective_trade_delay_days(config)
    signals = {}

    m1 = state["module1"]
    if m1["silver_days"] >= confirmation_days:
        signals["module1"] = "SILVER" if m1["position"] == "GOLD" else "GOLD"
    else:
        signals["module1"] = None

    m2 = state["module2"]
    if m2["platinum_days"] >= confirmation_days:
        signals["module2"] = "PLATINUM" if m2["position"] == "GOLD" else "GOLD"
    else:
        signals["module2"] = None

    m3 = state["module3"]
    if m3["palladium_days"] >= confirmation_days:
        signals["module3"] = "PALLADIUM" if m3["position"] == "GOLD" else "GOLD"
    else:
        signals["module3"] = None

    return signals


def record_switch(
    state: dict,
    module: str,
    from_metal: str,
    to_metal: str,
    ratio_name: str,
    ratio_value: float,
    date: str,
) -> dict:
    """Record a completed switch in the module's history."""
    state[module]["position"] = to_metal
    state[module]["history"].append(
        {
            "date": date,
            "from": from_metal,
            "to": to_metal,
            "ratio": ratio_name,
            "ratio_value": ratio_value,
        }
    )

    counter_key = {
        "module1": "silver_days",
        "module2": "platinum_days",
        "module3": "palladium_days",
    }[module]
    state[module][counter_key] = 0

    return state
