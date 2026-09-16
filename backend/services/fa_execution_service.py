from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    ExecutionLog,
    ExecutionStatus,
    FAAuthorization,
    FAAuthorizationStatus,
    IBKRAccountMapping,
    TradingProvider,
    User,
    UserModulePosition,
)
from services.fa_service import is_user_eligible_for_fa_execution
from services.ibkr_fa_client import IBKRFAClient


METAL_TO_DEFAULT_ETF = {
    "GOLD": "SGLN",
    "SILVER": "SSLN",
    "PLATINUM": "SPLT",
    "PALLADIUM": "SPDM",
}


@dataclass
class FAModuleSwitchRequest:
    user: User
    module_name: str
    from_metal: str
    to_metal: str
    ratio_col: Optional[str] = None
    ratio_value: Optional[float] = None
    dry_run: bool = True
    run_date: Optional[date] = None


@dataclass
class FAModuleSwitchResult:
    execution_log: ExecutionLog
    skipped: bool
    message: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_metal(metal: str) -> str:
    return metal.strip().upper()


def normalize_module(module_name: str) -> str:
    normalized = module_name.strip().upper()

    aliases = {
        "MODULE1": "M1",
        "MODULE_1": "M1",
        "AU_AG": "M1",
        "M1": "M1",
        "MODULE2": "M2",
        "MODULE_2": "M2",
        "AU_PT": "M2",
        "M2": "M2",
        "MODULE3": "M3",
        "MODULE_3": "M3",
        "AU_PD": "M3",
        "M3": "M3",
    }

    return aliases.get(normalized, normalized)


def build_idempotency_key(
    user_id: str,
    module_name: str,
    from_metal: str,
    to_metal: str,
    run_date: date,
) -> str:
    return (
        f"fa-switch:"
        f"{run_date.isoformat()}:"
        f"{user_id}:"
        f"{normalize_module(module_name)}:"
        f"{normalize_metal(from_metal)}:"
        f"{normalize_metal(to_metal)}"
    )


def get_module_position(
    db: Session,
    user_id: str,
    module_name: str,
) -> Optional[UserModulePosition]:
    return (
        db.query(UserModulePosition)
        .filter(
            UserModulePosition.user_id == user_id,
            UserModulePosition.module_name == normalize_module(module_name),
        )
        .first()
    )


def get_fa_authorization(db: Session, user_id: str) -> Optional[FAAuthorization]:
    return db.query(FAAuthorization).filter(FAAuthorization.user_id == user_id).first()


def get_ibkr_mapping(db: Session, user_id: str) -> Optional[IBKRAccountMapping]:
    return db.query(IBKRAccountMapping).filter(IBKRAccountMapping.user_id == user_id).first()


def find_existing_execution_log(
    db: Session,
    idempotency_key: str,
) -> Optional[ExecutionLog]:
    return db.query(ExecutionLog).filter(ExecutionLog.idempotency_key == idempotency_key).first()


def create_execution_log(
    db: Session,
    request: FAModuleSwitchRequest,
    module_position: Optional[UserModulePosition],
    idempotency_key: str,
    status: ExecutionStatus = ExecutionStatus.pending,
    error_message: Optional[str] = None,
) -> ExecutionLog:
    authorization = get_fa_authorization(db, request.user.id)
    mapping = get_ibkr_mapping(db, request.user.id)

    row = ExecutionLog(
        user_id=request.user.id,
        idempotency_key=idempotency_key,
        provider=TradingProvider.ibkr_fa,
        fa_authorization_id=authorization.id if authorization else None,
        ibkr_account_mapping_id=mapping.id if mapping else None,
        module_name=normalize_module(request.module_name),
        from_metal=normalize_metal(request.from_metal),
        to_metal=normalize_metal(request.to_metal),
        ratio_col=request.ratio_col,
        ratio_value=request.ratio_value,
        target_value_chf=module_position.last_value_chf if module_position else None,
        estimated_value_chf=module_position.last_value_chf if module_position else None,
        from_quantity=module_position.quantity if module_position else None,
        dry_run=request.dry_run,
        status=status,
        error_message=error_message,
        created_at=utc_now(),
    )
    db.add(row)
    db.flush()
    return row


def skip_with_log(
    db: Session,
    request: FAModuleSwitchRequest,
    module_position: Optional[UserModulePosition],
    idempotency_key: str,
    message: str,
) -> FAModuleSwitchResult:
    existing = find_existing_execution_log(db, idempotency_key)
    if existing:
        return FAModuleSwitchResult(
            execution_log=existing,
            skipped=True,
            message=f"Duplicate execution skipped: {message}",
        )

    row = create_execution_log(
        db=db,
        request=request,
        module_position=module_position,
        idempotency_key=idempotency_key,
        status=ExecutionStatus.skipped,
        error_message=message,
    )
    row.finished_at = utc_now()
    db.flush()

    return FAModuleSwitchResult(
        execution_log=row,
        skipped=True,
        message=message,
    )


def validate_execution_request(
    db: Session,
    request: FAModuleSwitchRequest,
) -> tuple[bool, Optional[str], Optional[UserModulePosition]]:
    if not is_user_eligible_for_fa_execution(db, request.user):
        return False, "User is not eligible for IBKR FA execution", None

    authorization = get_fa_authorization(db, request.user.id)
    if not authorization or authorization.status != FAAuthorizationStatus.active:
        return False, "FA authorization is not active", None

    mapping = get_ibkr_mapping(db, request.user.id)
    if not mapping or not mapping.is_active or not mapping.trading_enabled:
        return False, "IBKR account mapping is not active for trading", None

    module_position = get_module_position(
        db=db,
        user_id=request.user.id,
        module_name=request.module_name,
    )

    if not module_position:
        return False, "Missing virtual module position", None

    if not module_position.is_enabled:
        return False, "Module is disabled", module_position

    expected_from_metal = normalize_metal(request.from_metal)
    actual_metal = normalize_metal(module_position.metal)

    if actual_metal != expected_from_metal:
        return (
            False,
            f"Virtual module is on {actual_metal}, not {expected_from_metal}",
            module_position,
        )

    if not module_position.quantity or module_position.quantity <= 0:
        return False, "Module quantity is zero; nothing to sell", module_position

    if normalize_metal(request.to_metal) not in METAL_TO_DEFAULT_ETF:
        return False, f"Unsupported target metal: {request.to_metal}", module_position

    if not module_position.etf_symbol:
        return False, "Missing source ETF symbol in virtual module ledger", module_position

    return True, None, module_position


def execute_module_switch(
    db: Session,
    request: FAModuleSwitchRequest,
) -> FAModuleSwitchResult:
    """
    Executes one module switch for one FA client account.

    Example:
        Signal: M1 GOLD -> SILVER

    IBKR real account may show:
        SGLN total = 25 shares

    AuroRatio virtual ledger may show:
        M1 = 10 SGLN
        M3 = 15 SGLN

    This function sells only the M1 quantity, not the whole real SGLN position.
    """

    run_date = request.run_date or date.today()
    module_name = normalize_module(request.module_name)
    from_metal = normalize_metal(request.from_metal)
    to_metal = normalize_metal(request.to_metal)

    idempotency_key = build_idempotency_key(
        user_id=request.user.id,
        module_name=module_name,
        from_metal=from_metal,
        to_metal=to_metal,
        run_date=run_date,
    )

    existing = find_existing_execution_log(db, idempotency_key)
    if existing:
        return FAModuleSwitchResult(
            execution_log=existing,
            skipped=True,
            message="Duplicate execution skipped by idempotency key",
        )

    is_valid, error_message, module_position = validate_execution_request(db, request)

    if not is_valid:
        return skip_with_log(
            db=db,
            request=request,
            module_position=module_position,
            idempotency_key=idempotency_key,
            message=error_message or "Invalid execution request",
        )

    try:
        log = create_execution_log(
            db=db,
            request=request,
            module_position=module_position,
            idempotency_key=idempotency_key,
            status=ExecutionStatus.pending,
        )
    except IntegrityError:
        db.rollback()
        existing_after_race = find_existing_execution_log(db, idempotency_key)
        if existing_after_race:
            return FAModuleSwitchResult(
                execution_log=existing_after_race,
                skipped=True,
                message="Duplicate execution skipped after concurrent insert",
            )
        raise

    try:
        if request.dry_run:
            return execute_dry_run(
                db=db,
                log=log,
                module_position=module_position,
                to_metal=to_metal,
            )

        return execute_live_ibkr_switch(
            db=db,
            request=request,
            log=log,
            module_position=module_position,
            to_metal=to_metal,
            module_name=module_name,
            idempotency_key=idempotency_key,
        )

    except Exception as exc:
        log.status = ExecutionStatus.failed
        log.error_message = str(exc)
        log.finished_at = utc_now()
        db.flush()

        return FAModuleSwitchResult(
            execution_log=log,
            skipped=False,
            message=f"IBKR FA module switch failed: {exc}",
        )


def execute_dry_run(
    *,
    db: Session,
    log: ExecutionLog,
    module_position: UserModulePosition,
    to_metal: str,
) -> FAModuleSwitchResult:
    buy_symbol = METAL_TO_DEFAULT_ETF[to_metal]

    estimated_to_quantity = estimate_target_quantity_from_value(
        target_value_chf=module_position.last_value_chf,
        to_metal=to_metal,
    )

    log.sell_order_id = f"DRY-RUN-SELL-{log.id}"
    log.buy_order_id = f"DRY-RUN-BUY-{log.id}"
    log.order_id = log.buy_order_id
    log.to_quantity = estimated_to_quantity
    log.units = estimated_to_quantity
    log.status = ExecutionStatus.success
    log.finished_at = utc_now()
    log.raw_response = json.dumps(
        {
            "mode": "dry_run",
            "message": "No order submitted to IBKR",
            "from_symbol": module_position.etf_symbol,
            "from_quantity": module_position.quantity,
            "to_symbol": buy_symbol,
            "estimated_to_quantity": estimated_to_quantity,
            "target_value_chf": module_position.last_value_chf,
        }
    )

    db.flush()

    return FAModuleSwitchResult(
        execution_log=log,
        skipped=False,
        message="Dry-run module switch completed",
    )


def execute_live_ibkr_switch(
    *,
    db: Session,
    request: FAModuleSwitchRequest,
    log: ExecutionLog,
    module_position: UserModulePosition,
    to_metal: str,
    module_name: str,
    idempotency_key: str,
) -> FAModuleSwitchResult:
    mapping = get_ibkr_mapping(db, request.user.id)
    if not mapping:
        raise ValueError("Missing IBKR account mapping")

    client = IBKRFAClient()

    sell_result = client.sell_module_position(
        account_id=mapping.ibkr_client_account_id,
        symbol=module_position.etf_symbol,
        quantity=module_position.quantity,
        idempotency_key=f"{idempotency_key}:sell",
    )

    if not sell_result.ok:
        raise RuntimeError(f"Sell failed: {sell_result.error}")

    filled_value_chf = float(
        sell_result.filled_value_chf
        or module_position.last_value_chf
        or 0.0
    )

    if filled_value_chf <= 0:
        raise RuntimeError("Sell completed but filled value is zero")

    buy_symbol = METAL_TO_DEFAULT_ETF[to_metal]

    buy_result = client.buy_with_cash_value(
        account_id=mapping.ibkr_client_account_id,
        symbol=buy_symbol,
        value_chf=filled_value_chf,
        idempotency_key=f"{idempotency_key}:buy",
    )

    if not buy_result.ok:
        raise RuntimeError(f"Buy failed after sell: {buy_result.error}")

    bought_quantity = float(buy_result.filled_quantity or 0.0)

    if bought_quantity <= 0:
        raise RuntimeError("Buy completed but filled quantity is zero")

    module_position.metal = to_metal
    module_position.etf_symbol = buy_symbol
    module_position.quantity = bought_quantity
    module_position.last_value_chf = filled_value_chf
    module_position.last_fill_price = buy_result.fill_price
    module_position.last_sell_order_id = sell_result.order_id
    module_position.last_buy_order_id = buy_result.order_id
    module_position.last_execution_log_id = log.id

    log.sell_order_id = sell_result.order_id
    log.buy_order_id = buy_result.order_id
    log.order_id = buy_result.order_id
    log.to_quantity = bought_quantity
    log.units = bought_quantity
    log.estimated_value_chf = filled_value_chf
    log.status = ExecutionStatus.success
    log.finished_at = utc_now()
    log.raw_response = json.dumps(
        {
            "sell": sell_result.raw,
            "buy": buy_result.raw,
            "module_ledger_after": {
                "module_name": module_name,
                "metal": module_position.metal,
                "etf_symbol": module_position.etf_symbol,
                "quantity": module_position.quantity,
                "last_value_chf": module_position.last_value_chf,
            },
        },
        default=str,
    )

    db.flush()

    return FAModuleSwitchResult(
        execution_log=log,
        skipped=False,
        message="IBKR FA module switch executed",
    )


def estimate_target_quantity_from_value(
    target_value_chf: Optional[float],
    to_metal: str,
) -> float:
    """
    Dry-run estimator only.

    In live mode, quantity must come from the IBKR fill result.
    """
    if not target_value_chf:
        return 0.0

    return float(target_value_chf)