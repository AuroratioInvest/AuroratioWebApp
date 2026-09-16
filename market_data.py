"""Provider-neutral market data boundary for the precious-metals strategy.

The current development adapter uses Yahoo Finance because that is what the
existing root scheduler already used for daily price retrieval. The strategy
consumes normalized observations from this module rather than broker execution
infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
import time
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketObservation:
    instrument: str
    price: Decimal
    source_timestamp: datetime
    retrieved_at: datetime
    currency: str
    unit: str
    source: str


YAHOO_TICKERS = {
    "XAU": "GC=F",
    "XAG": "SI=F",
    "XPT": "PL=F",
    "XPD": "PA=F",
    "USDCHF": "USDCHF=X",
}

METAL_INSTRUMENTS = {"XAU", "XAG", "XPT", "XPD"}
REQUIRED_INSTRUMENTS = tuple(YAHOO_TICKERS.keys())


class MarketDataValidationError(ValueError):
    """Raised when a provider result cannot safely feed the strategy."""


class YahooFinanceMarketDataProvider:
    """Development market-data adapter preserving the existing scheduler source."""

    source = "yahoo_finance"

    def __init__(self, *, pause_seconds: float = 2.0):
        self.pause_seconds = pause_seconds

    def latest_observations(self) -> dict[str, MarketObservation]:
        import yfinance as yf

        retrieved_at = datetime.now(timezone.utc)
        observations: dict[str, MarketObservation] = {}
        for instrument, ticker in YAHOO_TICKERS.items():
            try:
                df = yf.download(ticker, period="5d", auto_adjust=True, progress=False)
                if df is None or df.empty:
                    logger.warning("No market data returned for %s", instrument)
                    continue
                close = df["Close"].dropna()
                if close.empty:
                    logger.warning("No close price returned for %s", instrument)
                    continue
                latest_price = close.iloc[-1]
                if hasattr(latest_price, "item"):
                    latest_price = latest_price.item()
                latest_index = close.index[-1]
                source_timestamp = latest_index.to_pydatetime()
                if source_timestamp.tzinfo is None or source_timestamp.utcoffset() is None:
                    source_timestamp = source_timestamp.replace(tzinfo=timezone.utc)
                else:
                    source_timestamp = source_timestamp.astimezone(timezone.utc)
                observations[instrument] = MarketObservation(
                    instrument=instrument,
                    price=Decimal(str(latest_price)),
                    source_timestamp=source_timestamp,
                    retrieved_at=retrieved_at,
                    currency="USD" if instrument in METAL_INSTRUMENTS else "CHF_PER_USD",
                    unit="troy_ounce" if instrument in METAL_INSTRUMENTS else "fx_rate",
                    source=self.source,
                )
                logger.info("Fetched %s market observation", instrument)
            except Exception as exc:
                logger.warning("Failed to fetch market data for %s: %s", instrument, exc)
            time.sleep(self.pause_seconds)
        return observations


def max_market_data_age_days() -> int:
    raw = os.getenv("MARKET_DATA_MAX_AGE_DAYS", "4")
    try:
        value = int(raw)
    except ValueError as exc:
        raise MarketDataValidationError("MARKET_DATA_MAX_AGE_DAYS must be an integer") from exc
    if value < 0:
        raise MarketDataValidationError("MARKET_DATA_MAX_AGE_DAYS must be non-negative")
    return value


def validate_strategy_observations(
    observations: dict[str, MarketObservation],
    *,
    now: datetime | None = None,
) -> dict[str, Decimal]:
    """Validate and convert normalized observations to scheduler price columns."""

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise MarketDataValidationError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)

    missing = [instrument for instrument in REQUIRED_INSTRUMENTS if instrument not in observations]
    if missing:
        raise MarketDataValidationError(f"Missing market observations: {', '.join(missing)}")

    metal_dates = set()
    prices: dict[str, Decimal] = {}
    for instrument in REQUIRED_INSTRUMENTS:
        observation = observations[instrument]
        if observation.instrument != instrument:
            raise MarketDataValidationError(f"Observation instrument mismatch for {instrument}")
        try:
            price = Decimal(str(observation.price))
        except (InvalidOperation, ValueError) as exc:
            raise MarketDataValidationError(f"Invalid market price for {instrument}") from exc
        if price <= 0:
            raise MarketDataValidationError(f"Invalid non-positive market price for {instrument}")
        source_timestamp = observation.source_timestamp
        if source_timestamp.tzinfo is None or source_timestamp.utcoffset() is None:
            raise MarketDataValidationError(f"Naive source timestamp for {instrument}")
        source_timestamp = source_timestamp.astimezone(timezone.utc)
        if (now - source_timestamp).days > max_market_data_age_days():
            raise MarketDataValidationError(f"Stale market data for {instrument}")
        if instrument in METAL_INSTRUMENTS:
            if observation.currency != "USD" or observation.unit != "troy_ounce":
                raise MarketDataValidationError(f"Incompatible currency or unit for {instrument}")
            metal_dates.add(source_timestamp.date())
        elif observation.currency != "CHF_PER_USD" or observation.unit != "fx_rate":
            raise MarketDataValidationError(f"Incompatible currency or unit for {instrument}")
        prices[instrument] = price

    if len(metal_dates) != 1:
        raise MarketDataValidationError("Metal observations must share the same source date")
    return prices


def decimal_prices_to_float_dict(prices: dict[str, Decimal]) -> dict[str, float]:
    """Convert validated Decimal observations to the legacy CSV shape."""

    return {instrument: round(float(price), 4) for instrument, price in prices.items()}
