"""Mean Reversion: überverkauft kaufen, überkauft verkaufen."""

from __future__ import annotations

import pandas as pd

from ..indicators import rsi
from .base import Strategy
from ._util import hold_between


class RSIReversion(Strategy):
    """Kauf bei RSI < ``oversold``, Verkauf bei RSI > ``overbought``."""

    name = "rsi_reversion"
    default_params = {"period": 14, "oversold": 30, "overbought": 70}
    param_grid = {
        "period": [7, 14, 21],
        "oversold": [20, 25, 30, 35],
        "overbought": [65, 70, 75, 80],
    }

    def validate(self) -> None:
        if not 0 < self.params["oversold"] < self.params["overbought"] < 100:
            raise ValueError("Es muss gelten: 0 < oversold < overbought < 100")

    @property
    def warmup(self) -> int:
        return int(self.params["period"]) + 1

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        r = rsi(df["close"], int(self.params["period"]))
        entries = r < self.params["oversold"]
        exits = r > self.params["overbought"]
        return hold_between(entries, exits)
