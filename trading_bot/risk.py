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
    cap = min(cash * risk.position_fraction, risk.max_order_value, cash)
    if risk.sizing == "risk":
        dist = stop_distance(price, risk, atr) if price else None
        if not dist:
            return 0.0  # ohne Stop kein Risiko berechenbar -> nicht handeln
        value = cash * risk.risk_per_trade * price / dist
        cap = min(cap, value)
    return cap if cap >= risk.min_order_value else 0.0


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
