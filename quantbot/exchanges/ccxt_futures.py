"""Adapter für USDT-Perpetuals über ccxt (Standard: Binance USDⓈ-M).

API-Schlüssel kommen ausschließlich aus Umgebungsvariablen und werden nie geloggt.
Für Marktdaten sind keine Schlüssel nötig.
"""

from __future__ import annotations

import logging
import os

from ..core.types import Balance, Order, OrderStatus, OrderType, PositionSnapshot, Side
from .base import ExchangeAdapter, ExchangeError, ExchangeUnavailable

log = logging.getLogger(__name__)

_STATUS = {
    "open": OrderStatus.OPEN,
    "closed": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELED,
    "cancelled": OrderStatus.CANCELED,
    "expired": OrderStatus.EXPIRED,
    "rejected": OrderStatus.REJECTED,
}


class CCXTFuturesAdapter(ExchangeAdapter):
    def __init__(self, exchange_id: str = "binanceusdm", with_keys: bool = False, sandbox: bool = False):
        import ccxt

        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"ccxt kennt die Börse {exchange_id!r} nicht")
        opts: dict = {"enableRateLimit": True, "options": {"defaultType": "future"}}
        if with_keys:
            key, secret = os.environ.get("QUANTBOT_API_KEY"), os.environ.get("QUANTBOT_API_SECRET")
            if not key or not secret:
                raise RuntimeError("QUANTBOT_API_KEY und QUANTBOT_API_SECRET fehlen (.env)")
            opts.update(apiKey=key, secret=secret)
            if os.environ.get("QUANTBOT_API_PASSWORD"):
                opts["password"] = os.environ["QUANTBOT_API_PASSWORD"]
        self.ccxt = ccxt
        self.ex = getattr(ccxt, exchange_id)(opts)
        if sandbox:
            self.ex.set_sandbox_mode(True)
        self.name = exchange_id
        self._markets_loaded = False

    def __repr__(self) -> str:  # niemals Schlüssel ausgeben
        return f"CCXTFuturesAdapter({self.name})"

    def _call(self, fn, *args, **kwargs):
        try:
            if not self._markets_loaded:
                self.ex.load_markets()
                self._markets_loaded = True
            return fn(*args, **kwargs)
        except (self.ccxt.NetworkError, self.ccxt.ExchangeNotAvailable, self.ccxt.RequestTimeout) as exc:
            raise ExchangeUnavailable(str(exc)) from exc
        except self.ccxt.OrderNotFound:
            return None
        except self.ccxt.BaseError as exc:
            raise ExchangeError(str(exc)) from exc

    # ------------------------------------------------------------ Marktdaten
    def get_ohlcv(self, symbol, timeframe, since=None, limit=500):
        return self._call(self.ex.fetch_ohlcv, symbol, timeframe, since=since, limit=limit) or []

    def get_funding_history(self, symbol, since=None, limit=1000):
        rows = self._call(self.ex.fetch_funding_rate_history, symbol, since=since, limit=limit) or []
        return [(int(r["timestamp"]), float(r["fundingRate"])) for r in rows if r.get("fundingRate") is not None]

    def get_ticker_price(self, symbol):
        t = self._call(self.ex.fetch_ticker, symbol)
        price = t.get("last") or t.get("close")
        if not price:
            raise ExchangeUnavailable(f"Kein Preis für {symbol}")
        return float(price)

    # ------------------------------------------------------------------ Konto
    def get_balance(self):
        b = self._call(self.ex.fetch_balance)
        usdt = b.get("USDT", {}) if isinstance(b, dict) else {}
        equity = float(usdt.get("total") or 0.0)
        return Balance(equity=equity, free=float(usdt.get("free") or 0.0))

    def get_positions(self):
        out = []
        for p in self._call(self.ex.fetch_positions) or []:
            contracts = float(p.get("contracts") or 0.0)
            if not contracts:
                continue
            sign = -1.0 if p.get("side") == "short" else 1.0
            out.append(
                PositionSnapshot(
                    symbol=p["symbol"],
                    qty=sign * contracts * float(p.get("contractSize") or 1.0),
                    entry_price=float(p.get("entryPrice") or 0.0),
                    unrealized_pnl=float(p.get("unrealizedPnl") or 0.0),
                    leverage=float(p["leverage"]) if p.get("leverage") else None,
                    liquidation_price=float(p["liquidationPrice"]) if p.get("liquidationPrice") else None,
                )
            )
        return out

    def set_leverage(self, symbol, leverage):
        self._call(self.ex.set_leverage, int(max(1, round(leverage))), symbol)

    # ----------------------------------------------------------------- Orders
    def place_order(self, order: Order) -> Order:
        params: dict = {"clientOrderId": order.client_id}
        if order.reduce_only:
            params["reduceOnly"] = True
        if order.stop_price is not None:
            params["stopPrice"] = order.stop_price
        ccxt_type = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_MARKET: "STOP_MARKET",
            OrderType.TAKE_PROFIT_MARKET: "TAKE_PROFIT_MARKET",
        }[order.type]
        qty = float(self.ex.amount_to_precision(order.symbol, order.qty)) if self._markets_loaded else order.qty
        raw = self._call(
            self.ex.create_order, order.symbol, ccxt_type, order.side.value, qty, order.price, params
        )
        return self._merge(order, raw)

    def cancel_order(self, symbol, client_id):
        self._call(self.ex.cancel_order, None, symbol, {"origClientOrderId": client_id})

    def get_order(self, symbol, client_id):
        raw = self._call(self.ex.fetch_order, None, symbol, {"origClientOrderId": client_id})
        if not raw:
            return None
        o = Order(client_id=client_id, symbol=symbol, side=Side(raw["side"]), type=OrderType.MARKET,
                  qty=float(raw.get("amount") or 0))
        return self._merge(o, raw)

    def get_open_orders(self, symbol=None):
        out = []
        for raw in self._call(self.ex.fetch_open_orders, symbol) or []:
            o = Order(
                client_id=raw.get("clientOrderId") or "",
                symbol=raw["symbol"],
                side=Side(raw["side"]),
                type=OrderType.MARKET,
                qty=float(raw.get("amount") or 0),
            )
            out.append(self._merge(o, raw))
        return out

    @staticmethod
    def _merge(order: Order, raw: dict | None) -> Order:
        if not raw:
            return order
        order.exchange_id = str(raw.get("id") or order.exchange_id or "")
        order.filled_qty = float(raw.get("filled") or 0.0)
        order.avg_price = float(raw["average"]) if raw.get("average") else order.avg_price
        fee = raw.get("fee") or {}
        order.fee = float(fee.get("cost") or 0.0)
        status = _STATUS.get(str(raw.get("status")), OrderStatus.UNKNOWN)
        if status is OrderStatus.OPEN and 0 < order.filled_qty < order.qty:
            status = OrderStatus.PARTIALLY_FILLED
        order.status = status
        return order
