# AuroRatio
Automated precious metals arbitrage bot — trades Gold/Silver/Platinum/Palladium ETCs via ratio signals. Includes 25-year backtest engine, multi-broker support via SnapTrade (IB, eToro, Fidelity and more), FastAPI backend, and React dashboard. Monitors daily Gold/Silver, Gold/Platinum, and Gold/Palladium price ratios and executes trades when ratios reach historically extreme levels — fully automated, no manual intervention required.

## Strategy

- Tracks 3 ratio pairs: AU/AG, AU/PT, AU/PD
- Signals confirmed over 2 consecutive days (hysteresis — prevents false triggers)
- Trades iShares Physical ETCs on the LSE (MiFID II compliant)
- Backtested over 25 years: **16.32% CAGR** vs 11.55% Buy & Hold Gold, **2.89x ounce multiplier**

## Architecture

```
AuroRatio/
├── Bot (Python)     — scheduler, ratio engine, hysteresis, IB execution
├── backend/         — FastAPI REST API, auth, Stripe, SnapTrade
├── frontend/        — React dashboard with live ratio charts
└── data/            — price history, backtest results (gitignored)
```

## Stack

- **Bot:** Python, yfinance, ib_insync, schedule
- **Backend:** FastAPI, SQLAlchemy, SQLite → PostgreSQL, JWT auth, rate limiting
- **Frontend:** React, TypeScript, TailwindCSS, TradingView Lightweight Charts
- **Brokers:** IB Gateway (direct) + SnapTrade (IB, eToro, Fidelity, +20 others)
- **Payments:** Stripe SEPA (subscriptions, webhooks, dunning)
- **Hosting:** Azure

## Quick Start

```bash
# Bot
pip install -r requirements.txt
python download_data.py
python scheduler.py --now

# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

See `GUIDE_DEMARRAGE.md` for full setup and deployment instructions.

## Status

- [x] Phase 1 — Bot engine (paper trading validated, real trade executed)
- [x] Phase 2 — Web platform (auth, dashboard, broker connection, payments)
- [ ] Phase 3 — Azure deployment + production go-live
