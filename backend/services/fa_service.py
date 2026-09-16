from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models import (
    FAAuthorization,
    FAAuthorizationStatus,
    IBKRAccountMapping,
    TradingProvider,
    User,
    UserBotState,
    UserModulePosition,
)


DEFAULT_MODULES = {
    "M1": {
        "metal": "GOLD",
        "etf_symbol": "SGLN",
    },
    "M2": {
        "metal": "GOLD",
        "etf_symbol": "SGLN",
    },
    "M3": {
        "metal": "GOLD",
        "etf_symbol": "SGLN",
    },
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_user_bot_state(db: Session, user: User) -> UserBotState:
    state = (
        db.query(UserBotState)
        .filter(UserBotState.user_id == user.id)
        .first()
    )

    if state:
        return state

    state = UserBotState(
        user_id=user.id,
        trading_enabled=False,
    )
    db.add(state)
    db.flush()
    return state


def get_or_create_module_positions(db: Session, user: User) -> list[UserModulePosition]:
    existing = (
        db.query(UserModulePosition)
        .filter(UserModulePosition.user_id == user.id)
        .all()
    )
    existing_by_module = {position.module_name: position for position in existing}

    created_or_existing: list[UserModulePosition] = []

    for module_name, defaults in DEFAULT_MODULES.items():
        position = existing_by_module.get(module_name)

        if not position:
            position = UserModulePosition(
                user_id=user.id,
                module_name=module_name,
                metal=defaults["metal"],
                etf_symbol=defaults["etf_symbol"],
                quantity=0.0,
                last_value_chf=0.0,
                is_enabled=True,
            )
            db.add(position)
            db.flush()

        created_or_existing.append(position)

    return created_or_existing


def get_or_create_fa_authorization(db: Session, user: User) -> FAAuthorization:
    authorization = (
        db.query(FAAuthorization)
        .filter(FAAuthorization.user_id == user.id)
        .first()
    )

    if authorization:
        return authorization

    authorization = FAAuthorization(
        user_id=user.id,
        status=FAAuthorizationStatus.pending_authorization,
        requested_at=utc_now(),
    )
    db.add(authorization)
    db.flush()
    return authorization


def upsert_ibkr_account_mapping(
    db: Session,
    user: User,
    advisor_master_account_id: str,
    ibkr_client_account_id: str,
    account_alias: Optional[str] = None,
    base_currency: str = "CHF",
    is_active: bool = True,
    trading_enabled: bool = True,
) -> IBKRAccountMapping:
    mapping = (
        db.query(IBKRAccountMapping)
        .filter(IBKRAccountMapping.user_id == user.id)
        .first()
    )

    if not mapping:
        mapping = IBKRAccountMapping(
            user_id=user.id,
            advisor_master_account_id=advisor_master_account_id,
            ibkr_client_account_id=ibkr_client_account_id,
            account_alias=account_alias,
            base_currency=base_currency,
            is_active=is_active,
            trading_enabled=trading_enabled,
        )
        db.add(mapping)
    else:
        mapping.advisor_master_account_id = advisor_master_account_id
        mapping.ibkr_client_account_id = ibkr_client_account_id
        mapping.account_alias = account_alias
        mapping.base_currency = base_currency
        mapping.is_active = is_active
        mapping.trading_enabled = trading_enabled

    db.flush()
    return mapping


def activate_fa_authorization(
    db: Session,
    user: User,
    advisor_master_account_id: str,
    ibkr_client_account_id: str,
    account_alias: Optional[str] = None,
    base_currency: str = "CHF",
) -> tuple[FAAuthorization, IBKRAccountMapping]:
    authorization = get_or_create_fa_authorization(db, user)

    authorization.status = FAAuthorizationStatus.active
    authorization.advisor_master_account_id = advisor_master_account_id
    authorization.ibkr_client_account_id = ibkr_client_account_id
    authorization.activated_at = utc_now()
    authorization.revoked_at = None
    authorization.rejected_at = None
    authorization.suspended_at = None

    mapping = upsert_ibkr_account_mapping(
        db=db,
        user=user,
        advisor_master_account_id=advisor_master_account_id,
        ibkr_client_account_id=ibkr_client_account_id,
        account_alias=account_alias,
        base_currency=base_currency,
        is_active=True,
        trading_enabled=True,
    )

    user.preferred_trading_provider = TradingProvider.ibkr_fa

    state = get_or_create_user_bot_state(db, user)
    get_or_create_module_positions(db, user)

    # Do not automatically enable trading here.
    # The admin should explicitly enable trading after confirming:
    # - subscription is active,
    # - module ledger is initialized,
    # - account mapping is correct.
    user.trading_enabled = False
    state.trading_enabled = False

    db.flush()
    return authorization, mapping


def set_fa_status(
    db: Session,
    user: User,
    status: FAAuthorizationStatus,
    notes: Optional[str] = None,
) -> FAAuthorization:
    authorization = get_or_create_fa_authorization(db, user)
    authorization.status = status

    if notes is not None:
        authorization.notes = notes

    now = utc_now()

    if status == FAAuthorizationStatus.active:
        authorization.activated_at = now
    elif status == FAAuthorizationStatus.rejected:
        authorization.rejected_at = now
        disable_user_trading(db, user)
    elif status == FAAuthorizationStatus.revoked:
        authorization.revoked_at = now
        disable_user_trading(db, user)
    elif status == FAAuthorizationStatus.suspended:
        authorization.suspended_at = now
        disable_user_trading(db, user)
    elif status == FAAuthorizationStatus.pending_authorization:
        disable_user_trading(db, user)

    db.flush()
    return authorization


def enable_user_trading(db: Session, user: User) -> UserBotState:
    authorization = (
        db.query(FAAuthorization)
        .filter(FAAuthorization.user_id == user.id)
        .first()
    )
    mapping = (
        db.query(IBKRAccountMapping)
        .filter(IBKRAccountMapping.user_id == user.id)
        .first()
    )

    if not authorization or authorization.status != FAAuthorizationStatus.active:
        raise ValueError("Cannot enable trading: FA authorization is not active")

    if not mapping or not mapping.is_active or not mapping.trading_enabled:
        raise ValueError("Cannot enable trading: IBKR account mapping is not active")

    state = get_or_create_user_bot_state(db, user)
    get_or_create_module_positions(db, user)

    user.trading_enabled = True
    user.preferred_trading_provider = TradingProvider.ibkr_fa
    state.trading_enabled = True

    db.flush()
    return state


def disable_user_trading(db: Session, user: User) -> UserBotState:
    state = get_or_create_user_bot_state(db, user)

    user.trading_enabled = False
    state.trading_enabled = False

    mapping = (
        db.query(IBKRAccountMapping)
        .filter(IBKRAccountMapping.user_id == user.id)
        .first()
    )
    if mapping:
        mapping.trading_enabled = False

    db.flush()
    return state


def set_user_module_enabled(
    db: Session,
    user: User,
    module_name: str,
    enabled: bool,
) -> UserModulePosition:
    normalized_module = module_name.upper()

    position = (
        db.query(UserModulePosition)
        .filter(
            UserModulePosition.user_id == user.id,
            UserModulePosition.module_name == normalized_module,
        )
        .first()
    )

    if not position:
        get_or_create_module_positions(db, user)
        position = (
            db.query(UserModulePosition)
            .filter(
                UserModulePosition.user_id == user.id,
                UserModulePosition.module_name == normalized_module,
            )
            .first()
        )

    if not position:
        raise ValueError(f"Unknown module: {module_name}")

    position.is_enabled = enabled

    state = get_or_create_user_bot_state(db, user)

    if normalized_module == "M1":
        state.m1_enabled = enabled
    elif normalized_module == "M2":
        state.m2_enabled = enabled
    elif normalized_module == "M3":
        state.m3_enabled = enabled
    else:
        raise ValueError(f"Unknown module: {module_name}")

    db.flush()
    return position


def is_user_eligible_for_fa_execution(db: Session, user: User) -> bool:
    if not user.is_active:
        return False

    if not user.trading_enabled:
        return False

    state = (
        db.query(UserBotState)
        .filter(UserBotState.user_id == user.id)
        .first()
    )
    if not state or not state.trading_enabled:
        return False

    authorization = (
        db.query(FAAuthorization)
        .filter(FAAuthorization.user_id == user.id)
        .first()
    )
    if not authorization or authorization.status != FAAuthorizationStatus.active:
        return False

    mapping = (
        db.query(IBKRAccountMapping)
        .filter(IBKRAccountMapping.user_id == user.id)
        .first()
    )
    if not mapping or not mapping.is_active or not mapping.trading_enabled:
        return False

    return True