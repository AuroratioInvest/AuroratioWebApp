from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from market_models import MarketPriceSnapshot


router = APIRouter()

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
STATE_FILE = PROJECT_ROOT / "state.json"
ROOT_PRICES_FILE = PROJECT_ROOT / "data" / "prices_clean.csv"
BACKTEST_RESULTS_FILE = BACKEND_DIR / "static" / "backtest_results.json"
USD_EUR_RATE = 0.92

METALS = {
    "gold": ("XAU", "Gold", "xau_usd"),
    "silver": ("XAG", "Silver", "xag_usd"),
    "platinum": ("XPT", "Platinum", "xpt_usd"),
    "palladium": ("XPD", "Palladium", "xpd_usd"),
}


def _price(snapshot: MarketPriceSnapshot, column: str) -> float:
    value = float(getattr(snapshot, column))
    if value <= 0:
        raise HTTPException(status_code=503, detail="Stored market data is invalid")
    return value


def _market_state() -> dict[str, str]:
    state = {"signal": "HOLD", "current_metal": "Gold"}
    if STATE_FILE.exists():
        try:
            loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    return state


def _local_file_fallback_enabled(db: Session) -> bool:
    """Allow the repository CSV only for explicit SQLite development."""

    configured = os.getenv("MARKET_DATA_LOCAL_FILE_FALLBACK", "true").strip().lower()
    return db.get_bind().dialect.name == "sqlite" and configured in {"1", "true", "yes", "on"}


def _load_local_file_snapshots() -> list[SimpleNamespace]:
    try:
        frame = pd.read_csv(ROOT_PRICES_FILE)
    except (OSError, pd.errors.ParserError) as exc:
        raise HTTPException(
            status_code=503,
            detail="No validated market data is available",
        ) from exc

    columns = ["XAU", "XAG", "XPT", "XPD", "USDCHF"]
    if not set(columns).issubset(frame.columns):
        raise HTTPException(status_code=503, detail="No validated market data is available")
    valid = frame.dropna(subset=columns)
    valid = valid[(valid[columns] > 0).all(axis=1)].tail(31)
    if valid.empty:
        raise HTTPException(status_code=503, detail="No validated market data is available")

    return [
        SimpleNamespace(
            xau_usd=row.XAU,
            xag_usd=row.XAG,
            xpt_usd=row.XPT,
            xpd_usd=row.XPD,
            usd_chf=row.USDCHF,
        )
        for row in reversed(list(valid.itertuples(index=False)))
    ]


@router.get("/data")
def get_market_data(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Return the latest validated market snapshots stored by the scheduler."""

    try:
        snapshots = (
            db.query(MarketPriceSnapshot)
            .order_by(MarketPriceSnapshot.source_timestamp.desc())
            .limit(31)
            .all()
        )
    except SQLAlchemyError as exc:
        db.rollback()
        if not _local_file_fallback_enabled(db):
            raise HTTPException(status_code=503, detail="Market data store is unavailable") from exc
        snapshots = []
    if not snapshots and _local_file_fallback_enabled(db):
        snapshots = _load_local_file_snapshots()
    if not snapshots:
        raise HTTPException(
            status_code=503,
            detail="No validated market data is available",
        )

    latest = snapshots[0]
    previous = snapshots[1] if len(snapshots) > 1 else latest
    performance_reference = snapshots[29] if len(snapshots) > 30 else None
    usd_chf = _price(latest, "usd_chf")

    metals: dict[str, dict[str, Any]] = {}
    prices: dict[str, float] = {}
    for key, (symbol, name, column) in METALS.items():
        latest_price = _price(latest, column)
        previous_price = _price(previous, column)
        change = latest_price - previous_price
        change_percent = ((latest_price / previous_price) - 1) * 100

        performance = 50.0
        if performance_reference is not None:
            historical_price = _price(performance_reference, column)
            performance_change = ((latest_price / historical_price) - 1) * 100
            performance = max(0.0, min(100.0, 50.0 + performance_change * 2.5))

        prices[symbol] = latest_price
        metals[key] = {
            "symbol": symbol,
            "name": name,
            "priceUSD": latest_price,
            "priceCHF": latest_price * usd_chf,
            "priceEUR": latest_price * USD_EUR_RATE,
            "change24h": change,
            "changePercent": change_percent,
            "performance": performance,
        }

    state = _market_state()
    return {
        "metals": metals,
        "ratios": {
            "AU_AG": prices["XAU"] / prices["XAG"],
            "AU_PT": prices["XAU"] / prices["XPT"],
            "AU_PD": prices["XAU"] / prices["XPD"],
        },
        "signal": state.get("signal", "HOLD"),
        "signalMetal": state.get("current_metal", "Gold"),
    }


@router.get("/backtest/results")
def get_backtest_results() -> JSONResponse:
    """Return the immutable backtest summary packaged with the backend."""

    try:
        result = json.loads(BACKTEST_RESULTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Packaged backtest results are unavailable",
        ) from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="Packaged backtest results are invalid")
    return JSONResponse(
        content=result,
        media_type="application/json; charset=utf-8",
    )
