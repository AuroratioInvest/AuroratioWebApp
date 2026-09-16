"""
ratios.py — Precious Metal Ratio Calculator
============================================
PURPOSE:
    Computes the 3 key ratios that drive the entire strategy:
      - AU/AG : Gold price divided by Silver price
      - AU/PT : Gold price divided by Platinum price
      - AU/PD : Gold price divided by Palladium price

WHY RATIOS AND NOT PRICES?
    The strategy does not bet on whether Gold goes up or down.
    It bets on the RELATIONSHIP between metals returning to historical norms.
    A ratio of 80 for AU/AG means 1 oz of Gold buys 80 oz of Silver.
    Historically this ratio oscillates between ~40 and ~100.
    When it hits extremes, it tends to revert — that's the edge we exploit.

WHY ARE RATIOS CALCULATED IN USD, NOT CHF?
    Because the ratio is a division of two prices in the same currency,
    the currency cancels out. Gold/Silver in USD gives the same ratio
    as Gold/Silver in CHF. No conversion needed for ratio calculation.
    CHF matters only when calculating portfolio value in francs.

THIS MODULE IS USED BY:
    - backtest.py  : computes ratios for every day in the 25-year simulation
    - scheduler.py : computes today's ratio for the daily decision
    - report.py    : reads the latest ratio for the daily report
"""

import pandas as pd
import yaml
import os


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def load_config():
    """Load settings from config.yaml."""
    with open("config.yaml") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def load_prices(path: str = None) -> pd.DataFrame:
    """
    Load the historical price data from CSV.

    Returns a DataFrame with one row per trading day and columns:
    XAU (Gold), XAG (Silver), XPT (Platinum), XPD (Palladium), USDCHF.
    The Date column becomes the index.

    Parameters:
        path : path to the clean prices CSV
    """
    if path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, "data", "prices_clean.csv")
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Ratio computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_ratios(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the 3 ratios for every row in the prices DataFrame.

    Each ratio answers: "how many ounces of the cheaper metal does
    one ounce of Gold buy today?"

    Input:  DataFrame with columns XAU, XAG, XPT, XPD
    Output: DataFrame with columns AU_AG, AU_PT, AU_PD

      AU_AG = XAU / XAG  →  Gold/Silver ratio   (normal range: ~40–100)
      AU_PT = XAU / XPT  →  Gold/Platinum ratio  (normal range: ~0.5–3)
      AU_PD = XAU / XPD  →  Gold/Palladium ratio (normal range: ~1–10)

    If either price is missing (NaN), the ratio for that day is also NaN.
    The backtest drops NaN rows before running, so missing days are harmless.
    """
    # 1. Check <= 0
    invalid = prices.stack()[prices.stack() <= 0]
    if not invalid.empty:
        raise ValueError(
            "Invalid prices (<= 0) found:\n"
            + invalid.to_string()
        )
    
    # 2. Check abnormal jumps
    pct_change = prices.iloc[-2:].pct_change().iloc[-1]
    invalid_jumps = pct_change[pct_change.abs() >= 0.5].dropna()

    if not invalid_jumps.empty:
        raise ValueError(
            f"Abnormal price jumps (≥ 50%) detected on latest data:\n"
            + (invalid_jumps * 100).round(1).to_string()
            + "\n(values shown as percentages)"
        )
    
    ratios = pd.DataFrame(index=prices.index)
    ratios["AU_AG"] = prices["XAU"] / prices["XAG"]
    ratios["AU_PT"] = prices["XAU"] / prices["XPT"]
    ratios["AU_PD"] = prices["XAU"] / prices["XPD"]
    return ratios


# ─────────────────────────────────────────────────────────────────────────────
# Latest ratios (used by scheduler and report)
# ─────────────────────────────────────────────────────────────────────────────

def get_latest_ratios() -> dict:
    """
    Return the most recent ratios as a simple dictionary.
    Used by the scheduler and report generator for the daily decision check.

    Returns:
        {
            "AU_AG": 64.59,
            "AU_PT": 2.40,
            "AU_PD": 3.22,
            "date":  "2026-03-29"
        }
    """
    prices = load_prices()
    ratios = compute_ratios(prices)
    latest = ratios.iloc[-1]  # Last row = most recent trading day
    return {
        "AU_AG": round(float(latest["AU_AG"]), 2),
        "AU_PT": round(float(latest["AU_PT"]), 2),
        "AU_PD": round(float(latest["AU_PD"]), 2),
        "date":  str(ratios.index[-1].date()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prices = load_prices()
    ratios = compute_ratios(prices)

    print(f"Ratios computed : {len(ratios)} rows")
    print(f"Date range      : {ratios.index[0].date()} to {ratios.index[-1].date()}")

    print(f"\nFirst 3 rows:")
    print(ratios.head(3).to_string())

    print(f"\nLast 3 rows:")
    print(ratios.tail(3).to_string())

    print(f"\nLatest ratios:")
    for k, v in get_latest_ratios().items():
        print(f"  {k}: {v}")
