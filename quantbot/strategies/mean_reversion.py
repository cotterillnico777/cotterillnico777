"""Mean-Reversion-Strategien. Ohne Trendfilter handeln sie gegen jeden Trend."""

from __future__ import annotations

import pandas as pd

from .. import indicators as ind
from .base import Strategy


def _trend_gate(df: pd.DataFrame, n: int) -> tuple[pd.Series, pd.Series]:
    """(long erlaubt, short erlaubt) – nur mit dem übergeordneten Trend handeln. n=0: aus."""
    if n <= 0:
        t = pd.Series(True, index=df.index)
        return t, t
    ma = ind.sma(df["close"], n)
    return (df["close"] > ma).fillna(False), (df["close"] < ma).fillna(False)


class RsiReversion(Strategy):
    name, family = "rsi_reversion", "mean_reversion"
    default_params = {"n": 14, "low": 30, "high": 70, "exit": 50, "trend_filter": 200, "atr_mult": 2.5,
                      "allow_short": True}
    param_grid = {"n": [7, 14, 21], "low": [20, 25, 30], "trend_filter": [0, 200], "atr_mult": [2.0, 3.0]}

    def validate(self):
        p = self.params
        if not 0 < p["low"] < p["exit"] < p["high"] < 100:
            raise ValueError("low < exit < high nötig")

    @property
    def warmup(self):
        return max(int(self.params["n"]) * 5, int(self.params["trend_filter"]) + 1)

    def compute(self, df, ctx):
        p = self.params
        r = ind.rsi(df["close"], p["n"])
        high = p["high"]
        can_long, can_short = _trend_gate(df, p["trend_filter"])
        short = p["allow_short"]
        sig = ind.hold_state(
            (r < p["low"]) & can_long, r > p["exit"],
            ((r > high) & can_short) if short else None, (r < p["exit"]) if short else None,
        )
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), rsi=r)


class BollingerReversion(Strategy):
    name, family = "bollinger_reversion", "mean_reversion"
    default_params = {"n": 20, "k": 2.0, "trend_filter": 200, "atr_mult": 2.5, "allow_short": True}
    param_grid = {"n": [14, 20, 30], "k": [1.5, 2.0, 2.5], "trend_filter": [0, 200], "atr_mult": [2.0, 3.0]}

    @property
    def warmup(self):
        return max(int(self.params["n"]) * 3, int(self.params["trend_filter"]) + 1)

    def compute(self, df, ctx):
        p = self.params
        c = df["close"]
        lo, mid, hi = ind.bollinger(c, p["n"], p["k"])
        can_long, can_short = _trend_gate(df, p["trend_filter"])
        short = p["allow_short"]
        sig = ind.hold_state((c < lo) & can_long, c >= mid,
                             ((c > hi) & can_short) if short else None, (c <= mid) if short else None)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), bb_pos=(c - mid) / (hi - mid))


class ZScoreReversion(Strategy):
    name, family = "zscore_reversion", "mean_reversion"
    default_params = {"n": 50, "entry": 2.0, "exit": 0.5, "trend_filter": 0, "atr_mult": 2.5, "allow_short": True}
    param_grid = {"n": [20, 50, 100], "entry": [1.5, 2.0, 2.5], "exit": [0.0, 0.5], "atr_mult": [2.0, 3.0]}

    def validate(self):
        if self.params["exit"] >= self.params["entry"]:
            raise ValueError("exit < entry nötig")

    @property
    def warmup(self):
        return max(int(self.params["n"]) * 2, int(self.params["trend_filter"]) + 1)

    def compute(self, df, ctx):
        p = self.params
        z = ind.zscore(df["close"], p["n"])
        can_long, can_short = _trend_gate(df, p["trend_filter"])
        short = p["allow_short"]
        sig = ind.hold_state((z < -p["entry"]) & can_long, z > -p["exit"],
                             ((z > p["entry"]) & can_short) if short else None, (z < p["exit"]) if short else None)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), z=z)


class VwapReversion(Strategy):
    """Abweichung vom rollierenden VWAP in ATR-Einheiten, Ausstieg bei Rückkehr zum VWAP."""

    name, family = "vwap_reversion", "mean_reversion"
    default_params = {"n": 48, "entry_atr": 2.0, "trend_filter": 0, "atr_mult": 2.5, "allow_short": True}
    param_grid = {"n": [24, 48, 96], "entry_atr": [1.5, 2.0, 3.0], "atr_mult": [2.0, 3.0]}

    @property
    def warmup(self):
        return max(int(self.params["n"]) * 2, int(self.params["trend_filter"]) + 1)

    def compute(self, df, ctx):
        p = self.params
        c = df["close"]
        v = ind.rolling_vwap(df, p["n"])
        a = ind.atr(df, 14)
        dev = (c - v) / a
        can_long, can_short = _trend_gate(df, p["trend_filter"])
        short = p["allow_short"]
        sig = ind.hold_state((dev < -p["entry_atr"]) & can_long, c >= v,
                             ((dev > p["entry_atr"]) & can_short) if short else None, (c <= v) if short else None)
        return self.output(sig, p["atr_mult"] * a, vwap_dev_atr=dev)
