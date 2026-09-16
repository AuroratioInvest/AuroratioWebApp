"""
download_data.py — Historical Price Data Downloader
====================================================
PURPOSE:
    Downloads 25 years of daily closing prices for Gold, Silver,
    Platinum, Palladium, and the USD/CHF exchange rate from Yahoo Finance.
    Saves two CSV files to the data/ folder:
      - prices_raw.csv   : original data with missing values intact
      - prices_clean.csv : forward-filled data (no gaps) used by the backtest

    Run this script once before running the backtest for the first time.
    You do not need to re-run it unless you want to refresh the data.

WHY YAHOO FINANCE?
    Interactive Brokers only provides ~20 years of history for Gold/Silver,
    and does not support Platinum/Palladium spot contracts at all.
    Yahoo Finance provides free historical data going back to 2000 for all
    4 metals — exactly what the backtest requires.
    This data is only used for the backtest.
    Live trading uses IB directly.

WHY FORWARD FILL (ffill)?
    Markets are closed on weekends and public holidays.
    On those days there is no new price — the last known price is carried
    forward to fill the gap. This is standard practice in backtesting and
    does not distort results, because no trades can execute on closed days.

NOTE ON DATA AVAILABILITY:
    Yahoo Finance futures data (GC=F etc.) is reliably available from
    approximately 30/08/2000 onward. The config start date of 01/01/2000
    was the client's request, but the effective start date of the backtest
    is 30/08/2000 due to this limitation.

HOW TO RUN:
    python download_data.py
"""

import yfinance as yf
import pandas as pd
import yaml
import os
import time
import argparse
from datetime import datetime, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

# --- Load configuration ---
# All settings (dates, thresholds, etc.) come from config.yaml.
# This means if the client changes a date, they only touch the config file.
with open("config.yaml") as f:
    config = yaml.safe_load(f)

start = config["backtest"]["start_date"]  # "2000-01-01"
# end is exclusive in yfinance — set to day AFTER the desired last date.
# To include 2025-12-31, we set end to 2026-01-01.
end   = config["backtest"]["end_date"]    # "2025-12-31"


# ─────────────────────────────────────────────────────────────────────────────
# Ticker definitions
# ─────────────────────────────────────────────────────────────────────────────

# Yahoo Finance ticker symbols for metal futures and the USD/CHF rate.
# The "=F" suffix means "continuous futures contract".
# GC=F = Gold continuous futures on Yahoo Finance (most liquid gold price proxy)
# SI=F = Silver continuous futures
# PL=F = Platinum continuous futures
# PA=F = Palladium continuous futures
# USDCHF=X is the spot exchange rate — used to convert values to CHF.
tickers = {
    "XAU":    "GC=F",       # Gold continuous futures
    "XAG":    "SI=F",       # Silver continuous futures
    "XPT":    "PL=F",       # Platinum continuous futures
    "XPD":    "PA=F",       # Palladium continuous futures
    "USDCHF": "USDCHF=X"    # USD to Swiss Franc exchange rate
}


# ─────────────────────────────────────────────────────────────────────────────
# Download full
# ─────────────────────────────────────────────────────────────────────────────
def download_full(backtest: bool = False):
    if backtest:
        end = config["backtest"]["end_date"] 
    else:
        end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"Downloading data from {start} to {end}...\n")

    all_data = {}  # Holds one Series per metal, indexed by date

    # --- Download each ticker one at a time ---
    for metal, ticker in tickers.items():
        print(f"Downloading {metal} ({ticker})...")
        try:
            # yf.download fetches OHLCV data (Open, High, Low, Close, Volume)
            # auto_adjust=True adjusts for splits and dividends (cleaner prices)
            # progress=False suppresses the download progress bar in the terminal
            df = yf.download(ticker, start=start, end=end,
                            auto_adjust=True, progress=False)

            if df is None or df.empty:
                print(f"  ❌ No data returned for {metal}")
            else:
                # Keep only the closing price — all we need for ratio calculation
                close = df[["Close"]].copy()
                close.columns = [metal]     # Rename "Close" → "XAU", "XAG", etc.
                close.dropna(inplace=True)  # Remove any rows with no closing price
                all_data[metal] = close
                print(f"  ✅ {len(close)} rows | "
                    f"{close.index[0].date()} to {close.index[-1].date()}")

        except Exception as e:
            print(f"  ❌ Failed {metal}: {e}")

        # 3-second delay between requests to avoid Yahoo Finance rate limiting.
        # Without this, Yahoo blocks all requests after a few rapid downloads.
        time.sleep(3)


    # ─────────────────────────────────────────────────────────────────────────────
    # Merge and save
    # ─────────────────────────────────────────────────────────────────────────────

    if not all_data:
        raise RuntimeError("No data was downloaded. Check your internet connection and try again.")

    # --- Merge all metals into a single DataFrame ---
    # pd.concat joins the DataFrames side by side (axis=1 = columns).
    # The result: one row per calendar day, one column per metal.
    # Days where some metals traded but others didn't will have NaN values.
    prices = pd.concat(all_data.values(), axis=1)
    prices.index.name = "Date"

    print(f"\nMerged dataset: {len(prices)} rows × {len(prices.columns)} columns")
    print(f"Date range    : {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"\nMissing values per column:")
    print(prices.isnull().sum().to_string())

    os.makedirs("data", exist_ok=True)

    # --- Save raw data (with gaps intact — useful for debugging) ---
    prices.to_csv("data/prices_raw.csv")
    print(f"\n✅ Saved: data/prices_raw.csv")

    # --- Forward-fill gaps and save the clean version used by the backtest ---
    # ffill(): each NaN is replaced with the last valid value.
    # Example: if Friday's price is 1800 and Saturday/Sunday have no data,
    # Saturday and Sunday both get the value 1800.
    prices_clean = prices.ffill()
    prices_clean.to_csv("data/prices_clean.csv")
    print(f"✅ Saved: data/prices_clean.csv")


    # ─────────────────────────────────────────────────────────────────────────────
    # Sanity check
    # ─────────────────────────────────────────────────────────────────────────────

    print(f"\nFirst 3 rows:")
    print(prices_clean.head(3).to_string())
    print(f"\nLast 3 rows:")
    print(prices_clean.tail(3).to_string())


# ─────────────────────────────────────────────────────────────────────────────
# Download repair
# ─────────────────────────────────────────────────────────────────────────────
def download_repair():
    """
    Repair mode — find and fill missing dates in prices_clean.csv.

    Instead of re-downloading everything, this function:
      1. Loads the existing prices_clean.csv
      2. Identifies weekdays that are missing between the first and last date
      3. Downloads only those missing dates from Yahoo Finance
      4. Merges the new data into the existing file and saves

    HOW TO RUN:
        python download_data.py --repair
    """
    path = "data/prices_clean.csv"

    if not os.path.exists(path):
        print("❌ prices_clean.csv not found. Run without --repair first.")
        return

    # Load existing data
    existing = pd.read_csv(path, index_col="Date", parse_dates=True)

    # Find weekdays that should exist but are missing
    expected = pd.bdate_range(start=existing.index.min(), end=existing.index.max())
    missing  = expected.difference(existing.index)

    if missing.empty:
        print("✅ No missing dates found. Nothing to repair.")
        return

    print(f"Found {len(missing)} missing date(s). Downloading...")

    # print(f"{len(missing)} missing dates:")
    # for d in missing:
    #     print(f"  {d.date()}  ({d.strftime('%A')})")
        
    # Download the missing range for each metal in one request
    # (one request per metal covering min→max of missing dates, then filter)
    repair_start = missing.min().date()
    repair_end   = (missing.max() + pd.Timedelta(days=1)).date()  # end is exclusive in yfinance

    all_data = {}

    for metal, ticker in tickers.items():
        print(f"Downloading {metal} ({ticker})...")
        try:
            df = yf.download(ticker, start=repair_start, end=repair_end,
                             auto_adjust=True, progress=False)

            if df is None or df.empty:
                print(f"  ❌ No data returned for {metal}")
            else:
                close = df[["Close"]].copy()
                close.columns = [metal]
                # Keep only the dates that were actually missing
                close = close[close.index.isin(missing)]
                close.dropna(inplace=True)
                if not close.empty:
                    all_data[metal] = close
                    print(f"  ✅ {len(close)} rows recovered for {metal}")
                else:
                    print(f"  ℹ️  No data available for missing dates in {metal}")

        except Exception as e:
            print(f"  ❌ Failed {metal}: {e}")

        time.sleep(3)

    if not all_data:
        print("❌ Could not recover any missing data.")
        return
    
    # Merge recovered data into one DataFrame
    recovered = pd.concat(all_data.values(), axis=1)
    recovered.index.name = "Date"

    # Combine with existing data, sort, forward-fill, and save
    combined = pd.concat([existing, recovered])
    combined = combined[~combined.index.duplicated(keep="last")]  # remove duplicates
    combined.sort_index(inplace=True)
    combined = combined.ffill()
    combined.to_csv(path)

    print(f"\n✅ Repair complete. {len(recovered)} rows added to {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair",   action="store_true")
    parser.add_argument("--backtest", action="store_true",
                        help="Download only up to backtest end_date instead of today")
    args = parser.parse_args()
    
    if args.repair:
        # repair mode
        download_repair()
    else:
        # normal full download
        download_full(backtest=args.backtest)
