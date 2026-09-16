import sys, os
from typing import List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(BASE_DIR)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import User, SignalLog
from dependencies import get_active_user
from services.module_state_service import get_or_create_user_bot_state
from ratios import get_latest_ratios, compute_ratios
import schemas
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/ratios", response_model=schemas.RatiosResponse)
def get_ratios(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db)
):
    try:
        ratios = get_latest_ratios()
    except Exception as e:
        import traceback
        logger.error(f"get_ratios error: {traceback.format_exc()}")
        raise HTTPException(status_code=503,
                            detail=f"Price data unavailable: {str(e)}")
    return schemas.RatiosResponse(**ratios)


@router.get("/state", response_model=schemas.BotStateResponse)
def get_state(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db)
):
    return get_or_create_user_bot_state(db, current_user.id)


@router.get("/history", response_model=List[schemas.SignalLogResponse])
def get_history(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db)
):
    return db.query(SignalLog)\
        .filter(SignalLog.signal_fired == True)\
            .order_by(SignalLog.date.desc())\
                .limit(50)\
                    .all()


@router.get("/ratios/history")
def get_ratios_history(
    current_user: User = Depends(get_active_user),
):
    try:
        import pandas as pd
        csv_path  = os.path.join(BASE_DIR, "data", "prices_clean.csv")
        df        = pd.read_csv(csv_path, index_col="Date", parse_dates=True)
        df        = df.tail(365)
        ratios_df = compute_ratios(df)

        return {
            "AU_AG": [
                {"time": str(d.date()), "value": round(float(v), 2)}
                for d, v in ratios_df["AU_AG"].dropna().items()
            ],
            "AU_PT": [
                {"time": str(d.date()), "value": round(float(v), 2)}
                for d, v in ratios_df["AU_PT"].dropna().items()
            ],
            "AU_PD": [
                {"time": str(d.date()), "value": round(float(v), 2)}
                for d, v in ratios_df["AU_PD"].dropna().items()
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=503,
                            detail=f"Chart data unavailable: {str(e)}")