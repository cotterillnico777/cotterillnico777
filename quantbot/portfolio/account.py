"""Futures-Konto mit Cross-Margin: Positionen, realisierte PnL, Gebühren, Funding, Liquidation.

Wird vom Backtest und von der simulierten Börse (Paper) gemeinsam verwendet, damit beide
dieselbe Buchhaltung haben.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    symbol: str
    qty: float = 0.0  # >0 long, <0 short
    avg_price: float = 0.0
    stop_price: float | None = None
    take_profit: float | None = None

    @property
    def side(self) -> int:
        return int(self.qty > 0) - int(self.qty < 0)

    def notional(self, price: float) -> float:
        return abs(self.qty) * price

    def unrealized(self, price: float) -> float:
        return self.qty * (price - self.avg_price)


@dataclass
class FillResult:
    realized_pnl: float  # Kursgewinn/-verlust des geschlossenen Teils (ohne Gebühren)
    closed_qty: float  # geschlossene Menge (vorzeichenlos)
    opened_qty: float  # neu eröffnete Menge (vorzeichenlos)
    flipped: bool  # Richtung gewechselt


@dataclass
class Account:
    cash: float  # Einzahlung + realisierte PnL - Gebühren - Funding
    mmr: dict[str, float] = field(default_factory=dict)  # Maintenance Margin Rate je Symbol
    positions: dict[str, Position] = field(default_factory=dict)
    fees_paid: float = 0.0
    funding_paid: float = 0.0  # >0 = gezahlt, <0 = erhalten
    liquidated: bool = False

    def position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol)
        return self.positions[symbol]

    # ------------------------------------------------------------ Bewertung
    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(p.unrealized(prices[s]) for s, p in self.positions.items() if p.qty)

    def gross_exposure(self, prices: dict[str, float]) -> float:
        return sum(p.notional(prices[s]) for s, p in self.positions.items() if p.qty)

    def net_exposure(self, prices: dict[str, float]) -> float:
        return sum(p.qty * prices[s] for s, p in self.positions.items() if p.qty)

    def maintenance_margin(self, prices: dict[str, float]) -> float:
        return sum(p.notional(prices[s]) * self.mmr.get(s, 0.01) for s, p in self.positions.items() if p.qty)

    def open_symbols(self) -> list[str]:
        return [s for s, p in self.positions.items() if p.qty]

    # ------------------------------------------------------------ Buchungen
    def apply_fill(self, symbol: str, qty: float, price: float, fee: float) -> FillResult:
        """Ausführung verbuchen. ``qty`` mit Vorzeichen (+ kaufen, - verkaufen)."""
        qty, price, fee = float(qty), float(price), float(fee)
        if qty == 0:
            return FillResult(0.0, 0.0, 0.0, False)
        pos = self.position(symbol)
        self.cash -= fee
        self.fees_paid += fee
        realized, closed, opened, flipped = 0.0, 0.0, 0.0, False
        if pos.qty == 0 or (pos.qty > 0) == (qty > 0):
            # Eröffnen oder Aufstocken: Durchschnittspreis gewichten
            new_qty = pos.qty + qty
            pos.avg_price = (pos.avg_price * abs(pos.qty) + price * abs(qty)) / abs(new_qty)
            pos.qty = new_qty
            opened = abs(qty)
        else:
            closed = min(abs(qty), abs(pos.qty))
            realized = closed * (price - pos.avg_price) * pos.side
            self.cash += realized
            rest = pos.qty + qty
            if abs(rest) < 1e-12:
                pos.qty, pos.avg_price = 0.0, 0.0
                pos.stop_price = pos.take_profit = None
            elif (rest > 0) == (pos.qty > 0):
                pos.qty = rest  # Teilschließung, Durchschnittspreis bleibt
            else:
                # Richtungswechsel: Rest wird zur Neueröffnung
                flipped = True
                opened = abs(rest)
                pos.qty, pos.avg_price = rest, price
                pos.stop_price = pos.take_profit = None
        return FillResult(realized, closed, opened, flipped)

    def apply_funding(self, symbol: str, rate: float, price: float) -> float:
        """Funding buchen: Long zahlt bei positiver Rate, Short erhält. Gibt Zahlung zurück."""
        pos = self.positions.get(symbol)
        if not pos or not pos.qty:
            return 0.0
        payment = pos.qty * price * rate  # >0 = Konto zahlt
        self.cash -= payment
        self.funding_paid += payment
        return payment

    # ------------------------------------------------------------ Liquidation
    def liquidation_check(self, worst_prices: dict[str, float]) -> bool:
        """True, wenn das Konto zu den ungünstigsten Kursen liquidiert würde."""
        if not self.open_symbols():
            return False
        return self.equity(worst_prices) <= self.maintenance_margin(worst_prices)

    def liquidation_price(self, symbol: str, prices: dict[str, float]) -> float | None:
        """Liquidationspreis von ``symbol``, wenn sich nur dieses Symbol bewegt (Cross-Margin).

        Löst  equity(p) = mm(p)  nach p auf. None = keine Liquidation möglich (z. B. flat).
        """
        pos = self.positions.get(symbol)
        if not pos or not pos.qty:
            return None
        others_eq = self.cash + sum(
            p.unrealized(prices[s]) for s, p in self.positions.items() if p.qty and s != symbol
        )
        others_mm = sum(
            p.notional(prices[s]) * self.mmr.get(s, 0.01)
            for s, p in self.positions.items()
            if p.qty and s != symbol
        )
        m = self.mmr.get(symbol, 0.01)
        # others_eq + q (p - a) = others_mm + |q| p m
        denom = pos.qty - abs(pos.qty) * m
        if abs(denom) < 1e-15:
            return None
        p = (others_mm - others_eq + pos.qty * pos.avg_price) / denom
        return p if p > 0 else None
