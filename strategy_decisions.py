"""Structured strategy decision boundary built around the existing root logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from types import MappingProxyType

import pandas as pd

from ratios import compute_ratios
from state import check_signals, update_counters

STRATEGY_IDENTIFIER = "precious-metals-relative-value"
STRATEGY_VERSION = "root-ratio-state-v1"

MODULE_RATIO = MappingProxyType(
    {
        "module1": ("AU_AG", "SILVER"),
        "module2": ("AU_PT", "PLATINUM"),
        "module3": ("AU_PD", "PALLADIUM"),
    }
)


@dataclass(frozen=True)
class StrategyDecisionCandidate:
    strategy_identifier: str
    strategy_version: str
    module: str
    ratio_identifier: str
    decision_date: date
    source_data_timestamp: datetime
    from_metal: str
    to_metal: str
    decision_type: str
    ratio_value: Decimal
    prices: MappingProxyType[str, Decimal]
    consecutive_days: int

    @property
    def identity_parts(self) -> tuple[str, str, str, str, str]:
        return (
            self.strategy_identifier,
            self.strategy_version,
            self.ratio_identifier,
            self.decision_date.isoformat(),
            self.decision_type,
        )


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def evaluate_confirmed_strategy_decisions(
    prices_df: pd.DataFrame,
    *,
    state: dict,
    config: dict,
    decision_date: date,
    source_data_timestamp: datetime,
) -> tuple[dict, list[StrategyDecisionCandidate], dict[str, Decimal]]:
    """Run the authoritative ratio/counter logic and return confirmed decisions.

    This function intentionally delegates formulas and two-day confirmation to
    ``ratios.compute_ratios``, ``state.update_counters``, and
    ``state.check_signals``.
    """

    if source_data_timestamp.tzinfo is None or source_data_timestamp.utcoffset() is None:
        raise ValueError("source_data_timestamp must be timezone-aware")
    source_data_timestamp = source_data_timestamp.astimezone(timezone.utc)

    ratios_df = compute_ratios(prices_df)
    latest_ratios = ratios_df.iloc[-1]
    ratios = {
        "AU_AG": round(float(latest_ratios["AU_AG"]), 4),
        "AU_PT": round(float(latest_ratios["AU_PT"]), 4),
        "AU_PD": round(float(latest_ratios["AU_PD"]), 4),
    }
    updated_state = update_counters(state, ratios, config)
    signals = check_signals(updated_state, config)
    latest_prices = prices_df.iloc[-1]
    price_context = MappingProxyType(
        {
            instrument: _to_decimal(latest_prices[instrument])
            for instrument in ["XAU", "XAG", "XPT", "XPD", "USDCHF"]
            if instrument in latest_prices
        }
    )

    decisions: list[StrategyDecisionCandidate] = []
    for module, target in signals.items():
        if target is None:
            continue
        ratio_identifier, _ = MODULE_RATIO[module]
        from_metal = str(updated_state[module]["position"])
        counter_key = {
            "module1": "silver_days",
            "module2": "platinum_days",
            "module3": "palladium_days",
        }[module]
        decisions.append(
            StrategyDecisionCandidate(
                strategy_identifier=STRATEGY_IDENTIFIER,
                strategy_version=STRATEGY_VERSION,
                module=module,
                ratio_identifier=ratio_identifier,
                decision_date=decision_date,
                source_data_timestamp=source_data_timestamp,
                from_metal=from_metal,
                to_metal=target,
                decision_type=f"{from_metal}_TO_{target}",
                ratio_value=Decimal(str(ratios[ratio_identifier])),
                prices=price_context,
                consecutive_days=int(updated_state[module][counter_key]),
            )
        )
    return updated_state, decisions, {key: Decimal(str(value)) for key, value in ratios.items()}
