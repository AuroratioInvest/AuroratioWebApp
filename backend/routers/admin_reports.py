from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_active_user
from models import User, MembershipLevel, ExecutionLog, UserBotState

router = APIRouter()


def require_admin(user: User) -> None:
    level = user.membership_level.value if hasattr(user.membership_level, "value") else str(user.membership_level)
    if level != MembershipLevel.aurum.value:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/execution-summary")
def execution_summary(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    logs = db.query(ExecutionLog).order_by(ExecutionLog.created_at.desc()).limit(50).all()
    states = db.query(UserBotState).all()
    return {
        "latest_logs": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "module": row.module_name,
                "from": row.from_metal,
                "to": row.to_metal,
                "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                "error": row.error_message,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in logs
        ],
        "module_states": [
            {
                "user_id": s.user_id,
                "trading_enabled": s.trading_enabled,
                "m1_status": s.m1_status.value,
                "m2_status": s.m2_status.value,
                "m3_status": s.m3_status.value,
                "m1_error": s.m1_error_message,
                "m2_error": s.m2_error_message,
                "m3_error": s.m3_error_message,
            }
            for s in states
        ],
    }
