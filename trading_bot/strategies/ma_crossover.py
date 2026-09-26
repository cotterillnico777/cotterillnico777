"""Trendfolge: gleitende Durchschnitte kreuzen sich."""

from __future__ import annotations

import pandas as pd

from ..indicators import ema, sma
from .base import Strategy


class MACrossover(Strategy):
    """Long, solange der schnelle Durchschnitt über dem langsamen liegt."""

    name = "ma_crossover"
    default_params = {"fast": 20, "slow": 50, "kind": "ema"}
    param_grid = {
        "fast": [5, 10, 20, 30, 50],
        "slow": [50, 100, 150, 200],
        "kind": ["ema", "sma"],
    }

    def validate(self) -> None:
        if self.params["fast"] >= self.params["slow"]:
            raise ValueError("'fast' muss kleiner als 'slow' sein")
        if self.params["kind"] not in ("sma", "ema"):
            raise ValueError("'kind' muss 'sma' oder 'ema' sein")

    @property
    def warmup(self) -> int:
        return int(self.params["slow"])

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ma = ema if self.params["kind"] == "ema" else sma
        fast = ma(df["close"], int(self.params["fast"]))
        slow = ma(df["close"], int(self.params["slow"]))
        return (fast > slow).astype(int).where(slow.notna(), 0)
