"""Protected routes for website execution testing/admin."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from core.features import require_legacy_customer_app
from dependencies import get_active_user
from models import (
    DailyBotReport,
    ExecutionLog,
    MembershipLevel,
    ModuleStatus,
    User,
)
from schemas import ExecutionLogResponse
from services.daily_report_service import (
    create_daily_bot_report,
    get_daily_bot_reports,
    get_latest_daily_bot_report,
    serialize_daily_bot_report,
)
from services.module_state_service import (
    get_or_create_user_bot_state,
    normalize_module,
    reset_module_failure,
    set_module_status,
)
from services.website_execution_service import execution_mode, run_website_execution

router = APIRouter()

VALID_MODULES = {"module1", "module2", "module3", "M1", "M2", "M3", "AU_AG", "AU_PT", "AU_PD"}


def require_admin(user: User) -> None:
    if user.membership_level != MembershipLevel.aurum:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.post("/run-now")
def run_now(
    user_id: str | None = Query(default=None),
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    summary = run_website_execution(db, user_id=user_id)

    create_daily_bot_report(
        db,
        summary=summary,
        triggered_by=f"admin:{current_user.id}",
    )

    return summary


@router.post(
    "/run-me",
    dependencies=[Depends(require_legacy_customer_app)],
)
def run_me(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    return run_website_execution(db, user_id=current_user.id)


@router.get("/mode")
def get_mode(current_user: User = Depends(get_active_user)):
    require_admin(current_user)
    return {"mode": execution_mode()}


@router.get("/logs", response_model=list[ExecutionLogResponse])
def get_logs(
    user_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    query = db.query(ExecutionLog)

    if user_id:
        query = query.filter(ExecutionLog.user_id == user_id)

    return (
        query.order_by(ExecutionLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get(
    "/my-logs",
    response_model=list[ExecutionLogResponse],
    dependencies=[Depends(require_legacy_customer_app)],
)
def get_my_logs(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ExecutionLog)
        .filter(ExecutionLog.user_id == current_user.id)
        .order_by(ExecutionLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get(
    "/state",
    dependencies=[Depends(require_legacy_customer_app)],
)
def get_my_execution_state(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    state = get_or_create_user_bot_state(db, current_user.id)

    return {
        "trading_enabled": state.trading_enabled,
        "module1": {
            "code": "M1",
            "position": state.m1_position,
            "enabled": state.m1_enabled,
            "status": state.m1_status.value,
            "error": state.m1_error_message,
            "last_trade_at": state.m1_last_trade_at.isoformat()
            if state.m1_last_trade_at
            else None,
        },
        "module2": {
            "code": "M2",
            "position": state.m2_position,
            "enabled": state.m2_enabled,
            "status": state.m2_status.value,
            "error": state.m2_error_message,
            "last_trade_at": state.m2_last_trade_at.isoformat()
            if state.m2_last_trade_at
            else None,
        },
        "module3": {
            "code": "M3",
            "position": state.m3_position,
            "enabled": state.m3_enabled,
            "status": state.m3_status.value,
            "error": state.m3_error_message,
            "last_trade_at": state.m3_last_trade_at.isoformat()
            if state.m3_last_trade_at
            else None,
        },
    }


@router.post(
    "/modules/{module_name}/reset",
    dependencies=[Depends(require_legacy_customer_app)],
)
def reset_module(
    module_name: str,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if module_name not in VALID_MODULES:
        raise HTTPException(status_code=400, detail="Invalid module")

    normalized_module = normalize_module(module_name)
    state = get_or_create_user_bot_state(db, current_user.id)

    reset_module_failure(state, normalized_module)
    set_module_status(state, normalized_module, ModuleStatus.ok, None)

    db.commit()
    return {"status": "reset", "module": normalized_module}


@router.post(
    "/modules/{module_name}/pause",
    dependencies=[Depends(require_legacy_customer_app)],
)
def pause_module(
    module_name: str,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if module_name not in VALID_MODULES:
        raise HTTPException(status_code=400, detail="Invalid module")

    normalized_module = normalize_module(module_name)
    state = get_or_create_user_bot_state(db, current_user.id)

    set_module_status(state, normalized_module, ModuleStatus.paused, "Paused manually")
    db.commit()

    return {"status": "paused", "module": normalized_module}


@router.post(
    "/modules/{module_name}/resume",
    dependencies=[Depends(require_legacy_customer_app)],
)
def resume_module(
    module_name: str,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if module_name not in VALID_MODULES:
        raise HTTPException(status_code=400, detail="Invalid module")

    normalized_module = normalize_module(module_name)
    state = get_or_create_user_bot_state(db, current_user.id)

    set_module_status(state, normalized_module, ModuleStatus.ok, None)
    db.commit()

    return {"status": "resumed", "module": normalized_module}


@router.get("/reports/latest")
def latest_report(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    report = get_latest_daily_bot_report(db)

    if not report:
        return None

    return serialize_daily_bot_report(report)


@router.get("/reports")
def list_reports(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    reports = get_daily_bot_reports(db, limit=20)

    return [serialize_daily_bot_report(report) for report in reports]
