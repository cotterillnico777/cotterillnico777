"""Ausführung von Orders: simuliert (Paper) oder echt über ccxt (Live)."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

log = logging.getLogger(__name__)


@dataclass
class Fill:
    side: str
    amount: float  # Base-Menge (z. B. BTC)
    price: float  # Durchschnittspreis
    # Netto-Änderung des Quote-Guthabens inkl. Gebühren:
    # negativ bei Käufen (ausgegeben), positiv bei Verkäufen (erhalten)
    quote_delta: float
    fee_quote: float  # Gebühr umgerechnet in Quote-Währung (nur Info)
    order_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Broker(ABC):
    @abstractmethod
    def balances(self) -> tuple[float, float]:
        """Freies Guthaben (base, quote)."""

    @abstractmethod
    def market_buy(self, quote_value: float, price: float) -> Fill: ...

    @abstractmethod
    def market_sell(self, amount: float, price: float) -> Fill: ...

    def state(self) -> dict:
        return {}


class PaperBroker(Broker):
    """Spielgeld-Konto. Füllt zum aktuellen Preis plus Slippage und Gebühr."""

    def __init__(
        self,
        quote: float,
        base: float = 0.0,
        fee: float = 0.001,
        slippage: float = 0.0005,
    ) -> None:
        self.quote, self.base = quote, base
        self.fee, self.slippage = fee, slippage

    def balances(self) -> tuple[float, float]:
        return self.base, self.quote

    def market_buy(self, quote_value: float, price: float) -> Fill:
        if quote_value > self.quote + 1e-9:
            raise ValueError("Paper: nicht genug Quote-Guthaben")
        fill_price = price * (1 + self.slippage)
        fee = quote_value * self.fee
        amount = (quote_value - fee) / fill_price
        self.quote -= quote_value
        self.base += amount
        return Fill("buy", amount, fill_price, -quote_value, fee, "paper")

    def market_sell(self, amount: float, price: float) -> Fill:
        amount = min(amount, self.base)
        fill_price = price * (1 - self.slippage)
        gross = amount * fill_price
        fee = gross * self.fee
        self.base -= amount
        self.quote += gross - fee
        return Fill("sell", amount, fill_price, gross - fee, fee, "paper")

    def state(self) -> dict:
        return {"base": self.base, "quote": self.quote}


def create_exchange(exchange_id: str, sandbox: bool = False, with_keys: bool = False):
    """ccxt-Exchange-Objekt erzeugen. API-Schlüssel kommen nur aus Umgebungsvariablen."""
    import ccxt

    if not hasattr(ccxt, exchange_id):
        raise ValueError(f"ccxt kennt die Börse '{exchange_id}' nicht")
    opts: dict = {"enableRateLimit": True}
    if with_keys:
        key = os.environ.get("TRADING_BOT_API_KEY")
        secret = os.environ.get("TRADING_BOT_API_SECRET")
        if not key or not secret:
            raise RuntimeError(
                "Für Live-Trading TRADING_BOT_API_KEY und TRADING_BOT_API_SECRET setzen "
                "(z. B. in der Datei .env)"
            )
        opts.update(apiKey=key, secret=secret)
        if os.environ.get("TRADING_BOT_API_PASSWORD"):
            opts["password"] = os.environ["TRADING_BOT_API_PASSWORD"]
    exchange = getattr(ccxt, exchange_id)(opts)
    if sandbox:
        exchange.set_sandbox_mode(True)
    exchange.load_markets()
    return exchange


class LiveBroker(Broker):
    """Echte Market-Orders über ccxt (nur Spot)."""

    def __init__(self, exchange, symbol: str) -> None:
        self.ex = exchange
        self.symbol = symbol
        self.market = exchange.market(symbol)
        if not self.market.get("spot", True):
            raise ValueError(f"{symbol} ist kein Spot-Markt; nur Spot wird unterstützt")
        self.base_ccy, self.quote_ccy = self.market["base"], self.market["quote"]

    def balances(self) -> tuple[float, float]:
        bal = self.ex.fetch_balance()
        free = bal.get("free", {})
        return float(free.get(self.base_ccy) or 0.0), float(free.get(self.quote_ccy) or 0.0)

    def _min_cost(self) -> float:
        return float(((self.market.get("limits") or {}).get("cost") or {}).get("min") or 0.0)

    def market_buy(self, quote_value: float, price: float) -> Fill:
        if quote_value < self._min_cost():
            raise ValueError(f"Order {quote_value:.2f} unter Börsenminimum {self._min_cost()}")
        if self.ex.has.get("createMarketBuyOrderWithCost"):
            order = self.ex.create_market_buy_order_with_cost(
                self.symbol, float(self.ex.cost_to_precision(self.symbol, quote_value))
            )
        else:
            amount = float(self.ex.amount_to_precision(self.symbol, quote_value / price))
            order = self.ex.create_order(self.symbol, "market", "buy", amount)
        return self._to_fill(order, "buy", price)

    def market_sell(self, amount: float, price: float) -> Fill:
        base_free, _ = self.balances()
        amount = float(self.ex.amount_to_precision(self.symbol, min(amount, base_free)))
        if amount <= 0:
            raise ValueError("Keine verkaufbare Menge vorhanden")
        order = self.ex.create_order(self.symbol, "market", "sell", amount)
        return self._to_fill(order, "sell", price)

    def _to_fill(self, order: dict, side: str, price_hint: float) -> Fill:
        oid = str(order.get("id", ""))
        # Viele Börsen liefern Füllinformationen erst beim erneuten Abruf
        if not order.get("filled") and oid and self.ex.has.get("fetchOrder"):
            try:
                order = self.ex.fetch_order(oid, self.symbol)
            except Exception as exc:  # noqa: BLE001
                log.warning("fetch_order fehlgeschlagen: %s", exc)
        filled = float(order.get("filled") or order.get("amount") or 0.0)
        avg = float(order.get("average") or order.get("price") or price_hint)
        cost = float(order.get("cost") or filled * avg)
        fee_quote = 0.0
        fee_paid_in_quote = 0.0
        for fee in order.get("fees") or ([order["fee"]] if order.get("fee") else []):
            if not fee or fee.get("cost") is None:
                continue
            if fee.get("currency") == self.quote_ccy:
                fee_quote += float(fee["cost"])
                fee_paid_in_quote += float(fee["cost"])
            elif fee.get("currency") == self.base_ccy:
                fee_quote += float(fee["cost"]) * avg
                if side == "buy":
                    filled -= float(fee["cost"])
        if filled <= 0:
            raise RuntimeError(f"Order {oid} wurde nicht ausgeführt: {order.get('status')}")
        quote_delta = -(cost + fee_paid_in_quote) if side == "buy" else cost - fee_paid_in_quote
        return Fill(side, filled, avg, quote_delta, fee_quote, oid)
