"""Rollierende Volatilität und Kovarianz (nur Vergangenheit) für die Risk Engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.timeframes import periods_per_year, tf_seconds


class RiskStats:
    """Vorberechnete, annualisierte Volatilität und Kovarianz je Kerze.

    Wert bei Index i nutzt nur Renditen bis einschließlich Kerze i.
    """

    def __init__(self, closes: dict[str, pd.Series], timeframe: str, lookback_days: int) -> None:
        self.symbols = list(closes)
        ppy = periods_per_year(timeframe)
        window = max(10, int(lookback_days * 86400 / tf_seconds(timeframe)))
        rets = pd.DataFrame({s: np.log(c).diff() for s, c in closes.items()})
        self.index = rets.index
        self.vol = {s: (rets[s].rolling(window, min_periods=window // 2).std() * np.sqrt(ppy)).values
                    for s in self.symbols}
        self.cov: dict[tuple[str, str], np.ndarray] = {}
        for a_i, a in enumerate(self.symbols):
            for b in self.symbols[a_i:]:
                c = rets[a].rolling(window, min_periods=window // 2).cov(rets[b]) * ppy
                self.cov[(a, b)] = self.cov[(b, a)] = c.values

    def volatility(self, symbol: str, i: int) -> float:
        v = self.vol[symbol][i]
        return float(v) if np.isfinite(v) and v > 0 else float("nan")

    def covariance(self, i: int, symbols: list[str]) -> np.ndarray | None:
        m = np.array([[self.cov[(a, b)][i] for b in symbols] for a in symbols], dtype=float)
        return m if np.isfinite(m).all() else None

    def correlation(self, i: int, a: str, b: str) -> float:
        c = self.cov[(a, b)][i]
        va, vb = self.cov[(a, a)][i], self.cov[(b, b)][i]
        return float(c / np.sqrt(va * vb)) if va > 0 and vb > 0 else float("nan")
