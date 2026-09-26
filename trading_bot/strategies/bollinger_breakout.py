"""Ausbruch: Kurs schließt über dem oberen Bollinger-Band."""

from __future__ import annotations

import pandas as pd

from ..indicators import bollinger_bands
from .base import Strategy
from ._util import hold_between


class BollingerBreakout(Strategy):
    """Kauf bei Schluss über dem oberen Band, Verkauf unter der Mittellinie."""

    name = "bollinger_breakout"
    default_params = {"period": 20, "num_std": 2.0}

    def validate(self) -> None:
        if self.params["period"] < 2 or self.params["num_std"] <= 0:
            raise ValueError("'period' >= 2 und 'num_std' > 0 erforderlich")

    @property
    def warmup(self) -> int:
        return int(self.params["period"])

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        _, mid, upper = bollinger_bands(
            df["close"], int(self.params["period"]), float(self.params["num_std"])
        )
        entries = df["close"] > upper
        exits = df["close"] < mid
        return hold_between(entries, exits)
