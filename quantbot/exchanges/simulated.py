"""Simulierte Börse für Paper Trading.

Marktdaten kommen von einer echten Datenquelle (z. B. CCXTFuturesAdapter ohne Schlüssel).
Orders, Positionen, Gebühren, Funding und Liquidation laufen über dasselbe ``Account``-Modell
wie der Backtest. Dadurch unterscheidet sich Paper von Live nur im Adapter, nicht in der Logik.

Für Tests lassen sich Fehler einspeisen: Timeouts (vor/nach Annahme), Ablehnungen,
Teilausführungen.
"""

from __future__ import annotations

import itertools
from dataclasses import replace

from ..backtesting.costs import CostModel
from ..core.types import Balance, Order, OrderStatus, OrderType, PositionSnapshot, Side
from ..portfolio.account import Account
from .base import ExchangeAdapter, ExchangeError, ExchangeUnavailable


class SimulatedExchange(ExchangeAdapter):
    name = "paper"

    def __init__(self, market: ExchangeAdapter | None, costs: CostModel, initial_equity: float,
                 mmr: dict[str, float]) -> None:
        self.market = market
        self.costs = costs
        self.account = Account(cash=initial_equity, mmr=dict(mmr))
        self.orders: dict[str, Order] = {}
        self.last_price: dict[str, float] = {}
        self.funding_by_symbol: dict[str, float] = {}
        self.leverage: dict[str, float] = {}
        self.fault_queue: list[str] = []  # "timeout_before", "timeout_after", "reject", "partial"
        self._ids = itertools.count(1)
        self.fills: list[dict] = []

    # ------------------------------------------------------------ Marktdaten
    def get_ohlcv(self, symbol, timeframe, since=None, limit=500):
        return self.market.get_ohlcv(symbol, timeframe, since=since, limit=limit)

    def get_funding_history(self, symbol, since=None, limit=1000):
        return self.market.get_funding_history(symbol, since=since, limit=limit)

    def get_ticker_price(self, symbol):
        if self.market is not None:
            p = self.market.get_ticker_price(symbol)
            self.last_price[symbol] = p
            return p
        return self.last_price[symbol]

    def set_price(self, symbol: str, price: float) -> None:
        self.last_price[symbol] = price

    # ------------------------------------------------------------------ Konto
    def get_balance(self):
        eq = self.account.equity({s: self.last_price.get(s, p.avg_price) for s, p in self.account.positions.items()})
        used = sum(p.notional(self.last_price.get(s, p.avg_price)) / max(self.leverage.get(s, 1.0), 1.0)
                   for s, p in self.account.positions.items() if p.qty)
        return Balance(equity=eq, free=eq - used)

    def get_positions(self):
        out = []
        prices = {s: self.last_price.get(s, p.avg_price) for s, p in self.account.positions.items()}
        for s, p in self.account.positions.items():
            if p.qty:
                out.append(PositionSnapshot(s, p.qty, p.avg_price, p.unrealized(prices[s]),
                                            self.leverage.get(s), self.account.liquidation_price(s, prices)))
        return out

    def set_leverage(self, symbol, leverage):
        self.leverage[symbol] = float(leverage)

    # ----------------------------------------------------------------- Orders
    def place_order(self, order: Order) -> Order:
        fault = self.fault_queue.pop(0) if self.fault_queue else None
        if fault == "timeout_before":
            raise ExchangeUnavailable("simulierter Timeout (Order nicht angekommen)")
        if order.client_id in self.orders:  # Idempotenz: gleiche client_id = gleiche Order
            return replace(self.orders[order.client_id])
        if fault == "reject":
            raise ExchangeError("simulierte Ablehnung")
        o = replace(order)
        o.exchange_id = f"sim-{next(self._ids)}"
        pos = self.account.position(o.symbol).qty
        if o.reduce_only:
            sign = 1 if o.side is Side.BUY else -1
            if pos == 0 or (pos > 0) == (sign > 0):
                o.status = OrderStatus.REJECTED
                o.error = "reduce_only ohne passende Position"
                self.orders[o.client_id] = o
                raise ExchangeError(o.error)
            o.qty = min(o.qty, abs(pos))
        if o.type is OrderType.MARKET:
            ratio = 0.5 if fault == "partial" else 1.0
            self._fill(o, o.qty * ratio, self._market_price(o))
            o.status = OrderStatus.FILLED if ratio == 1.0 else OrderStatus.CANCELED  # Rest verfällt (IOC)
        else:
            o.status = OrderStatus.OPEN
        self.orders[o.client_id] = o
        if fault == "timeout_after":
            raise ExchangeUnavailable("simulierter Timeout (Order wurde aber ausgeführt)")
        return replace(o)

    def cancel_order(self, symbol, client_id):
        o = self.orders.get(client_id)
        if o is None:
            raise ExchangeError("Order unbekannt")
        if not o.status.is_final:
            o.status = OrderStatus.CANCELED

    def get_order(self, symbol, client_id):
        o = self.orders.get(client_id)
        return replace(o) if o else None

    def get_open_orders(self, symbol=None):
        return [replace(o) for o in self.orders.values()
                if o.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED) and (symbol is None or o.symbol == symbol)]

    # ------------------------------------------------------------- Simulation
    def _market_price(self, o: Order) -> float:
        px = self.get_ticker_price(o.symbol) if self.market else self.last_price[o.symbol]
        side = 1 if o.side is Side.BUY else -1
        return self.costs.fill_price(px, side, px, px)

    def _fill(self, o: Order, qty: float, price: float, maker: bool = False) -> None:
        if qty <= 0:
            return
        signed = qty if o.side is Side.BUY else -qty
        fee = self.costs.fee(qty * price, maker)
        self.account.apply_fill(o.symbol, signed, price, fee)
        o.avg_price = ((o.avg_price or 0.0) * o.filled_qty + price * qty) / (o.filled_qty + qty)
        o.filled_qty += qty
        o.fee += fee
        self.fills.append({"client_id": o.client_id, "symbol": o.symbol, "side": o.side.value,
                           "qty": qty, "price": price, "fee": fee})

    def process_bar(self, symbol: str, high: float, low: float, close: float) -> list[Order]:
        """Stop-/Take-Profit-Orders gegen Hoch/Tief prüfen (seit letzter Prüfung). Stop zuerst."""
        self.last_price[symbol] = close
        triggered = []
        opens = [o for o in self.orders.values()
                 if o.symbol == symbol and o.status is OrderStatus.OPEN and o.stop_price is not None]
        opens.sort(key=lambda o: 0 if o.type is OrderType.STOP_MARKET else 1)
        for o in opens:
            pos = self.account.position(symbol).qty
            if pos == 0 and o.reduce_only:
                o.status = OrderStatus.CANCELED
                continue
            sell = o.side is Side.SELL
            if o.type is OrderType.STOP_MARKET:
                hit = low <= o.stop_price if sell else high >= o.stop_price
                ref = min(o.stop_price, close) if sell and close < o.stop_price else \
                    max(o.stop_price, close) if not sell and close > o.stop_price else o.stop_price
                price = self.costs.fill_price(ref, -1 if sell else 1, ref, ref)
            else:
                hit = high >= o.stop_price if sell else low <= o.stop_price
                price = o.stop_price
            if hit:
                qty = min(o.qty, abs(pos)) if o.reduce_only else o.qty
                self._fill(o, qty, price)
                o.status = OrderStatus.FILLED
                triggered.append(replace(o))
        return triggered

    def apply_funding(self, symbol: str, rate: float, price: float) -> float:
        paid = self.account.apply_funding(symbol, rate, price)
        self.funding_by_symbol[symbol] = self.funding_by_symbol.get(symbol, 0.0) + paid
        return paid

    def check_liquidation(self, worst: dict[str, float]) -> bool:
        prices = {**self.last_price, **worst}
        if self.account.liquidation_check(prices):
            for s in list(self.account.open_symbols()):
                p = self.account.positions[s]
                self.account.apply_fill(s, -p.qty, prices[s], abs(p.qty) * prices[s] * self.costs.liquidation_fee)
            self.account.liquidated = True
            return True
        return False

    # ------------------------------------------------------------ Persistenz
    def to_state(self) -> dict:
        import dataclasses

        return {
            "cash": self.account.cash,
            "fees_paid": self.account.fees_paid,
            "funding_paid": self.account.funding_paid,
            "positions": {s: [p.qty, p.avg_price] for s, p in self.account.positions.items() if p.qty},
            "orders": {cid: {**dataclasses.asdict(o), "side": o.side.value, "type": o.type.value,
                             "status": o.status.value}
                       for cid, o in self.orders.items()},
            "funding_by_symbol": self.funding_by_symbol,
            "last_price": self.last_price,
        }

    def load_state(self, st: dict) -> None:
        from ..portfolio.account import Position

        self.account.cash = st["cash"]
        self.account.fees_paid = st.get("fees_paid", 0.0)
        self.account.funding_paid = st.get("funding_paid", 0.0)
        self.account.positions = {s: Position(s, q, a) for s, (q, a) in st["positions"].items()}
        self.orders = {}
        for cid, d in st["orders"].items():
            d = dict(d)
            d["side"], d["type"], d["status"] = Side(d["side"]), OrderType(d["type"]), OrderStatus(d["status"])
            self.orders[cid] = Order(**d)
        self.funding_by_symbol = dict(st.get("funding_by_symbol", {}))
        self.last_price = dict(st.get("last_price", {}))
        self._ids = itertools.count(len(self.orders) + 1)
