"""
portfolio_service.py

SnapTrade is display/read-only.
IBKR FA is execution.

This service:
- syncs real broker positions from SnapTrade for display
- exposes the AuroRatio virtual module ledger separately
- never uses SnapTrade positions to decide what each module owns
"""

from datetime import datetime, timezone
import logging
from typing import Any

import requests
from sqlalchemy.orm import Session

from models import BrokerConnection, Position, UserModulePosition

logger = logging.getLogger(__name__)

ETC_TO_METAL = {
    "SPLT": "PLATINUM",
    "SPLT.L": "PLATINUM",
    "SGLN": "GOLD",
    "SGLN.L": "GOLD",
    "SSLN": "SILVER",
    "SSLN.L": "SILVER",
    "SPDM": "PALLADIUM",
    "SPDM.L": "PALLADIUM",
}

MODULE_DISPLAY = {
    "M1": "Gold ↔ Silver",
    "M2": "Gold ↔ Platinum",
    "M3": "Gold ↔ Palladium",
}


def utc_now():
    return datetime.now(timezone.utc)


def get_currency_to_chf_rate(currency: str) -> float:
    currency = (currency or "CHF").upper()

    if currency == "CHF":
        return 1.0

    try:
        response = requests.get(
            f"https://api.frankfurter.app/latest?from={currency}&to=CHF",
            timeout=5,
        )
        if response.status_code == 200:
            rate = response.json().get("rates", {}).get("CHF")
            if rate:
                return float(rate)
    except Exception as exc:
        logger.warning("Could not fetch FX rate %s/CHF: %s", currency, exc)

    if currency == "GBP":
        return 1.06

    return 1.0


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        cleaned = (
            value.replace(",", "")
            .replace("CHF", "")
            .replace("GBP", "")
            .replace("USD", "")
            .replace("EUR", "")
            .replace("£", "")
            .replace("$", "")
            .replace("€", "")
            .strip()
        )

        if not cleaned:
            return None

        try:
            return float(cleaned)
        except ValueError:
            try:
                return float(value.replace(",", ".").strip())
            except ValueError:
                return None

    return None


def _money_to_chf(value: Any) -> float:
    if value is None:
        return 0.0

    direct = _safe_float(value)
    if direct is not None:
        return direct

    if isinstance(value, dict):
        amount = None

        for key in [
            "value",
            "amount",
            "cash",
            "total",
            "balance",
            "current",
            "market_value",
            "marketValue",
            "net_liquidation",
            "netLiquidation",
            "net_asset_value",
            "netAssetValue",
        ]:
            if value.get(key) is not None:
                amount = value.get(key)
                break

        amount_float = _safe_float(amount)

        if amount_float is None:
            return 0.0

        currency = (
            value.get("currency")
            or value.get("currency_code")
            or value.get("iso_currency_code")
            or value.get("currencyCode")
            or "CHF"
        )

        if isinstance(currency, dict):
            currency = currency.get("code") or currency.get("symbol") or "CHF"

        return amount_float * get_currency_to_chf_rate(str(currency))

    return 0.0


def _extract_broker_name(account: dict) -> str | None:
    candidates = [
        account.get("institution_name"),
        account.get("brokerage_name"),
        account.get("brokerageName"),
        account.get("name"),
        account.get("account_name"),
        account.get("accountName"),
    ]

    brokerage = account.get("brokerage")
    if isinstance(brokerage, dict):
        candidates.append(brokerage.get("name"))

    brokerage_auth = account.get("brokerage_authorization") or account.get(
        "brokerageAuthorization"
    )
    if isinstance(brokerage_auth, dict):
        brokerage_obj = brokerage_auth.get("brokerage")
        if isinstance(brokerage_obj, dict):
            candidates.append(brokerage_obj.get("name"))

    account_obj = account.get("account")
    if isinstance(account_obj, dict):
        candidates.extend(
            [
                account_obj.get("institution_name"),
                account_obj.get("brokerage_name"),
                account_obj.get("brokerageName"),
                account_obj.get("name"),
                account_obj.get("account_name"),
                account_obj.get("accountName"),
            ]
        )

        nested_auth = account_obj.get("brokerage_authorization") or account_obj.get(
            "brokerageAuthorization"
        )
        if isinstance(nested_auth, dict):
            nested_brokerage = nested_auth.get("brokerage")
            if isinstance(nested_brokerage, dict):
                candidates.append(nested_brokerage.get("name"))

    for candidate in candidates:
        if candidate:
            return str(candidate)

    return None


def _extract_total_value_chf(account: dict) -> float:
    candidate_keys = [
        "total_value",
        "totalValue",
        "net_asset_value",
        "netAssetValue",
        "net_liquidation",
        "netLiquidation",
        "market_value",
        "marketValue",
        "balance",
        "balances",
        "value",
        "amount",
    ]

    for key in candidate_keys:
        raw = account.get(key)

        value = _money_to_chf(raw)
        if value > 0:
            return value

        if isinstance(raw, dict):
            for nested_key in [
                "total",
                "value",
                "amount",
                "cash",
                "available_cash",
                "availableCash",
                "settled_cash",
                "settledCash",
                "net_liquidation",
                "netLiquidation",
                "net_asset_value",
                "netAssetValue",
                "market_value",
                "marketValue",
                "current",
            ]:
                nested_value = _money_to_chf(raw.get(nested_key))
                if nested_value > 0:
                    return nested_value

        if isinstance(raw, list):
            total = sum(_money_to_chf(item) for item in raw)
            if total > 0:
                return total

    account_obj = account.get("account")
    if isinstance(account_obj, dict):
        for key in candidate_keys:
            raw = account_obj.get(key)

            value = _money_to_chf(raw)
            if value > 0:
                return value

            if isinstance(raw, dict):
                for nested_key in [
                    "total",
                    "value",
                    "amount",
                    "cash",
                    "available_cash",
                    "availableCash",
                    "settled_cash",
                    "settledCash",
                    "net_liquidation",
                    "netLiquidation",
                    "net_asset_value",
                    "netAssetValue",
                    "market_value",
                    "marketValue",
                    "current",
                ]:
                    nested_value = _money_to_chf(raw.get(nested_key))
                    if nested_value > 0:
                        return nested_value

    return 0.0


def _extract_cash_chf(account: dict) -> float:
    total_cash = 0.0

    balances = (
        account.get("balances")
        or account.get("cash_balances")
        or account.get("cashBalances")
    )

    if isinstance(balances, list):
        for balance in balances:
            total_cash += _money_to_chf(balance)

    elif isinstance(balances, dict):
        for key in [
            "cash",
            "available_cash",
            "availableCash",
            "settled_cash",
            "settledCash",
            "total",
            "current",
            "value",
            "amount",
        ]:
            total_cash += _money_to_chf(balances.get(key))

    for key in [
        "cash",
        "available_cash",
        "availableCash",
        "settled_cash",
        "settledCash",
    ]:
        total_cash += _money_to_chf(account.get(key))

    account_obj = account.get("account")
    if isinstance(account_obj, dict):
        for key in [
            "cash",
            "available_cash",
            "availableCash",
            "settled_cash",
            "settledCash",
            "balance",
            "balances",
        ]:
            total_cash += _money_to_chf(account_obj.get(key))

    return total_cash


def _extract_symbol(position: dict) -> str | None:
    symbol_data = position.get("symbol")

    if isinstance(symbol_data, str):
        return symbol_data.upper()

    if isinstance(symbol_data, dict):
        inner_symbol = symbol_data.get("symbol")

        if isinstance(inner_symbol, str):
            return inner_symbol.upper()

        if isinstance(inner_symbol, dict):
            raw = (
                inner_symbol.get("symbol")
                or inner_symbol.get("raw_symbol")
                or inner_symbol.get("rawSymbol")
                or inner_symbol.get("ticker")
            )
            return raw.upper() if raw else None

        raw = (
            symbol_data.get("ticker")
            or symbol_data.get("raw_symbol")
            or symbol_data.get("rawSymbol")
            or symbol_data.get("symbol")
        )
        return raw.upper() if raw else None

    raw = (
        position.get("ticker")
        or position.get("raw_symbol")
        or position.get("rawSymbol")
    )
    return raw.upper() if raw else None


def _extract_units(position: dict) -> float:
    for key in ["units", "quantity", "qty"]:
        value = position.get(key)
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed

    return 0.0


def _extract_position_value_chf(position: dict) -> float:
    for key in [
        "value",
        "market_value",
        "marketValue",
        "total_value",
        "totalValue",
        "amount",
    ]:
        value = _money_to_chf(position.get(key))
        if value > 0:
            return value

    return 0.0


def _extract_price(position: dict) -> tuple[float, str]:
    price = (
        position.get("price")
        or position.get("last_price")
        or position.get("lastPrice")
        or position.get("market_price")
        or position.get("marketPrice")
        or 0
    )
    currency = (
        position.get("currency")
        or position.get("currency_code")
        or position.get("currencyCode")
        or position.get("price_currency")
        or "GBP"
    )

    if isinstance(currency, dict):
        currency = currency.get("code") or currency.get("symbol") or "GBP"

    price_float = _safe_float(price) or 0.0

    if str(currency).upper() in {"GBX", "GBP"} and price_float > 1000:
        price_float = price_float / 100

    if str(currency).upper() == "GBX":
        currency = "GBP"

    return price_float, str(currency).upper()


def get_active_display_connection(db: Session, user_id: str) -> BrokerConnection | None:
    return (
        db.query(BrokerConnection)
        .filter(BrokerConnection.user_id == user_id)
        .filter(BrokerConnection.is_active == True)
        .filter(BrokerConnection.can_display_portfolio == True)
        .order_by(BrokerConnection.connected_at.desc())
        .first()
    )


def sync_positions_from_snaptrade(db: Session, user_id: str, snaptrade) -> dict:
    logger.info("Syncing SnapTrade display positions for user %s", user_id)

    connection = get_active_display_connection(db, user_id)

    if not connection:
        logger.warning("No active display broker connection for user %s", user_id)
        return {"total_chf": 0.0, "positions": []}

    try:
        accounts = snaptrade.account_information.get_all_user_holdings(
            user_id=connection.snaptrade_user_id,
            user_secret=connection.snaptrade_user_secret,
        )

        accounts_body = accounts.body if hasattr(accounts, "body") else []
        total_value_chf = 0.0
        positions_total_chf = 0.0
        positions_data = []

        for account in accounts_body:
            if not isinstance(account, dict):
                continue

            brokerage_name = _extract_broker_name(account)

            if brokerage_name and connection.broker_name in (None, "Pending", "Unknown"):
                connection.broker_name = brokerage_name

            account_value_chf = _extract_total_value_chf(account)

            if account_value_chf <= 0:
                account_value_chf = _extract_cash_chf(account)

            total_value_chf += account_value_chf

            positions = account.get("positions", []) or []
            logger.info(
                "SnapTrade account parsed: broker=%s account_value_chf=%s positions=%s",
                brokerage_name,
                account_value_chf,
                len(positions),
            )

            for position in positions:
                if not isinstance(position, dict):
                    continue

                symbol = _extract_symbol(position)
                if not symbol:
                    continue

                normalized_symbol = symbol.upper()
                metal = ETC_TO_METAL.get(normalized_symbol)

                if not metal:
                    logger.info("Skipping non-metal SnapTrade position: %s", normalized_symbol)
                    continue

                units = _extract_units(position)
                direct_value_chf = _extract_position_value_chf(position)
                price, currency = _extract_price(position)

                if direct_value_chf > 0:
                    value_chf = direct_value_chf
                else:
                    value_chf = units * price * get_currency_to_chf_rate(currency)

                positions_total_chf += value_chf

                db_position = (
                    db.query(Position)
                    .filter(
                        Position.user_id == user_id,
                        Position.etf_symbol == normalized_symbol,
                    )
                    .first()
                )

                if db_position:
                    db_position.quantity = units
                    db_position.last_price_gbp = price if currency == "GBP" else None
                    db_position.value_chf = value_chf
                    db_position.last_synced_at = utc_now()
                else:
                    db_position = Position(
                        user_id=user_id,
                        broker_connection_id=connection.id,
                        metal=metal,
                        etf_symbol=normalized_symbol,
                        quantity=units,
                        last_price_gbp=price if currency == "GBP" else None,
                        value_chf=value_chf,
                        last_synced_at=utc_now(),
                    )
                    db.add(db_position)

                positions_data.append(
                    {
                        "metal": metal,
                        "symbol": normalized_symbol,
                        "quantity": units,
                        "price": round(price, 4),
                        "currency": currency,
                        "value_chf": round(value_chf, 2),
                    }
                )

        if total_value_chf <= 0 and positions_total_chf > 0:
            total_value_chf = positions_total_chf

        db.commit()

        return {
            "total_chf": round(total_value_chf, 2),
            "positions": positions_data,
        }

    except Exception as exc:
        db.rollback()
        logger.exception("Failed to sync SnapTrade positions: %s", exc)
        return {"total_chf": 0.0, "positions": []}


def get_virtual_module_positions(db: Session, user_id: str) -> list[dict]:
    rows = (
        db.query(UserModulePosition)
        .filter(UserModulePosition.user_id == user_id)
        .order_by(UserModulePosition.module_name.asc())
        .all()
    )

    return [
        {
            "id": row.id,
            "module_name": row.module_name,
            "display_name": MODULE_DISPLAY.get(row.module_name, row.module_name),
            "metal": row.metal,
            "etf_symbol": row.etf_symbol,
            "quantity": row.quantity,
            "value_chf": round(float(row.last_value_chf or 0), 2),
            "last_fill_price": row.last_fill_price,
            "is_enabled": row.is_enabled,
            "last_sell_order_id": row.last_sell_order_id,
            "last_buy_order_id": row.last_buy_order_id,
            "last_execution_log_id": row.last_execution_log_id,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


def build_module_display_from_ledger(
    db: Session,
    user_id: str,
    total_chf: float,
) -> dict:
    rows = (
        db.query(UserModulePosition)
        .filter(UserModulePosition.user_id == user_id)
        .order_by(UserModulePosition.module_name.asc())
        .all()
    )

    modules = {}

    fallback_value = total_chf / 3 if total_chf else 0.0

    for code in ["M1", "M2", "M3"]:
        row = next((item for item in rows if item.module_name == code), None)

        if row:
            value = float(row.last_value_chf or 0.0)
            if value <= 0 and fallback_value > 0:
                value = fallback_value

            modules[code] = {
                "code": code,
                "name": MODULE_DISPLAY.get(code, code),
                "current_metal": row.metal,
                "etf_symbol": row.etf_symbol,
                "quantity": row.quantity,
                "value_chf": round(value, 2),
                "is_enabled": row.is_enabled,
                "source": "virtual_ledger",
            }
        else:
            modules[code] = {
                "code": code,
                "name": MODULE_DISPLAY.get(code, code),
                "current_metal": "GOLD",
                "etf_symbol": "SGLN",
                "quantity": 0.0,
                "value_chf": round(fallback_value, 2),
                "is_enabled": True,
                "source": "fallback",
            }

    return modules