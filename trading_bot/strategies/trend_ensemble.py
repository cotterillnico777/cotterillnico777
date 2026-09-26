"""Trendfolge-Ensemble: Donchian-Ausbrüche über drei Zeiträume.

Jeder Zeitraum ist ein eigenes kleines Trendsystem (Turtle-Prinzip):
  - Einstieg, wenn der Schluss über dem höchsten Hoch der letzten N Kerzen liegt
  - Ausstieg, wenn der Schluss unter dem tiefsten Tief der letzten N × exit_ratio Kerzen fällt
Das Signal ist der Anteil der Systeme, die long sind: 0, 1/3, 2/3 oder 1.
So wird schrittweise ein- und ausgestiegen, und kein einzelner Zeitraum
entscheidet allein, was robuster ist als ein einzelnes Parameterpaar.

Mit ``kind: sma`` wird statt Donchian "Schluss über SMA(N)" verwendet.
"""

from __future__ import annotations

import pandas as pd

from ..indicators import donchian, sma
from ._util import hold_between
from .base import Strategy


class TrendEnsemble(Strategy):
    """Ensemble aus drei Trendsystemen, Signal = Anteil der Systeme im Aufwärtstrend."""

    name = "trend_ensemble"
    # Voreinstellung für Tageskerzen (ca. 1, 2,5 und 5 Monate).
    # Für 4h-Kerzen etwa × 6 wählen (z. B. 120 / 330 / 600).
    default_params = {"short": 20, "mid": 55, "long": 100, "exit_ratio": 0.5, "kind": "donchian"}
    param_grid = {
        "short": [10, 20, 30],
        "mid": [40, 55, 70],
        "long": [90, 120, 150],
        "exit_ratio": [0.5],
        "kind": ["donchian", "sma"],
    }

    def validate(self) -> None:
        p = self.params
        if not 2 <= p["short"] < p["mid"] < p["long"]:
            raise ValueError("Es muss gelten: 2 <= short < mid < long")
        if not 0 < p["exit_ratio"] <= 1:
            raise ValueError("'exit_ratio' muss in (0, 1] liegen")
        if p["kind"] not in ("donchian", "sma"):
            raise ValueError("'kind' muss 'donchian' oder 'sma' sein")

    @property
    def lookbacks(self) -> list[int]:
        return [int(self.params[k]) for k in ("short", "mid", "long")]

    @property
    def warmup(self) -> int:
        return self.lookbacks[-1] + 1

    def _system(self, df: pd.DataFrame, n: int) -> pd.Series:
        close = df["close"]
        if self.params["kind"] == "sma":
            ma = sma(close, n)
            return (close > ma).astype(int).where(ma.notna(), 0)
        upper, _ = donchian(df, n)
        _, lower = donchian(df, max(2, round(n * self.params["exit_ratio"])))
        return hold_between(close > upper, close < lower)

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        systems = [self._system(df, n) for n in self.lookbacks]
        return sum(systems) / len(systems)
