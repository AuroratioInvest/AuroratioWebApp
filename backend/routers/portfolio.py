from datetime import datetime, timezone
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from snaptrade_client import SnapTrade
from sqlalchemy.orm import Session

import schemas
from database import get_db
from dependencies import get_active_user
from models import PortfolioSnapshot, Position, User
from services.module_state_service import (
    get_or_create_all_module_positions,
    get_or_create_user_bot_state,
)
from services.portfolio_service import (
    build_module_display_from_ledger,
    get_virtual_module_positions,
    sync_positions_from_snaptrade,
)

router = APIRouter()

snaptrade = SnapTrade(
    consumer_key=os.getenv("SNAPTRADE_CONSUMER_KEY"),
    client_id=os.getenv("SNAPTRADE_CLIENT_ID"),
)


@router.get("/snapshots", response_model=List[schemas.PortfolioSnapshotResponse])
def get_snapshots(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.user_id == current_user.id)
        .order_by(PortfolioSnapshot.date.desc())
        .limit(90)
        .all()
    )


@router.get("/position", response_model=schemas.PositionResponse)
def get_position(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    position = (
        db.query(Position)
        .filter(Position.user_id == current_user.id)
        .order_by(Position.last_synced_at.desc())
        .first()
    )

    if position is None:
        raise HTTPException(status_code=404, detail="No position found")

    return position


@router.get("/positions")
def get_positions(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Position)
        .filter(Position.user_id == current_user.id)
        .order_by(Position.last_synced_at.desc())
        .all()
    )

    return [
        {
            "id": row.id,
            "metal": row.metal,
            "etf_symbol": row.etf_symbol,
            "quantity": row.quantity,
            "last_price_gbp": row.last_price_gbp,
            "value_chf": row.value_chf,
            "last_synced_at": row.last_synced_at.isoformat()
            if row.last_synced_at
            else None,
        }
        for row in rows
    ]


@router.get("/modules")
def get_module_positions(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    get_or_create_user_bot_state(db, current_user.id)
    get_or_create_all_module_positions(db, current_user.id)
    db.commit()

    return {
        "modules": get_virtual_module_positions(db, current_user.id),
        "last_synced": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/balance")
def get_balance(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    get_or_create_user_bot_state(db, current_user.id)
    get_or_create_all_module_positions(db, current_user.id)
    db.commit()

    snaptrade_result = sync_positions_from_snaptrade(db, current_user.id, snaptrade)

    total_chf = float(snaptrade_result.get("total_chf") or 0.0)
    real_positions = snaptrade_result.get("positions") or []

    modules = build_module_display_from_ledger(
        db=db,
        user_id=current_user.id,
        total_chf=total_chf,
    )

    return {
        "total_chf": round(total_chf, 2),
        "modules": modules,
        "virtual_modules": list(modules.values()),
        "real_positions": real_positions,
        "positions": real_positions,
        "execution_provider": "ibkr_fa",
        "display_provider": "snaptrade",
        "last_synced": datetime.now(timezone.utc).isoformat(),
        "note": (
            "real_positions come from SnapTrade for display; "
            "modules come from AuroRatio virtual ledger for FA execution."
        ),
    }