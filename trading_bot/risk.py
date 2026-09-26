"""Risikoregeln, die sowohl im Backtest als auch im Live-Betrieb gelten."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import RiskConfig


def entry_order_value(cash: float, risk: RiskConfig) -> float:
    """Wie viel Quote-Währung für einen Einstieg eingesetzt wird (0 = keine Order)."""
    value = min(cash * risk.position_fraction, risk.max_order_value, cash)
    return value if value >= risk.min_order_value else 0.0


def stop_price(entry_price: float, risk: RiskConfig) -> float | None:
    if risk.stop_loss_pct <= 0:
        return None
    return entry_price * (1 - risk.stop_loss_pct)


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
            return Decision(False, "Ordergröße unter Minimum oder kein Guthaben")
        if order_value > self.risk.max_order_value + 1e-9:
            return Decision(False, "Ordergröße über max_order_value")
        return Decision(True)
