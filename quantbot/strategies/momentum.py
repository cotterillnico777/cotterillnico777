"""Momentum-Strategien."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import indicators as ind
from .base import Strategy, align_htf, htf_candles


class RelativeStrength(Strategy):
    """Querschnitts-Momentum: stärkstes Asset long, schwächstes short (nur mit passendem Eigentrend)."""

    name, family = "relative_strength", "momentum"
    default_params = {"lookback": 60, "atr_mult": 3.0, "allow_short": True}
    param_grid = {"lookback": [20, 60, 120], "atr_mult": [2.0, 3.0, 4.0]}

    @property
    def warmup(self):
        return int(self.params["lookback"]) + 20

    def compute(self, df, ctx):
        p = self.params
        L = p["lookback"]
        if len(ctx.universe_closes) < 2:
            raise ValueError("relative_strength braucht mehrere Märkte (universe_closes)")
        moms = pd.DataFrame({s: c / c.shift(L) - 1 for s, c in ctx.universe_closes.items()}).reindex(df.index)
        own = moms[ctx.symbol]
        valid = moms.notna().all(axis=1)
        best = pd.Series(None, index=df.index, dtype=object)
        worst = pd.Series(None, index=df.index, dtype=object)
        if valid.any():
            best[valid] = moms[valid].idxmax(axis=1)
            worst[valid] = moms[valid].idxmin(axis=1)
        sig = pd.Series(0.0, index=df.index)
        sig[(best == ctx.symbol) & (own > 0)] = 1.0
        if p["allow_short"]:
            sig[(worst == ctx.symbol) & (own < 0)] = -1.0
        sig[moms.isna().any(axis=1)] = 0.0
        rank = moms.rank(axis=1, pct=True)[ctx.symbol]
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), mom=own, rank=rank)


class VolumeMomentum(Strategy):
    """Ausbruch über das n-Kerzen-Hoch mit Volumenbestätigung, Ausstieg unter SMA(exit)."""

    name, family = "volume_momentum", "momentum"
    default_params = {"n": 20, "vol_mult": 1.5, "exit": 20, "atr_mult": 3.0, "allow_short": True}
    param_grid = {"n": [20, 40, 60], "vol_mult": [1.2, 1.5, 2.0], "atr_mult": [2.0, 3.0]}

    @property
    def warmup(self):
        return int(max(self.params["n"], self.params["exit"])) + 30

    def compute(self, df, ctx):
        p = self.params
        c = df["close"]
        hi, lo = ind.donchian(df, p["n"])
        vol_ok = df["volume"] > p["vol_mult"] * ind.sma(df["volume"], 20).shift(1)
        ma = ind.sma(c, p["exit"])
        short = p["allow_short"]
        sig = ind.hold_state((c > hi) & vol_ok, c < ma,
                             ((c < lo) & vol_ok) if short else None, (c > ma) if short else None)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14),
                           vol_ratio=df["volume"] / ind.sma(df["volume"], 20).shift(1))


class BreakoutRetest(Strategy):
    """Ausbruch über das n-Kerzen-Hoch, danach Rücksetzer bis an das Ausbruchsniveau
    (innerhalb tol × ATR, ohne Schluss darunter), Einstieg beim Wiederanstieg über das Vortageshoch.
    Ausstieg bei Schluss unter dem Niveau minus 1 ATR oder unter SMA(exit). Symmetrisch short."""

    name, family = "breakout_retest", "momentum"
    default_params = {"n": 40, "tol": 0.5, "max_wait": 20, "exit": 20, "atr_mult": 2.5, "allow_short": True}
    param_grid = {"n": [20, 40, 80], "tol": [0.3, 0.5, 1.0], "atr_mult": [2.0, 3.0]}

    @property
    def warmup(self):
        return int(self.params["n"]) + 30

    def compute(self, df, ctx):
        p = self.params
        c, h, l = df["close"].values, df["high"].values, df["low"].values
        hi, lo = ind.donchian(df, p["n"])
        hi, lo = hi.values, lo.values
        a = ind.atr(df, 14).values
        ma = ind.sma(df["close"], p["exit"]).values
        n = len(c)
        sig = np.zeros(n)
        state, level, since, retested = 0, np.nan, 0, False
        pos = 0
        for i in range(1, n):
            if not (np.isfinite(hi[i]) and np.isfinite(a[i])):
                continue
            # Positionsverwaltung
            if pos > 0 and (c[i] < level - a[i] or c[i] < ma[i]):
                pos = 0
            elif pos < 0 and (c[i] > level + a[i] or c[i] > ma[i]):
                pos = 0
            if pos == 0:
                if state == 0:
                    if c[i] > hi[i]:
                        state, level, since, retested = 1, hi[i], 0, False
                    elif p["allow_short"] and c[i] < lo[i]:
                        state, level, since, retested = -1, lo[i], 0, False
                else:
                    since += 1
                    if since > p["max_wait"] or (state > 0 and c[i] < level - a[i]) or \
                            (state < 0 and c[i] > level + a[i]):
                        state = 0
                    elif state > 0:
                        if l[i] <= level + p["tol"] * a[i]:
                            retested = True
                        elif retested and c[i] > h[i - 1]:
                            pos, state = 1, 0
                    else:
                        if h[i] >= level - p["tol"] * a[i]:
                            retested = True
                        elif retested and c[i] < l[i - 1]:
                            pos, state = -1, 0
            sig[i] = pos
        return self.output(pd.Series(sig, index=df.index), p["atr_mult"] * ind.atr(df, 14))


class MultiTimeframeMomentum(Strategy):
    """Handel nur, wenn Momentum auf höherem (Tages-) und eigenem Zeitrahmen übereinstimmt."""

    name, family = "mtf_momentum", "momentum"
    default_params = {"htf": "1d", "htf_lookback": 20, "ltf_lookback": 20, "atr_mult": 3.0, "allow_short": True}
    param_grid = {"htf_lookback": [10, 20, 50], "ltf_lookback": [10, 20, 50], "atr_mult": [2.0, 3.0]}

    @property
    def warmup(self):
        return int(self.params["ltf_lookback"]) + 30

    def compute(self, df, ctx):
        p = self.params
        c = df["close"]
        d = htf_candles(df, ctx.timeframe, p["htf"])["close"]
        dmom = align_htf(d / d.shift(p["htf_lookback"]) - 1, df.index)
        lmom = c / c.shift(p["ltf_lookback"]) - 1
        agree_up = (dmom > 0) & (lmom > 0)
        agree_dn = (dmom < 0) & (lmom < 0)
        sig = pd.Series(0.0, index=df.index)
        sig[agree_up] = 1.0
        if p["allow_short"]:
            sig[agree_dn] = -1.0
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), htf_mom=dmom, ltf_mom=lmom)
