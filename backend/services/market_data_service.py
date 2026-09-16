from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from market_models import MarketPriceSnapshot


PRICE_COLUMNS = {
    "XAU": "xau_usd",
    "XAG": "xag_usd",
    "XPT": "xpt_usd",
    "XPD": "xpd_usd",
    "USDCHF": "usd_chf",
}


def store_validated_market_prices(
    db: Session,
    *,
    prices: Mapping[str, Decimal],
    source_timestamp: datetime,
    retrieved_at: datetime,
    source: str,
) -> MarketPriceSnapshot:
    """Insert or refresh one already-validated scheduler price snapshot."""

    missing = PRICE_COLUMNS.keys() - prices.keys()
    if missing:
        raise ValueError(f"Missing validated market prices: {', '.join(sorted(missing))}")
    if source_timestamp.tzinfo is None or source_timestamp.utcoffset() is None:
        raise ValueError("Market source timestamp must be timezone-aware")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("Market retrieval timestamp must be timezone-aware")

    values = {
        column: Decimal(str(prices[instrument]))
        for instrument, column in PRICE_COLUMNS.items()
    }
    if any(value <= 0 for value in values.values()):
        raise ValueError("Validated market prices must be positive")

    snapshot = db.get(MarketPriceSnapshot, source_timestamp)
    if snapshot is None:
        snapshot = MarketPriceSnapshot(
            source_timestamp=source_timestamp,
            retrieved_at=retrieved_at,
            source=source,
            **values,
        )
        db.add(snapshot)
    else:
        snapshot.retrieved_at = retrieved_at
        snapshot.source = source
        for column, value in values.items():
            setattr(snapshot, column, value)

    db.commit()
    db.refresh(snapshot)
    return snapshot
