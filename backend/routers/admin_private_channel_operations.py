from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_active_admin
from models import User
from services.private_channel_operations_service import (
    CHANNEL_CONFIGURATION_DEFAULT_LIMIT,
    CHANNEL_CONFIGURATION_MAX_LIMIT,
    get_private_channel_operations_overview,
    list_private_channel_configuration,
)

router = APIRouter(
    prefix="/admin/private-channel-operations",
    tags=["Admin Private Channel Operations"],
)


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    del admin
    return get_private_channel_operations_overview(db)


@router.get("/channel-configuration")
def channel_configuration(
    limit: int = Query(
        default=CHANNEL_CONFIGURATION_DEFAULT_LIMIT,
        ge=1,
        le=CHANNEL_CONFIGURATION_MAX_LIMIT,
    ),
    after_channel_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    del admin
    try:
        return list_private_channel_configuration(
            db,
            limit=limit,
            after_channel_id=after_channel_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
