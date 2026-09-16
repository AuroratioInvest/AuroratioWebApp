import pytest

from models import ModuleStatus, User, UserBotState, UserModulePosition
from services import website_strategy_service as strategy


CASES = [
    ("M1", "AU_AG", "GOLD", "SILVER", 80.0, 79.99),
    ("M2", "AU_PT", "GOLD", "PLATINUM", 2.0, 1.99),
    ("M3", "AU_PD", "GOLD", "PALLADIUM", 4.0, 3.99),
    ("M1", "AU_AG", "SILVER", "GOLD", 40.0, 40.01),
    ("M2", "AU_PT", "PLATINUM", "GOLD", 0.45, 0.46),
    ("M3", "AU_PD", "PALLADIUM", "GOLD", 0.9, 0.91),
]


def _state_for(db_session, user_id: str, module: str, position: str):
    user = User(
        id=user_id,
        email=f"{user_id.lower()}@example.com",
        hashed_password="unused",
    )
    state = UserBotState(
        user_id=user_id,
        trading_enabled=True,
        m1_enabled=module == "M1",
        m2_enabled=module == "M2",
        m3_enabled=module == "M3",
        m1_position=position if module == "M1" else "GOLD",
        m2_position=position if module == "M2" else "GOLD",
        m3_position=position if module == "M3" else "GOLD",
        m1_status=ModuleStatus.ok,
        m2_status=ModuleStatus.ok,
        m3_status=ModuleStatus.ok,
    )
    ledger = UserModulePosition(
        user_id=user_id,
        module_name=module,
        metal=position,
        etf_symbol={
            "GOLD": "SGLN",
            "SILVER": "SSLN",
            "PLATINUM": "SPLT",
            "PALLADIUM": "SPDM",
        }[position],
    )
    db_session.add_all([user, state, ledger])
    db_session.commit()
    return state


@pytest.mark.parametrize(
    ("module", "ratio_name", "from_metal", "to_metal", "threshold", "outside"),
    CASES,
)
def test_threshold_is_inclusive_and_requires_two_consecutive_runs(
    monkeypatch,
    db_session,
    module,
    ratio_name,
    from_metal,
    to_metal,
    threshold,
    outside,
):
    user_id = f"user-{module}-{from_metal}"
    _state_for(db_session, user_id, module, from_metal)
    ratios = {"AU_AG": 60.0, "AU_PT": 1.0, "AU_PD": 2.0}
    ratios[ratio_name] = threshold
    monkeypatch.setattr(strategy, "get_latest_ratios", lambda: ratios)

    assert strategy.compute_user_signals(db_session, user_id) == []

    signals = strategy.compute_user_signals(db_session, user_id)

    assert len(signals) == 1
    assert signals[0].module_name == module
    assert signals[0].from_metal == from_metal
    assert signals[0].to_metal == to_metal
    assert signals[0].ratio_col == ratio_name
    assert signals[0].ratio_value == threshold

    ratios[ratio_name] = outside
    assert strategy.compute_user_signals(db_session, user_id) == []


def test_strategy_constants_preserve_current_financial_behavior():
    assert strategy.HYSTERESIS_DAYS == 2
    assert {
        name: rule["threshold"] for name, rule in strategy.BUY_RULES.items()
    } == {"M1": 80.0, "M2": 2.0, "M3": 4.0}
    assert {
        name: rule["threshold"] for name, rule in strategy.SELL_RULES.items()
    } == {"M1": 40.0, "M2": 0.45, "M3": 0.9}
