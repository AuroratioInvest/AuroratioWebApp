"""
scheduler.py — Subscriber Signal Pipeline Orchestrator
=======================================================
PURPOSE:
    Runs the accountless subscriber signal pipeline automatically every weekday
    at 17:05 CET (SIX exchange close time).

    When triggered, it executes 5 steps in sequence:
      1. Fetch today's prices from Yahoo Finance
      2. Persist the validated snapshot and append it to local history
      3. Reuse the existing ratio and two-day confirmation logic
      4. Persist confirmed subscriber signals and durable publication work
      5. Leave delivery to the signal-publication worker command

    The bot can also be run immediately for testing:
        python scheduler.py --now

HOW THE SCHEDULER WORKS:
    The `schedule` library lets you register functions to run at specific times.
    Once started, the main loop runs every 30 seconds, checks if any scheduled
    job is due, and executes it if so.
    The bot keeps running indefinitely until you press Ctrl+C.

        schedule.every().monday.at("17:05").do(run_daily_cycle)
        → "Every Monday at 17:05, call run_daily_cycle()"

IMPORTANT:
    This scheduler does not connect to brokers and does not execute trades.
    Subscribers manually evaluate and execute published signals through their
    own brokerage accounts.

HOW TO RUN:
    Daily mode (runs every weekday at 17:05 CET):
        python scheduler.py

    Daily mode with backtest-only data on first download:
        python scheduler.py --backtest

    Immediate test (runs the full cycle right now, skips the schedule):
        python scheduler.py --now

    Immediate test with backtest-only data on first download:
        python scheduler.py --now --backtest
"""

import os
import sys
import argparse
import asyncio
import logging
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "data", "prices_clean.csv")
BACKEND_DIR = os.path.join(HERE, "backend")
ENV_PATH = os.path.join(BACKEND_DIR, ".env")

load_dotenv(ENV_PATH)
if BACKEND_DIR not in sys.path:
    sys.path.append(BACKEND_DIR)

import time
import yaml
import pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from market_data import (
    YahooFinanceMarketDataProvider,
    decimal_prices_to_float_dict,
    validate_strategy_observations,
)
from ratios import compute_ratios
from state import load_state, save_state, record_switch
from strategy_decisions import evaluate_confirmed_strategy_decisions

# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────
os.makedirs(os.path.join(HERE, "data"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(HERE, "data", f"cycle_{datetime.now().strftime('%Y%m%d')}.log")
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BUSINESS_TIMEZONE = os.getenv("AURORATIO_STRATEGY_TIMEZONE", "Europe/Paris")
BUSINESS_TZ = ZoneInfo(BUSINESS_TIMEZONE)
STRATEGY_RUN_HOUR = 17
STRATEGY_RUN_MINUTE = 5


def business_now() -> datetime:
    """Return the current strategy business time explicitly in Europe/Paris by default."""
    return datetime.now(BUSINESS_TZ)


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def load_config():
    """Load settings from config.yaml."""
    with open(os.path.join(HERE, "config.yaml")) as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Price fetching
# ─────────────────────────────────────────────────────────────────────────────

def fetch_latest_prices() -> dict:
    """
    Download today's closing prices from Yahoo Finance for all 5 instruments.

    Uses the last 5 days of data and takes the most recent closing price.
    Using period="5d" instead of a specific date is more reliable —
    it always returns the most recent available data even around weekends
    or public holidays when markets are closed.

    Returns:
        dict — e.g. {"XAU": 4492.0, "XAG": 69.54, "XPT": 1870.6, ...}
        Returns an empty dict for any ticker that fails to download.
    """
    provider = YahooFinanceMarketDataProvider()
    observations = provider.latest_observations()
    prices = validate_strategy_observations(observations)
    return decimal_prices_to_float_dict(prices)


# ─────────────────────────────────────────────────────────────────────────────
# CSV management
# ─────────────────────────────────────────────────────────────────────────────

def update_prices_csv(prices: dict) -> pd.DataFrame:
    """
    Append today's prices to the historical CSV file.

    If today's date is already in the file (e.g. running --now twice in one day),
    the append is skipped to avoid duplicate rows.

    Parameters:
        prices : dict of today's prices from fetch_latest_prices()

    Returns:
        The updated DataFrame (needed immediately for ratio calculation).
    """
    df = pd.read_csv(CSV_PATH, index_col="Date", parse_dates=True)
    today = pd.Timestamp(business_now().date())

    if today in df.index:
        logger.info("  ℹ️  Today's date already in CSV — skipping append.")
        return df

    # Create a single-row DataFrame for today and append it
    new_row = pd.DataFrame([prices], index=[today])
    new_row.index.name = "Date"
    df = pd.concat([df, new_row])
    df.to_csv(CSV_PATH)

    logger.info(f"  ✅ Prices appended to {CSV_PATH}")
    return df


def persist_validated_market_prices(
    observations: dict,
    prices: dict,
    *,
    session_factory=None,
) -> str:
    """Share a validated provider result with the backend through its database."""

    from services.market_data_service import store_validated_market_prices

    if session_factory is None:
        from database import SessionLocal

        session_factory = SessionLocal

    source_timestamp = max(
        observation.source_timestamp for observation in observations.values()
    )
    retrieved_at = max(observation.retrieved_at for observation in observations.values())
    sources = {observation.source for observation in observations.values()}
    source = next(iter(sources)) if len(sources) == 1 else ",".join(sorted(sources))

    db = session_factory()
    try:
        database_dialect = db.get_bind().dialect.name
        store_validated_market_prices(
            db,
            prices=prices,
            source_timestamp=source_timestamp,
            retrieved_at=retrieved_at,
            source=source,
        )
        return database_dialect
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def refresh_persisted_market_snapshot(*, session_factory=None) -> None:
    """Fetch, validate, and persist a snapshot independently of strategy state."""

    logger.info("Refreshing persisted market snapshot...")
    provider = YahooFinanceMarketDataProvider()
    observations = provider.latest_observations()
    decimal_prices = validate_strategy_observations(observations)
    database_dialect = persist_validated_market_prices(
        observations,
        decimal_prices,
        session_factory=session_factory,
    )
    source_timestamp = max(
        observation.source_timestamp for observation in observations.values()
    )
    logger.info(
        "Persisted validated market snapshot. source_timestamp=%s instruments=%s database=%s",
        source_timestamp.isoformat(),
        ",".join(sorted(decimal_prices)),
        database_dialect,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Daily cycle
# ─────────────────────────────────────────────────────────────────────────────

def run_daily_cycle() -> int:
    """Run the retained accountless subscriber signal cycle.

    This compatibility wrapper intentionally no longer contains any broker,
    order, portfolio, or legacy customer execution branch.
    """
    return run_subscriber_signal_cycle()


def run_subscriber_signal_cycle() -> int:
    """
    Run the accountless subscriber signal cycle.

    This path uses the same authoritative price, ratio, and hysteresis logic as
    the legacy cycle, but it never calls broker execution. Confirmed decisions
    become canonical subscriber signals and durable publication work.
    """
    logger.info("=" * 60)
    logger.info("AURORATIO — SUBSCRIBER SIGNAL CYCLE")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    config = load_config()
    logger.info("[1/5] Fetching latest market observations...")
    provider = YahooFinanceMarketDataProvider()
    observations = provider.latest_observations()
    decimal_prices = validate_strategy_observations(observations)
    prices = decimal_prices_to_float_dict(decimal_prices)

    try:
        persist_validated_market_prices(observations, decimal_prices)
    except Exception:
        # Market display persistence is deliberately isolated from the existing
        # signal/publication workflow so an operational write failure cannot
        # change strategy behavior.
        logger.exception("Could not persist validated market prices")

    logger.info("[2/5] Updating price history...")
    df = update_prices_csv(prices)

    logger.info("[3/5] Evaluating confirmed strategy decisions...")
    state = load_state()
    source_timestamp = max(
        observation.source_timestamp for observation in observations.values()
    )
    decision_date = df.index[-1].date()
    updated_state, decisions, ratios = evaluate_confirmed_strategy_decisions(
        df,
        state=state,
        config=config,
        decision_date=decision_date,
        source_data_timestamp=source_timestamp,
    )
    if not decisions:
        save_state(updated_state)
        logger.info("  ✅ No confirmed subscriber signals.")
        return 0

    logger.info("[4/5] Persisting subscriber signals and publication work...")
    db_path = os.path.join(BACKEND_DIR, "auroratio.db")
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{db_path}")
    from database import SessionLocal
    from services.strategy_signal_bridge_service import ingest_confirmed_strategy_decision

    published = 0
    db = SessionLocal()
    try:
        for decision in decisions:
            result = ingest_confirmed_strategy_decision(db, candidate=decision)
            ratio_value = float(ratios[decision.ratio_identifier])
            updated_state = record_switch(
                updated_state,
                decision.module,
                decision.from_metal,
                decision.to_metal,
                decision.ratio_identifier,
                ratio_value,
                decision.decision_date.isoformat(),
            )
            logger.info(
                "  ✅ %s %s persisted as signal %s",
                decision.ratio_identifier,
                decision.decision_type,
                result.signal_id,
            )
            published += 1
    finally:
        db.close()

    save_state(updated_state)
    logger.info("[5/5] Processing due signal publications immediately...")
    try:
        from services.subscriber_signal_publication_service import (
            SIGNAL_PUBLICATION_MAX_LIMIT,
            process_due_signal_publications,
        )

        total_processed = 0
        total_published = 0
        # Drain all work that is due now in bounded service-level batches. Retryable
        # failures receive a future next_attempt_at and are left for the periodic CLI
        # worker, so this loop does not busy-retry provider failures.
        for _ in range(10):
            result = asyncio.run(
                process_due_signal_publications(
                    limit=SIGNAL_PUBLICATION_MAX_LIMIT,
                    now=datetime.now(timezone.utc),
                )
            )
            total_processed += result.processed
            total_published += result.published
            if result.processed < SIGNAL_PUBLICATION_MAX_LIMIT:
                break
        logger.info(
            "  ✅ Immediate publication pass complete: processed=%s published=%s",
            total_processed,
            total_published,
        )
    except Exception:
        # Signal rows and durable publication work are already committed. A provider
        # outage must not erase the strategy decision; the periodic publication CLI
        # worker remains the retry/fallback path.
        logger.exception(
            "Immediate signal publication failed; durable worker will retry due work"
        )

    return published


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler
# ─────────────────────────────────────────────────────────────────────────────

def start_scheduler(backtest: bool = False):
    """Run the strategy once each weekday at 17:05 Europe/Paris.

    The scheduler uses an explicit IANA timezone instead of the host machine's
    local timezone, so summer/winter DST changes cannot shift the strategy run.
    If the process starts after 17:05 on a weekday and today's row is missing,
    one catch-up run is attempted.
    """
    run_label = f"{STRATEGY_RUN_HOUR:02d}:{STRATEGY_RUN_MINUTE:02d}"
    print(
        f"Scheduler started. Will run every weekday at {run_label} "
        f"{BUSINESS_TIMEZONE}."
    )
    print("Press Ctrl+C to stop.\n")

    if not os.path.exists(CSV_PATH):
        logger.info("No price data found — running initial download...")
        from download_data import download_full
        download_full(backtest=backtest)

    # A fresh deployment may download a CSV that already contains today's row.
    # The strategy guard below correctly avoids a duplicate decision cycle, but
    # market persistence must not depend on that filesystem-only guard.
    try:
        refresh_persisted_market_snapshot()
    except Exception:
        logger.exception(
            "Startup market snapshot refresh failed; scheduled strategy remains active"
        )

    last_attempted_date = None

    while True:
        now_local = business_now()
        run_date = now_local.date()
        scheduled_time_reached = (now_local.hour, now_local.minute) >= (
            STRATEGY_RUN_HOUR,
            STRATEGY_RUN_MINUTE,
        )

        if (
            now_local.weekday() <= 4
            and scheduled_time_reached
            and last_attempted_date != run_date
        ):
            try:
                df = pd.read_csv(CSV_PATH, index_col="Date", parse_dates=True)
                today = pd.Timestamp(run_date)
                if today in df.index:
                    logger.info(
                        "Today's strategy price row already exists — no duplicate cycle needed."
                    )
                else:
                    logger.info(
                        "Running scheduled subscriber signal cycle for %s at %s.",
                        run_date.isoformat(),
                        now_local.strftime("%H:%M:%S %Z"),
                    )
                    run_subscriber_signal_cycle()
            except FileNotFoundError:
                logger.warning(
                    "prices_clean.csv not found — running subscriber signal cycle now."
                )
                run_subscriber_signal_cycle()
            except Exception:
                logger.exception("Scheduled subscriber signal cycle failed")
            finally:
                # One strategy attempt per business day. Durable publication retries
                # are handled independently by process_signal_publications.
                last_attempted_date = run_date

        time.sleep(30)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AuroRatio Daily Scheduler")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run the daily cycle immediately instead of waiting for 17:05"
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="On first download, use backtest end_date from config.yaml instead of today"
    )
    args = parser.parse_args(argv)

    if args.now:
        # Check if price data exists, download if missing
        if not os.path.exists(CSV_PATH):
            logger.info("No price data found — running initial download...")
            from download_data import download_full
            download_full(backtest=args.backtest)
        run_subscriber_signal_cycle()
        
    else:
        start_scheduler(backtest=args.backtest)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
