from pathlib import Path

import pandas as pd


BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
PRICES_FILE = PROJECT_ROOT / "data" / "prices_clean.csv"


def load_prices(path: Path | None = None) -> pd.DataFrame:
    csv_path = path or PRICES_FILE

    if not csv_path.exists():
        raise FileNotFoundError(f"Prices file not found: {csv_path}")

    return pd.read_csv(csv_path, index_col="Date", parse_dates=True)


def compute_ratios(prices: pd.DataFrame) -> pd.DataFrame:
    invalid = prices[["XAU", "XAG", "XPT", "XPD"]].stack()
    invalid = invalid[invalid <= 0]

    if not invalid.empty:
        raise ValueError("Invalid prices <= 0 found")

    ratios = pd.DataFrame(index=prices.index)
    ratios["AU_AG"] = prices["XAU"] / prices["XAG"]
    ratios["AU_PT"] = prices["XAU"] / prices["XPT"]
    ratios["AU_PD"] = prices["XAU"] / prices["XPD"]

    return ratios


def get_latest_ratios() -> dict:
    prices = load_prices()
    ratios = compute_ratios(prices)
    latest = ratios.iloc[-1]

    return {
        "AU_AG": round(float(latest["AU_AG"]), 2),
        "AU_PT": round(float(latest["AU_PT"]), 2),
        "AU_PD": round(float(latest["AU_PD"]), 2),
        "date": str(ratios.index[-1].date()),
    }