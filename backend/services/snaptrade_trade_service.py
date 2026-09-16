"""
services/snaptrade_trade_service.py

SnapTrade trading adapter for the website execution path.

This is intended for sandbox / paper-trading testing first.
It uses SnapTrade's safer order flow:
1. Get quote
2. Search/resolve tradable symbol
3. Check order impact
4. Place checked order
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging
import os
import requests

from snaptrade_client import SnapTrade

logger = logging.getLogger(__name__)

ETC_SYMBOLS = {
    "GOLD": "SGLN",
    "SILVER": "SSLN",
    "PLATINUM": "SPLT",
    "PALLADIUM": "SPDM",
}


@dataclass
class Quote:
    symbol: str
    currency: str
    bid: float | None
    ask: float | None
    last: float | None
    price: float
    raw: Any


@dataclass
class OrderResult:
    ok: bool
    action: str
    symbol: str
    units: int
    order_id: str | None = None
    trade_id: str | None = None
    status: str | None = None
    error: str | None = None
    raw: Any | None = None


class SnapTradeTradeService:
    def __init__(self, snaptrade: SnapTrade, *, base_currency: str = "CHF"):
        self.snaptrade = snaptrade
        self.base_currency = base_currency.upper()

    def _body(self, response):
        return response.body if hasattr(response, "body") else response

    def fx_rate(self, from_currency: str, to_currency: str) -> float:
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        if from_currency == to_currency:
            return 1.0
        response = requests.get(
            f"https://api.frankfurter.app/latest?from={from_currency}&to={to_currency}",
            timeout=5,
        )
        response.raise_for_status()
        return float(response.json()["rates"][to_currency])

    def _extract_quote(self, item: dict, requested_symbol: str) -> Quote:
        symbol = item.get("symbol") or item.get("ticker") or item.get("raw_symbol") or requested_symbol
        if isinstance(symbol, dict):
            symbol = symbol.get("symbol") or symbol.get("raw_symbol") or requested_symbol

        currency = (
            item.get("currency")
            or item.get("currency_code")
            or item.get("price_currency")
            or "GBP"
        )
        if isinstance(currency, dict):
            currency = currency.get("code") or currency.get("symbol") or "GBP"

        def num(*keys):
            for key in keys:
                value = item.get(key)
                if value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        pass
            return None

        bid = num("bid", "bid_price", "bidPrice")
        ask = num("ask", "ask_price", "askPrice")
        last = num("last", "last_price", "lastPrice", "price", "trade_price")

        if bid and ask and bid > 0 and ask > 0:
            price = (bid + ask) / 2
        elif last and last > 0:
            price = last
        elif ask and ask > 0:
            price = ask
        elif bid and bid > 0:
            price = bid
        else:
            raise RuntimeError(f"Quote has no valid price for {requested_symbol}: {item}")

        return Quote(
            symbol=str(symbol),
            currency=str(currency).upper(),
            bid=bid,
            ask=ask,
            last=last,
            price=float(price),
            raw=item,
        )

    def get_quote(self, *, user_id: str, user_secret: str, account_id: str, symbol: str) -> Quote:
        try:
            response = self.snaptrade.trading.get_user_account_quotes(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
                symbols=symbol,
                use_ticker=True,
            )
        except AttributeError as exc:
            raise RuntimeError(
                "Your snaptrade-client version does not expose trading.get_user_account_quotes. "
                "Upgrade snaptrade-python-sdk or adapt this wrapper."
            ) from exc

        body = self._body(response)
        if isinstance(body, dict):
            candidates = body.get("quotes") or body.get("data") or body.get("results") or [body]
        else:
            candidates = body or []

        if not candidates:
            raise RuntimeError(f"No quote returned for {symbol}")

        return self._extract_quote(candidates[0], symbol)

    def search_symbol(self, *, user_id: str, user_secret: str, account_id: str, symbol: str) -> dict:
        try:
            response = self.snaptrade.reference_data.symbol_search_user_account(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
                substring=symbol,
            )
        except AttributeError as exc:
            raise RuntimeError(
                "Your snaptrade-client version does not expose reference_data.symbol_search_user_account. "
                "Upgrade snaptrade-python-sdk or adapt this wrapper."
            ) from exc

        body = self._body(response) or []
        if isinstance(body, dict):
            body = body.get("data") or body.get("results") or [body]

        exact = []
        for item in body:
            candidate = item.get("symbol") or item.get("raw_symbol") or item.get("ticker")
            if isinstance(candidate, dict):
                candidate = candidate.get("symbol") or candidate.get("raw_symbol")
            if candidate == symbol:
                exact.append(item)

        if exact:
            return exact[0]
        if body:
            logger.warning("Exact symbol %s not found. Using first SnapTrade search result: %s", symbol, body[0])
            return body[0]
        raise RuntimeError(f"Could not find tradable symbol {symbol} for account {account_id}")

    def universal_symbol_id(self, symbol_obj: dict) -> str:
        for key in ("id", "universal_symbol_id", "universalSymbolId"):
            if symbol_obj.get(key):
                return symbol_obj[key]
        nested = symbol_obj.get("symbol")
        if isinstance(nested, dict):
            for key in ("id", "universal_symbol_id", "universalSymbolId"):
                if nested.get(key):
                    return nested[key]
        raise RuntimeError(f"Could not extract universal symbol id from {symbol_obj}")

    def check_order_impact(
        self,
        *,
        user_id: str,
        user_secret: str,
        account_id: str,
        action: str,
        universal_symbol_id: str,
        units: int,
        order_type: str,
        time_in_force: str,
        price: float | None = None,
    ) -> dict:
        kwargs = {
            "user_id": user_id,
            "user_secret": user_secret,
            "account_id": account_id,
            "action": action.upper(),
            "universal_symbol_id": universal_symbol_id,
            "units": units,
            "order_type": order_type,
            "time_in_force": time_in_force,
        }
        if price is not None:
            kwargs["price"] = price

        response = self.snaptrade.trading.get_order_impact(**kwargs)
        body = self._body(response)
        if not body:
            raise RuntimeError("SnapTrade order impact returned empty response")
        return body

    def place_checked_order(self, *, user_id: str, user_secret: str, trade_id: str) -> dict:
        # wait_to_confirm is supported in recent SDK versions.
        try:
            response = self.snaptrade.trading.place_order(
                user_id=user_id,
                user_secret=user_secret,
                trade_id=trade_id,
                wait_to_confirm=True,
            )
        except TypeError:
            response = self.snaptrade.trading.place_order(
                user_id=user_id,
                user_secret=user_secret,
                trade_id=trade_id,
            )
        return self._body(response)

    def calculate_units_for_budget(
        self,
        *,
        budget_base: float,
        quote: Quote,
        side: str,
        fee_reserve_percent: float,
        slippage_percent: float,
    ) -> tuple[int, float, float]:
        if budget_base <= 0:
            return 0, 0.0, 0.0

        fx = self.fx_rate(self.base_currency, quote.currency)
        budget_quote = budget_base * fx * (1 - fee_reserve_percent / 100)

        if side.upper() == "BUY":
            base_price = quote.ask or quote.price
            limit_price = base_price * (1 + slippage_percent / 100)
        else:
            base_price = quote.bid or quote.price
            limit_price = base_price * (1 - slippage_percent / 100)

        if limit_price <= 0:
            return 0, 0.0, 0.0

        units = int(budget_quote / limit_price)
        return units, round(limit_price, 4), budget_quote

    def place_limit_order_checked(
        self,
        *,
        user_id: str,
        user_secret: str,
        account_id: str,
        metal: str,
        action: str,
        units: int,
        limit_price: float,
    ) -> OrderResult:
        symbol = ETC_SYMBOLS[metal]
        if units <= 0:
            return OrderResult(ok=False, action=action, symbol=symbol, units=units, error="Units must be positive")

        try:
            symbol_obj = self.search_symbol(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
                symbol=symbol,
            )
            universal_symbol_id = self.universal_symbol_id(symbol_obj)
            impact = self.check_order_impact(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
                action=action,
                universal_symbol_id=universal_symbol_id,
                units=units,
                order_type="Limit",
                time_in_force="Day",
                price=limit_price,
            )
            trade_id = impact.get("id") or impact.get("tradeId") or impact.get("trade_id")
            if not trade_id:
                return OrderResult(ok=False, action=action, symbol=symbol, units=units, error=f"No trade id from impact: {impact}", raw=impact)

            placed = self.place_checked_order(user_id=user_id, user_secret=user_secret, trade_id=trade_id)
            order_id = placed.get("brokerage_order_id") or placed.get("order_id") or placed.get("id")
            status = placed.get("status") or placed.get("state")
            return OrderResult(ok=True, action=action, symbol=symbol, units=units, order_id=order_id, trade_id=trade_id, status=status, raw={"impact": impact, "placed": placed})
        except Exception as exc:
            logger.exception("SnapTrade %s order failed for %s", action, symbol)
            return OrderResult(ok=False, action=action, symbol=symbol, units=units, error=str(exc))
