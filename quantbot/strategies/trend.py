"""Trendfolge-Strategien."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import indicators as ind
from .base import Strategy, StrategyContext


class EmaTrend(Strategy):
    """Richtung = schnelle EMA über/unter langsamer EMA, optional nur bei ADX >= adx_min."""

    name, family = "ema_trend", "trend"
    default_params = {"fast": 20, "slow": 100, "adx_min": 0, "atr_mult": 3.0, "allow_short": True}
    param_grid = {"fast": [10, 20, 40], "slow": [60, 100, 200], "adx_min": [0, 20], "atr_mult": [2.0, 3.0, 4.0]}

    def validate(self):
        if self.params["fast"] >= self.params["slow"]:
            raise ValueError("fast < slow nötig")

    @property
    def warmup(self):
        return int(self.params["slow"] * 3)

    def compute(self, df, ctx):
        p = self.params
        f, s = ind.ema(df["close"], p["fast"]), ind.ema(df["close"], p["slow"])
        sig = np.sign(f - s).where(s.notna(), 0.0)
        if p["adx_min"] > 0:
            a, _, _ = ind.adx(df)
            sig = sig.where(a >= p["adx_min"], 0.0)
        if not p["allow_short"]:
            sig = sig.clip(lower=0)
        a14 = ind.atr(df, 14)
        return self.output(sig, p["atr_mult"] * a14, spread=(f - s) / df["close"])


class DonchianBreakout(Strategy):
    """Ausbruch über das Hoch / unter das Tief der letzten n Kerzen, Ausstieg über m Kerzen."""

    name, family = "donchian_breakout", "trend"
    default_params = {"entry": 55, "exit": 20, "atr_mult": 3.0, "allow_short": True}
    param_grid = {"entry": [20, 55, 100], "exit": [10, 20, 50], "atr_mult": [2.0, 3.0, 4.0]}

    def validate(self):
        if self.params["exit"] >= self.params["entry"]:
            raise ValueError("exit < entry nötig")

    @property
    def warmup(self):
        return int(self.params["entry"]) + 20

    def compute(self, df, ctx):
        p = self.params
        c = df["close"]
        hi_e, lo_e = ind.donchian(df, p["entry"])
        hi_x, lo_x = ind.donchian(df, p["exit"])
        short = p["allow_short"]
        sig = ind.hold_state(c > hi_e, c < lo_x, (c < lo_e) if short else None, (c > hi_x) if short else None)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14),
                           dist_high=(c / hi_e - 1), dist_low=(c / lo_e - 1))


class TimeSeriesMomentum(Strategy):
    """Durchschnitt der Vorzeichen der Rendite über drei Zeiträume (Stärke 1/3, 2/3, 1)."""

    name, family = "ts_momentum", "trend"
    default_params = {"l1": 20, "l2": 60, "l3": 120, "atr_mult": 3.0, "allow_short": True}
    param_grid = {"l1": [10, 20, 30], "l2": [40, 60, 90], "l3": [120, 180, 250], "atr_mult": [2.0, 3.0, 4.0]}

    def validate(self):
        if not self.params["l1"] < self.params["l2"] < self.params["l3"]:
            raise ValueError("l1 < l2 < l3 nötig")

    @property
    def warmup(self):
        return int(self.params["l3"]) + 20

    def compute(self, df, ctx):
        p = self.params
        c = df["close"]
        parts = [np.sign(c / c.shift(p[k]) - 1) for k in ("l1", "l2", "l3")]
        sig = (sum(parts) / 3).where(c.shift(p["l3"]).notna(), 0.0)
        if not p["allow_short"]:
            sig = sig.clip(lower=0)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14),
                           mom_l1=c / c.shift(p["l1"]) - 1, mom_l3=c / c.shift(p["l3"]) - 1)


class AdxDirectional(Strategy):
    """+DI/-DI-Richtung nur bei ausgeprägtem Trend (ADX > Schwelle)."""

    name, family = "adx_directional", "trend"
    default_params = {"n": 14, "adx_min": 25, "atr_mult": 3.0, "allow_short": True}
    param_grid = {"n": [10, 14, 20], "adx_min": [20, 25, 30], "atr_mult": [2.0, 3.0, 4.0]}

    @property
    def warmup(self):
        return int(self.params["n"]) * 5

    def compute(self, df, ctx):
        p = self.params
        a, pdi, mdi = ind.adx(df, p["n"])
        sig = pd.Series(np.where(pdi > mdi, 1.0, -1.0), index=df.index).where(a >= p["adx_min"], 0.0)
        sig = sig.where(a.notna(), 0.0)
        if not p["allow_short"]:
            sig = sig.clip(lower=0)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), adx=a, di_spread=pdi - mdi)
