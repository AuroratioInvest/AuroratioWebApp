from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_active_user
from models import TradeLog, User

router = APIRouter()

MODULE_LABELS = {
    "M1": "Gold ↔ Silver",
    "M2": "Gold ↔ Platinum",
    "M3": "Gold ↔ Palladium",
    "module1": "Gold ↔ Silver",
    "module2": "Gold ↔ Platinum",
    "module3": "Gold ↔ Palladium",
}


@router.get("/history")
def get_trade_history(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    offset = (page - 1) * limit

    query = (
        db.query(TradeLog)
        .filter(TradeLog.user_id == current_user.id)
        .order_by(TradeLog.date.desc())
    )

    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    trades = []

    for row in rows:
        module_code = row.module_name or row.ratio_col or "—"

        action = None
        if row.from_metal and row.to_metal:
            action = f"{row.from_metal} → {row.to_metal}"

        trades.append(
            {
                "id": row.id,
                "date": row.date.isoformat() if row.date else None,
                "module": module_code,
                "module_label": MODULE_LABELS.get(module_code, module_code),
                "provider": row.provider.value if hasattr(row.provider, "value") else str(row.provider),
                "action": action,
                "from_metal": row.from_metal,
                "to_metal": row.to_metal,
                "ratio_col": row.ratio_col,
                "ratio": row.ratio_value,
                "quantity": row.quantity,
                "amount": row.quantity,
                "fill_price": row.fill_price,
                "sell_order_id": row.sell_order_id,
                "buy_order_id": row.buy_order_id,
                "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                "error_message": row.error_message,
            }
        )

    return {
        "trades": trades,
        "page": page,
        "limit": limit,
        "total": total,
        "has_next": offset + limit < total,
    }