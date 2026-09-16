"""
services/snaptrade_execution_service.py

SnapTrade trading adapter.

Important:
- This replaces local IB Gateway execution for production.
- It uses SnapTrade's recommended flow: check order impact first, then place the
  checked order.
- Exact SDK method names can vary by installed snaptrade-client version. The
  helper methods below isolate SDK calls so you only change this file if your SDK
  signature differs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import logging

from snaptrade_client import SnapTrade

logger = logging.getLogger(__name__)


ETC_SYMBOLS = {
    "GOLD": "SGLN",
    "SILVER": "SSLN",
    "PLATINUM": "SPLT",
    "PALLADIUM": "SPDM",
}


@dataclass
class SnapTradeOrderResult:
    ok: bool
    order_id: str | None = None
    trade_id: str | None = None
    status: str | None = None
    error: str | None = None
    raw: Any | None = None


class SnapTradeExecutionService:
    def __init__(self, snaptrade: SnapTrade):
        self.snaptrade = snaptrade

    def _body(self, response):
        return response.body if hasattr(response, "body") else response

    def find_symbol_for_account(
        self,
        *,
        user_id: str,
        user_secret: str,
        account_id: str,
        symbol: str,
    ) -> dict:
        """
        Search for a tradable account symbol and return the raw symbol object.
        You may need to adapt the field extraction to your SnapTrade SDK version.
        """
        try:
            response = self.snaptrade.reference_data.symbol_search_user_account(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
                substring=symbol,
            )
        except AttributeError as exc:
            raise RuntimeError(
                "Your SnapTrade SDK does not expose reference_data.symbol_search_user_account. "
                "Check your installed SDK trading/reference-data method names."
            ) from exc

        body = self._body(response) or []

        for item in body:
            candidate = item.get("symbol") or item.get("raw_symbol") or item.get("ticker")
            if candidate == symbol:
                return item

        if body:
            logger.warning("Exact symbol %s not found. Using first search result: %s", symbol, body[0])
            return body[0]

        raise RuntimeError(f"No tradable SnapTrade symbol found for {symbol} in account {account_id}")

    def get_universal_symbol_id(self, symbol_obj: dict) -> str:
        for key in ["id", "universal_symbol_id", "universalSymbolId"]:
            value = symbol_obj.get(key)
            if value:
                return value

        nested = symbol_obj.get("symbol")
        if isinstance(nested, dict):
            for key in ["id", "universal_symbol_id", "universalSymbolId"]:
                value = nested.get(key)
                if value:
                    return value

        raise RuntimeError(f"Could not extract universal symbol id from SnapTrade symbol: {symbol_obj}")

    def check_order_impact(
        self,
        *,
        user_id: str,
        user_secret: str,
        account_id: str,
        action: str,
        units: int,
        universal_symbol_id: str,
        order_type: str = "Market",
        time_in_force: str = "Day",
        limit_price: float | None = None,
    ) -> dict:
        kwargs = {
            "user_id": user_id,
            "user_secret": user_secret,
            "account_id": account_id,
            "action": action.upper(),
            "order_type": order_type,
            "time_in_force": time_in_force,
            "units": units,
            "universal_symbol_id": universal_symbol_id,
        }

        if limit_price is not None:
            kwargs["price"] = limit_price

        try:
            response = self.snaptrade.trading.get_order_impact(**kwargs)
        except AttributeError as exc:
            raise RuntimeError(
                "Your SnapTrade SDK does not expose trading.get_order_impact. "
                "Upgrade snaptrade-python-sdk or adapt this wrapper."
            ) from exc

        body = self._body(response)
        if not body:
            raise RuntimeError("SnapTrade order impact returned empty response")

        return body

    def place_checked_order(
        self,
        *,
        user_id: str,
        user_secret: str,
        trade_id: str,
    ) -> dict:
        try:
            response = self.snaptrade.trading.place_order(
                user_id=user_id,
                user_secret=user_secret,
                trade_id=trade_id,
            )
        except AttributeError as exc:
            raise RuntimeError(
                "Your SnapTrade SDK does not expose trading.place_order. "
                "Upgrade snaptrade-python-sdk or adapt this wrapper."
            ) from exc

        return self._body(response)

    def place_equity_order_checked(
        self,
        *,
        user_id: str,
        user_secret: str,
        account_id: str,
        metal: str,
        action: str,
        units: int,
        order_type: str = "Market",
        limit_price: float | None = None,
    ) -> SnapTradeOrderResult:
        if units <= 0:
            return SnapTradeOrderResult(ok=False, error="Order units must be positive")

        symbol = ETC_SYMBOLS[metal]

        try:
            symbol_obj = self.find_symbol_for_account(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
                symbol=symbol,
            )
            universal_symbol_id = self.get_universal_symbol_id(symbol_obj)

            impact = self.check_order_impact(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
                action=action,
                units=units,
                universal_symbol_id=universal_symbol_id,
                order_type=order_type,
                limit_price=limit_price,
            )

            trade_id = impact.get("id") or impact.get("tradeId") or impact.get("trade_id")
            if not trade_id:
                return SnapTradeOrderResult(
                    ok=False,
                    error=f"SnapTrade impact check did not return trade id: {impact}",
                    raw=impact,
                )

            placed = self.place_checked_order(
                user_id=user_id,
                user_secret=user_secret,
                trade_id=trade_id,
            )

            order_id = placed.get("brokerage_order_id") or placed.get("order_id") or placed.get("id")
            status = placed.get("status") or placed.get("state")

            return SnapTradeOrderResult(
                ok=True,
                order_id=order_id,
                trade_id=trade_id,
                status=status,
                raw={"impact": impact, "placed": placed},
            )

        except Exception as exc:
            logger.exception("SnapTrade order failed")
            return SnapTradeOrderResult(ok=False, error=str(exc))
