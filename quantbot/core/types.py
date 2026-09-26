"""Gemeinsame Datenmodelle aller Module."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Mode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    TAKE_PROFIT_MARKET = "take_profit_market"


class OrderStatus(str, Enum):
    NEW = "new"  # lokal angelegt, noch nicht gesendet
    SUBMITTED = "submitted"  # an die Börse gesendet, Antwort offen
    OPEN = "open"  # von der Börse angenommen
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"  # z. B. Timeout: Status muss abgefragt werden

    @property
    def is_final(self) -> bool:
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )


@dataclass(frozen=True)
class Instrument:
    """Handelbarer Kontrakt (linearer USDT-Perpetual)."""

    symbol: str  # z. B. "BTC/USDT:USDT"
    base: str
    quote: str = "USDT"
    maintenance_margin_rate: float = 0.005
    min_qty: float = 0.0
    qty_step: float = 0.0
    min_notional: float = 5.0

    @property
    def key(self) -> str:
        """Kurzname für Dateien und Berichte, z. B. BTCUSDT."""
        return f"{self.base}{self.quote}"


@dataclass
class Order:
    client_id: str
    symbol: str
    side: Side
    type: OrderType
    qty: float
    price: float | None = None  # Limit-Preis
    stop_price: float | None = None  # Auslösepreis für Stop/Take-Profit
    reduce_only: bool = False
    status: OrderStatus = OrderStatus.NEW
    exchange_id: str | None = None
    filled_qty: float = 0.0
    avg_price: float | None = None
    fee: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    reason: str = ""  # entry / exit / stop / take_profit / rebalance
    error: str = ""

    @property
    def remaining(self) -> float:
        return max(self.qty - self.filled_qty, 0.0)


@dataclass
class Fill:
    order_client_id: str
    symbol: str
    side: Side
    qty: float
    price: float
    fee: float
    timestamp: str


@dataclass
class PositionSnapshot:
    symbol: str
    qty: float  # >0 long, <0 short
    entry_price: float
    unrealized_pnl: float = 0.0
    leverage: float | None = None
    liquidation_price: float | None = None


@dataclass
class Balance:
    equity: float  # Kontowert inkl. unrealisierter PnL
    free: float  # frei verfügbare Margin
    currency: str = "USDT"
    extra: dict = field(default_factory=dict)


@dataclass
class Intent:
    """Zielposition für ein Symbol, erzeugt von Strategie + Risk Engine.

    ``target_qty`` mit Vorzeichen (+ long, - short, 0 = flat). Stop/Take-Profit gelten für
    die Position nach der Ausführung. ``meta`` landet im Trade-Journal (Strategie, Version,
    Signalstärke, Regime, Einstiegsgrund, Features).
    """

    symbol: str
    target_qty: float
    stop_price: float | None = None
    take_profit: float | None = None
    reason: str = "signal"
    meta: dict = field(default_factory=dict)
