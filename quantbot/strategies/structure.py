"""Marktstruktur und Multi-Timeframe."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import indicators as ind
from .base import Strategy, align_htf, htf_candles


class SwingStructure(Strategy):
    """Höhere Hochs + höhere Tiefs = long, tiefere Hochs + tiefere Tiefs = short.

    Ein Swing-Hoch bei t-k ist erst bei t bestätigt (k Kerzen später). Genau dann wird es
    verwendet, nicht früher (sonst Zukunftsdaten).
    """

    name, family = "swing_structure", "structure"
    default_params = {"k": 5, "atr_mult": 3.0, "allow_short": True}
    param_grid = {"k": [3, 5, 10], "atr_mult": [2.0, 3.0, 4.0]}

    @property
    def warmup(self):
        return int(self.params["k"]) * 10

    def compute(self, df, ctx):
        k = int(self.params["k"])
        h, l = df["high"].values, df["low"].values
        n = len(h)
        sig = np.zeros(n)
        highs: list[float] = []
        lows: list[float] = []
        state = 0
        for t in range(2 * k, n):
            j = t - k  # Kandidat, bei t bestätigt
            win_h = h[j - k: j + k + 1]
            win_l = l[j - k: j + k + 1]
            if h[j] == win_h.max():
                highs.append(h[j])
            if l[j] == win_l.min():
                lows.append(l[j])
            if len(highs) >= 2 and len(lows) >= 2:
                if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
                    state = 1
                elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
                    state = -1 if self.params["allow_short"] else 0
                # gemischt: letzten Zustand beibehalten
            sig[t] = state
        return self.output(pd.Series(sig, index=df.index), self.params["atr_mult"] * ind.atr(df, 14))


class MtfPullback(Strategy):
    """Übergeordneter Trend (Tages-EMA) + Einstieg im Rücksetzer (RSI) auf dem eigenen Zeitrahmen."""

    name, family = "mtf_pullback", "structure"
    default_params = {"htf": "1d", "htf_ema": 50, "rsi_n": 14, "entry": 40, "exit": 60, "atr_mult": 2.5,
                      "allow_short": True}
    param_grid = {"htf_ema": [20, 50, 100], "entry": [30, 35, 40], "atr_mult": [2.0, 3.0]}

    def validate(self):
        p = self.params
        if not 0 < p["entry"] < 50 < p["exit"] < 100:
            raise ValueError("entry < 50 < exit nötig")

    @property
    def warmup(self):
        return int(self.params["rsi_n"]) * 5

    def compute(self, df, ctx):
        p = self.params
        d = htf_candles(df, ctx.timeframe, p["htf"])
        trend = np.sign(d["close"] - ind.ema(d["close"], p["htf_ema"]))
        trend = align_htf(trend, df.index).fillna(0.0)
        r = ind.rsi(df["close"], p["rsi_n"])
        short = p["allow_short"]
        sig = ind.hold_state((trend > 0) & (r < p["entry"]), (r > p["exit"]) | (trend <= 0),
                             ((trend < 0) & (r > 100 - p["entry"])) if short else None,
                             ((r < 100 - p["exit"]) | (trend >= 0)) if short else None)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), htf_trend=trend, rsi=r)
