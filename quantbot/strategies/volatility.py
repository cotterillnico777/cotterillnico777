"""Volatilitäts-Strategien: Kontraktion -> Ausbruch."""

from __future__ import annotations

import pandas as pd

from .. import indicators as ind
from .base import Strategy


class SqueezeBreakout(Strategy):
    """Nach Kontraktion (Bollinger-Bandbreite im unteren Perzentil) Ausbruch aus der Range.

    Ausstieg bei Rückkehr unter die Mittellinie (long) bzw. darüber (short).
    """

    name, family = "squeeze_breakout", "volatility"
    default_params = {"n": 20, "squeeze_pct": 0.2, "rank_window": 250, "lookback": 5, "atr_mult": 2.5,
                      "allow_short": True}
    param_grid = {"n": [14, 20, 30], "squeeze_pct": [0.1, 0.2, 0.3], "atr_mult": [2.0, 3.0]}

    @property
    def warmup(self):
        return int(self.params["rank_window"]) // 2 + int(self.params["n"])

    def compute(self, df, ctx):
        p = self.params
        c = df["close"]
        lo, mid, hi = ind.bollinger(c, p["n"], 2.0)
        bw = (hi - lo) / mid
        rank = ind.percentile_rank(bw, p["rank_window"])
        squeezed = (rank <= p["squeeze_pct"]).rolling(p["lookback"], min_periods=1).max().astype(bool)
        prev_hi, prev_lo = ind.donchian(df, p["n"])
        short = p["allow_short"]
        sig = ind.hold_state(squeezed & (c > prev_hi), c < mid,
                             (squeezed & (c < prev_lo)) if short else None, (c > mid) if short else None)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), bw_rank=rank)


class KeltnerBreakout(Strategy):
    """Volatilitätsausbruch: Schluss außerhalb EMA ± k×ATR, Ausstieg bei Rückkehr zur EMA."""

    name, family = "keltner_breakout", "volatility"
    default_params = {"n": 20, "k": 2.0, "atr_mult": 2.5, "allow_short": True}
    param_grid = {"n": [20, 50, 100], "k": [1.5, 2.0, 3.0], "atr_mult": [2.0, 3.0]}

    @property
    def warmup(self):
        return int(self.params["n"]) * 3

    def compute(self, df, ctx):
        p = self.params
        c = df["close"]
        mid = ind.ema(c, p["n"])
        a = ind.atr(df, p["n"])
        up, dn = mid + p["k"] * a, mid - p["k"] * a
        short = p["allow_short"]
        sig = ind.hold_state(c > up, c < mid, (c < dn) if short else None, (c > mid) if short else None)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), kc_pos=(c - mid) / a)
