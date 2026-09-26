"""Börsenunabhängige Schnittstelle. Strategie- und Risikologik kennen nur diese Klasse."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.types import Balance, Order, PositionSnapshot


class ExchangeError(Exception):
    """Fachlicher Fehler der Börse (z. B. Order abgelehnt). Nicht erneut versuchen."""


class ExchangeUnavailable(Exception):
    """Netzwerk/Timeout/Wartung. Wiederholung ist sinnvoll, Status danach prüfen."""


class ExchangeAdapter(ABC):
    name: str = "abstract"

    # ------------------------------------------------------------ Marktdaten
    @abstractmethod
    def get_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int = 500
    ) -> list[list[float]]:
        """Kerzen [ms, open, high, low, close, volume], aufsteigend."""

    @abstractmethod
    def get_funding_history(
        self, symbol: str, since: int | None = None, limit: int = 1000
    ) -> list[tuple[int, float]]:
        """[(ms, rate)], aufsteigend."""

    @abstractmethod
    def get_ticker_price(self, symbol: str) -> float: ...

    # ------------------------------------------------------------------ Konto
    @abstractmethod
    def get_balance(self) -> Balance: ...

    @abstractmethod
    def get_positions(self) -> list[PositionSnapshot]: ...

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: float) -> None: ...

    # ----------------------------------------------------------------- Orders
    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """Order senden. Muss die ``client_id`` an die Börse weitergeben (Idempotenz)."""

    @abstractmethod
    def cancel_order(self, symbol: str, client_id: str) -> None: ...

    @abstractmethod
    def get_order(self, symbol: str, client_id: str) -> Order | None:
        """Order über die eigene client_id finden (None = der Börse unbekannt)."""

    @abstractmethod
    def get_open_orders(self, symbol: str | None = None) -> list[Order]: ...
