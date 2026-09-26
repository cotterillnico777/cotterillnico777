"""Risikoregeln, die sowohl im Backtest als auch im Live-Betrieb gelten."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from .config import RiskConfig


def stop_distance(price: float, risk: RiskConfig, atr: float | None) -> float | None:
    """Abstand des Stops unter ``price`` in Quote-Währung (None = kein Stop)."""
    if risk.stop_mode == "atr":
        if atr is None or math.isnan(atr) or atr <= 0:
            return None
        return risk.atr_multiplier * atr
    if risk.stop_loss_pct <= 0:
        return None
    return price * risk.stop_loss_pct


def stop_price(entry_price: float, risk: RiskConfig, atr: float | None = None) -> float | None:
    dist = stop_distance(entry_price, risk, atr)
    return None if dist is None else entry_price - dist


def trail_stop(
    stop: float | None, highest: float, risk: RiskConfig, atr: float | None = None
) -> float | None:
    """Trailing-Stop nachziehen. Der Stop steigt nur, er fällt nie."""
    if stop is None or not risk.trailing_stop:
        return stop
    dist = stop_distance(highest, risk, atr)
    return stop if dist is None else max(stop, highest - dist)


def position_value(
    equity: float,
    risk: RiskConfig,
    price: float | None = None,
    atr: float | None = None,
    vol: float | None = None,
) -> float:
    """Wert einer *vollen* Position (Strategiesignal 1.0) in Quote-Währung.

    ``fixed``:      position_fraction × Guthaben
    ``risk``:       so viel, dass ein Stop-Treffer risk_per_trade × Guthaben kostet
    ``vol_target``: Guthaben × target_vol / gemessene Volatilität, d. h. bei
                    60 % Marktvolatilität und 25 % Ziel rund 42 % investiert
    position_fraction und max_order_value gelten immer als Obergrenze.
    """
    value = min(equity * risk.position_fraction, risk.max_order_value)
    if risk.sizing == "risk":
        dist = stop_distance(price, risk, atr) if price else None
        if not dist:
            return 0.0  # ohne Stop kein Risiko berechenbar -> nicht handeln
        value = min(value, equity * risk.risk_per_trade * price / dist)
    elif risk.sizing == "vol_target":
        if vol is None or math.isnan(vol) or vol <= 0:
            return 0.0  # Volatilität noch unbekannt (Vorlauf)
        value = min(value, equity * risk.target_vol / vol)
    return max(value, 0.0)


def entry_order_value(
    cash: float, risk: RiskConfig, price: float | None = None, atr: float | None = None
) -> float:
    """Wie viel Quote-Währung für einen Einstieg eingesetzt wird (0 = keine Order).

    ``sizing: fixed``: position_fraction × Guthaben.
    ``sizing: risk``: so viel, dass ein Stop-Treffer ``risk_per_trade`` × Guthaben
    kostet. Bei ruhigem Markt (enger Stop) wird die Position größer, bei
    unruhigem kleiner. In beiden Fällen gelten position_fraction und
    max_order_value als Obergrenze.
    """
    cap = min(position_value(cash, risk, price, atr), cash)
    return cap if cap >= risk.min_order_value else 0.0


@dataclass
class Order:
    """Ergebnis von ``plan_rebalance``.

    action: "open" / "buy" (value = Quote-Betrag), "sell" (value = Anteil der
    Position 0..1), "close" (alles verkaufen) oder None (nichts tun).
    """

    action: str | None
    value: float = 0.0
    weight: float = 0.0  # neues Positionsgewicht nach Ausführung
    unit_value: float = 0.0  # Wert einer vollen Position (für fixed/risk)


def plan_rebalance(
    target_weight: float,
    held_weight: float,
    unit_value: float,
    current_value: float,
    equity: float,
    cash: float,
    risk: RiskConfig,
    price: float,
    atr: float | None = None,
    vol: float | None = None,
) -> Order:
    """Von der aktuellen zur gewünschten Position (Gewicht 0..1 der Strategie).

    fixed/risk: Die Größe einer vollen Position wird beim Öffnen festgelegt.
    Danach wird nur gehandelt, wenn sich das Strategiegewicht ändert (z. B.
    Ensemble 1/3 -> 2/3). Gewinner werden also nicht beschnitten.

    vol_target: Zielwert = Gewicht × Guthaben × target_vol / Volatilität. Nach-
    justiert wird erst ab ``rebalance_threshold`` relativer Abweichung.
    """
    keep = Order(None, 0.0, held_weight, unit_value)
    if target_weight <= 0:
        return Order("close", 1.0) if current_value > 0 else Order(None)

    if current_value <= 0:
        unit = position_value(equity, risk, price, atr, vol)
        value = min(unit * target_weight, cash)
        if value < risk.min_order_value or value <= 0:
            return Order(None)
        return Order("open", value, target_weight, unit)

    if risk.sizing == "vol_target":
        target = target_weight * position_value(equity, risk, price, atr, vol)
        delta = target - current_value
        if abs(delta) <= risk.rebalance_threshold * max(target, current_value):
            return keep
        if delta > 0:
            value = min(delta, cash)
            if value < risk.min_order_value:
                return keep
            return Order("buy", value, target_weight, unit_value)
        if target <= 0:
            return Order("close", 1.0)
        if -delta < risk.min_order_value:
            return keep
        return Order("sell", -delta / current_value, target_weight, unit_value)

    if abs(target_weight - held_weight) < 1e-9:
        return keep
    if target_weight > held_weight:
        value = min((target_weight - held_weight) * unit_value, cash)
        if value < risk.min_order_value:
            return keep
        return Order("buy", value, target_weight, unit_value)
    frac = (held_weight - target_weight) / held_weight
    if frac * current_value < risk.min_order_value:
        return keep
    return Order("sell", frac, target_weight, unit_value)


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


class RiskManager:
    """Prüft vor jeder Kauforder, ob sie erlaubt ist.

    Verkäufe (Ausstiege, Stop-Loss) werden nie blockiert, damit der Bot
    eine offene Position immer schließen kann.
    """

    def __init__(self, risk: RiskConfig, kill_switch_file: str | Path) -> None:
        self.risk = risk
        self.kill_switch_file = Path(kill_switch_file)

    def kill_switch_active(self) -> bool:
        return self.kill_switch_file.exists()

    def check_entry(self, order_value: float, realized_pnl_today: float) -> Decision:
        if self.kill_switch_active():
            return Decision(False, f"Kill-Switch aktiv ({self.kill_switch_file} existiert)")
        if realized_pnl_today <= -self.risk.max_daily_loss:
            return Decision(
                False,
                f"Tagesverlustlimit erreicht ({realized_pnl_today:.2f} <= "
                f"-{self.risk.max_daily_loss:.2f})",
            )
        if order_value <= 0:
            return Decision(False, "Ordergröße unter Minimum, kein Guthaben oder kein Stop berechenbar")
        if order_value > self.risk.max_order_value + 1e-9:
            return Decision(False, "Ordergröße über max_order_value")
        return Decision(True)
