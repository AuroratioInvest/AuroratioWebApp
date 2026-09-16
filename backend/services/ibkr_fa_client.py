from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class IBKROrderResult:
    ok: bool
    order_id: str | None = None
    status: str | None = None
    filled_quantity: float | None = None
    filled_value_chf: float | None = None
    fill_price: float | None = None
    error: str | None = None
    raw: Any | None = None


class IBKRFAClient:
    """
    IBKR Financial Advisor API client.

    Production target:
    - FA / Institutional Trading Web API via OAuth

    Testing target:
    - CP Gateway + paper account

    Important:
    Exact IBKR order/confirmation behavior can vary by account, gateway mode,
    instrument, and permissions. Keep live mode blocked until fully tested.
    """

    def __init__(self):
        self.mode = os.getenv("IBKR_AUTH_MODE", "gateway").strip().lower()

        if self.mode == "oauth":
            self.base_url = os.getenv(
                "IBKR_BASE_URL",
                "https://api.ibkr.com/v1/api",
            ).rstrip("/")
        else:
            self.base_url = os.getenv(
                "IBKR_BASE_URL",
                "https://localhost:5000/v1/api",
            ).rstrip("/")

        self.timeout = int(os.getenv("IBKR_HTTP_TIMEOUT", "30"))
        self.verify_ssl = os.getenv("IBKR_VERIFY_SSL", "false").lower() == "true"
        self.oauth_token = os.getenv("IBKR_OAUTH_ACCESS_TOKEN")

        self.default_exchange = os.getenv("IBKR_DEFAULT_EXCHANGE", "SMART")
        self.default_currency = os.getenv("IBKR_DEFAULT_CURRENCY", "CHF")
        self.order_wait_timeout = int(os.getenv("IBKR_ORDER_WAIT_TIMEOUT", "90"))

    # =========================================================
    # HTTP
    # =========================================================

    def _headers(self, *, idempotency_key: str | None = None) -> dict:
        headers = {
            "Content-Type": "application/json",
        }

        if self.mode == "oauth":
            if not self.oauth_token:
                raise RuntimeError("IBKR_AUTH_MODE=oauth but IBKR_OAUTH_ACCESS_TOKEN is missing")
            headers["Authorization"] = f"Bearer {self.oauth_token}"

        # IBKR may not honor this as a true idempotency key, but keeping it
        # in headers helps observability/proxy logs and future adapters.
        if idempotency_key:
            headers["X-AuroRatio-Idempotency-Key"] = idempotency_key

        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        url = f"{self.base_url}{endpoint}"

        logger.info("IBKR request %s %s", method, url)

        response = requests.request(
            method=method,
            url=url,
            headers=self._headers(idempotency_key=idempotency_key),
            json=payload,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )

        text = response.text

        try:
            data = response.json()
        except Exception:
            data = {"raw_text": text}

        if response.status_code >= 400:
            raise RuntimeError(f"IBKR HTTP {response.status_code}: {text}")

        return data

    # =========================================================
    # HEALTH / SESSION
    # =========================================================

    def ping(self) -> dict:
        return self._request("GET", "/iserver/auth/status")

    def reauthenticate(self) -> dict:
        return self._request("POST", "/iserver/reauthenticate")

    def tickle(self) -> dict:
        return self._request("POST", "/tickle")

    # =========================================================
    # PUBLIC ORDER HELPERS USED BY fa_execution_service.py
    # =========================================================

    def sell_module_position(
        self,
        *,
        account_id: str,
        symbol: str,
        quantity: float,
        idempotency_key: str,
    ) -> IBKROrderResult:
        if quantity <= 0:
            return IBKROrderResult(
                ok=True,
                status="skipped",
                filled_quantity=0,
                filled_value_chf=0,
                raw={"message": "Quantity <= 0, sell skipped"},
            )

        submit = self.place_market_order(
            account_id=account_id,
            symbol=symbol,
            side="SELL",
            quantity=quantity,
            idempotency_key=idempotency_key,
        )

        if not submit.ok or not submit.order_id:
            return submit

        fill = self.wait_for_fill(
            account_id=account_id,
            order_id=submit.order_id,
            timeout_seconds=self.order_wait_timeout,
        )

        normalized = self.normalize_fill(fill)

        return IBKROrderResult(
            ok=True,
            order_id=submit.order_id,
            status=normalized["status"],
            filled_quantity=normalized["filled_quantity"],
            filled_value_chf=normalized["filled_value"],
            fill_price=normalized["fill_price"],
            raw={
                "submit": submit.raw,
                "fill": fill,
                "normalized": normalized,
            },
        )

    def buy_with_cash_value(
        self,
        *,
        account_id: str,
        symbol: str,
        value_chf: float,
        idempotency_key: str,
    ) -> IBKROrderResult:
        if value_chf <= 0:
            return IBKROrderResult(
                ok=False,
                error="Cannot buy with non-positive cash value",
            )

        quote = self.get_quote(symbol)

        reference_price = quote.get("ask") or quote.get("last") or quote.get("price")
        if not reference_price or reference_price <= 0:
            return IBKROrderResult(
                ok=False,
                error=f"Could not get valid quote for {symbol}: {quote}",
                raw=quote,
            )

        fee_reserve_percent = float(os.getenv("AURORATIO_FEE_RESERVE_PERCENT", "0.5"))
        usable_value = value_chf * (1 - fee_reserve_percent / 100)

        quantity = int(usable_value / float(reference_price))

        if quantity <= 0:
            return IBKROrderResult(
                ok=False,
                error=(
                    f"Calculated 0 units for {symbol}. "
                    f"value_chf={value_chf}, reference_price={reference_price}"
                ),
                raw=quote,
            )

        submit = self.place_market_order(
            account_id=account_id,
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            idempotency_key=idempotency_key,
        )

        if not submit.ok or not submit.order_id:
            return submit

        fill = self.wait_for_fill(
            account_id=account_id,
            order_id=submit.order_id,
            timeout_seconds=self.order_wait_timeout,
        )

        normalized = self.normalize_fill(fill)

        return IBKROrderResult(
            ok=True,
            order_id=submit.order_id,
            status=normalized["status"],
            filled_quantity=normalized["filled_quantity"],
            filled_value_chf=normalized["filled_value"],
            fill_price=normalized["fill_price"],
            raw={
                "quote": quote,
                "computed_quantity": quantity,
                "submit": submit.raw,
                "fill": fill,
                "normalized": normalized,
            },
        )

    # =========================================================
    # ORDERS
    # =========================================================

    def place_market_order(
        self,
        *,
        account_id: str,
        symbol: str,
        side: str,
        quantity: float,
        idempotency_key: str | None = None,
    ) -> IBKROrderResult:
        conid = self.resolve_conid(symbol)

        payload = {
            "orders": [
                {
                    "acctId": account_id,
                    "conid": conid,
                    "secType": f"{conid}:STK",
                    "cOID": idempotency_key,
                    "orderType": "MKT",
                    "side": side.upper(),
                    "quantity": int(quantity),
                    "tif": "DAY",
                    "outsideRTH": False,
                }
            ]
        }

        try:
            data = self._request(
                "POST",
                f"/iserver/account/{account_id}/orders",
                payload=payload,
                idempotency_key=idempotency_key,
            )

            logger.info("IBKR order response: %s", data)

            # Some IBKR order calls return confirmation prompts that must be confirmed.
            data = self.handle_order_reply_if_needed(data)

            order_id = self.extract_order_id(data)

            return IBKROrderResult(
                ok=True,
                order_id=order_id,
                status="submitted",
                raw=data,
            )

        except Exception as exc:
            logger.exception("IBKR market order failed")
            return IBKROrderResult(
                ok=False,
                error=str(exc),
            )

    def handle_order_reply_if_needed(self, response: Any) -> Any:
        """
        IBKR can return a reply/confirmation instead of directly accepting the order.

        Typical shape can include an id that must be confirmed through:
            /iserver/reply/{replyid}

        We handle it conservatively:
        - if a message/reply id exists, auto-confirm only if env allows it.
        """

        auto_confirm = os.getenv("IBKR_AUTO_CONFIRM_ORDER_REPLIES", "false").lower() == "true"

        reply_id = self.extract_reply_id(response)
        if not reply_id:
            return response

        if not auto_confirm:
            raise RuntimeError(
                f"IBKR returned order confirmation reply_id={reply_id}. "
                "Set IBKR_AUTO_CONFIRM_ORDER_REPLIES=true only after testing."
            )

        confirmed = self._request(
            "POST",
            f"/iserver/reply/{reply_id}",
            payload={"confirmed": True},
        )

        return confirmed

    # =========================================================
    # ORDER STATUS
    # =========================================================

    def get_live_orders(self, *, account_id: str | None = None) -> Any:
        if account_id:
            return self._request("GET", f"/iserver/account/{account_id}/orders")

        return self._request("GET", "/iserver/account/orders")

    def wait_for_fill(
        self,
        *,
        account_id: str,
        order_id: str,
        timeout_seconds: int = 90,
    ) -> dict:
        started = time.time()
        last_seen: dict | None = None

        while time.time() - started < timeout_seconds:
            orders = self.get_live_orders(account_id=account_id)

            for order in self.extract_orders_list(orders):
                candidate_ids = {
                    str(order.get("orderId")),
                    str(order.get("order_id")),
                    str(order.get("id")),
                }

                if str(order_id) in candidate_ids:
                    last_seen = order
                    status = str(order.get("status") or "").lower()

                    if status in {"filled", "submitted", "presubmitted", "pre_submitted"}:
                        return order

                    if status in {"cancelled", "canceled", "inactive", "rejected"}:
                        raise RuntimeError(f"IBKR order {order_id} ended with status={status}: {order}")

            time.sleep(2)

        raise RuntimeError(
            f"Timed out waiting for order fill: {order_id}. Last seen: {last_seen}"
        )

    # =========================================================
    # MARKET DATA / QUOTES
    # =========================================================

    def get_quote(self, symbol: str) -> dict:
        """
        Minimal quote function.

        In production, you should confirm:
        - correct conid
        - delayed vs real-time permissions
        - quote currency
        - price fields returned by your IBKR account

        For now this uses the market data snapshot endpoint shape commonly used
        by Client Portal API.
        """

        conid = self.resolve_conid(symbol)

        data = self._request(
            "GET",
            f"/iserver/marketdata/snapshot?conids={conid}&fields=31,84,86",
        )

        item = data[0] if isinstance(data, list) and data else data

        last = self.safe_float(item.get("31")) if isinstance(item, dict) else None
        bid = self.safe_float(item.get("84")) if isinstance(item, dict) else None
        ask = self.safe_float(item.get("86")) if isinstance(item, dict) else None

        price = ask or last or bid

        return {
            "symbol": symbol,
            "conid": conid,
            "last": last,
            "bid": bid,
            "ask": ask,
            "price": price,
            "raw": data,
        }

    # =========================================================
    # CONTRACTS
    # =========================================================

    def resolve_conid(self, symbol: str) -> int:
        """
        Temporary hardcoded conid map.

        VERY IMPORTANT:
        You must verify the real conids in your IBKR account before live trading.
        Different listings/exchanges/currencies can have different conids.
        """

        mapping = {
            "SGLN": int(os.getenv("IBKR_CONID_SGLN", "532640894")),
            "SSLN": int(os.getenv("IBKR_CONID_SSLN", "537505665")),
            "SPLT": int(os.getenv("IBKR_CONID_SPLT", "586241180")),
            "SPDM": int(os.getenv("IBKR_CONID_SPDM", "586241181")),
        }

        normalized = symbol.upper()

        if normalized not in mapping:
            raise RuntimeError(f"No conid mapping for {symbol}")

        return mapping[normalized]

    # =========================================================
    # NORMALIZATION HELPERS
    # =========================================================

    @staticmethod
    def extract_orders_list(response: Any) -> list[dict]:
        if isinstance(response, dict):
            orders = response.get("orders")
            if isinstance(orders, list):
                return orders

            data = response.get("data")
            if isinstance(data, list):
                return data

        if isinstance(response, list):
            return response

        return []

    @staticmethod
    def extract_order_id(response: Any) -> str:
        if isinstance(response, list) and response:
            first = response[0]
            if isinstance(first, dict):
                for key in ("order_id", "orderId", "id", "local_order_id"):
                    if first.get(key):
                        return str(first[key])

        if isinstance(response, dict):
            for key in ("order_id", "orderId", "id", "local_order_id"):
                if response.get(key):
                    return str(response[key])

            orders = response.get("orders")
            if isinstance(orders, list) and orders:
                return IBKRFAClient.extract_order_id(orders)

        raise RuntimeError(f"Could not extract IBKR order id from: {json.dumps(response, default=str)}")

    @staticmethod
    def extract_reply_id(response: Any) -> str | None:
        if isinstance(response, list) and response:
            first = response[0]
            if isinstance(first, dict):
                for key in ("id", "replyId", "reply_id"):
                    if first.get("message") and first.get(key):
                        return str(first[key])

        if isinstance(response, dict):
            for key in ("replyId", "reply_id"):
                if response.get(key):
                    return str(response[key])

            if response.get("message") and response.get("id"):
                return str(response["id"])

        return None

    @staticmethod
    def normalize_fill(order: dict) -> dict:
        status = str(order.get("status") or "unknown")

        filled_quantity = (
            IBKRFAClient.safe_float(order.get("filledQuantity"))
            or IBKRFAClient.safe_float(order.get("filled_quantity"))
            or IBKRFAClient.safe_float(order.get("cumQty"))
            or IBKRFAClient.safe_float(order.get("sizeAndFills"))
            or 0.0
        )

        fill_price = (
            IBKRFAClient.safe_float(order.get("avgPrice"))
            or IBKRFAClient.safe_float(order.get("avg_price"))
            or IBKRFAClient.safe_float(order.get("lastExecutionPrice"))
            or 0.0
        )

        filled_value = filled_quantity * fill_price if filled_quantity and fill_price else 0.0

        return {
            "status": status,
            "filled_quantity": filled_quantity,
            "fill_price": fill_price,
            "filled_value": filled_value,
            "raw": order,
        }

    @staticmethod
    def safe_float(value: Any) -> float | None:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            cleaned = (
                value.replace(",", "")
                .replace("C", "")
                .replace("P", "")
                .strip()
            )
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None

        return None