"""Marktregime je Kerze: Trend (bull/bear/sideways) × Volatilität (high/normal/low).

Grundlage sind vollständige Tageskerzen (sichtbar erst nach Tagesschluss):
  Trend:  Schluss über/unter SMA(trend_ma_days) UND Steigung der SMA über slope_days
          größer/kleiner als ±sideways_band -> bull/bear, sonst sideways
  Vola:   realisierte Vola (vol_lookback_days) als Perzentil der letzten vol_rank_days Tage
          >= high_vol_pct -> high, <= low_vol_pct -> low, sonst normal
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import indicators as ind
from ..config.schema import RegimeConfig
from ..strategies.base import align_htf, htf_candles

TRENDS = ("bull", "bear", "sideways")
VOLS = ("high", "normal", "low")


def detect_regimes(df: pd.DataFrame, timeframe: str, cfg: RegimeConfig) -> pd.DataFrame:
    d = htf_candles(df, timeframe, "1d") if timeframe != "1d" else df.copy()
    c = d["close"]
    ma = ind.sma(c, cfg.trend_ma_days)
    slope = ma / ma.shift(cfg.slope_days) - 1
    trend = pd.Series("unknown", index=d.index, dtype=object)
    ok = ma.notna() & slope.notna()
    trend[ok] = "sideways"
    trend[ok & (c > ma) & (slope > cfg.sideways_band)] = "bull"
    trend[ok & (c < ma) & (slope < -cfg.sideways_band)] = "bear"

    vol = ind.realized_vol(c, cfg.vol_lookback_days, 365)
    rank = ind.percentile_rank(vol, cfg.vol_rank_days)
    vreg = pd.Series("unknown", index=d.index, dtype=object)
    vok = rank.notna()
    vreg[vok] = "normal"
    vreg[vok & (rank >= cfg.high_vol_pct)] = "high"
    vreg[vok & (rank <= cfg.low_vol_pct)] = "low"

    out = pd.DataFrame({"trend": trend, "vol": vreg, "vol_rank": rank, "ma_slope": slope})
    out = align_htf(out, df.index)
    out["trend"] = out["trend"].fillna("unknown")
    out["vol"] = out["vol"].fillna("unknown")
    out["label"] = out["trend"] + "|" + out["vol"]
    return out


def regime_allows(allowed: list[str], trend: str, vol: str) -> bool:
    """Leere Liste = immer. Einträge: 'bull', 'high', oder kombiniert 'bull|high'."""
    if not allowed:
        return True
    return trend in allowed or vol in allowed or f"{trend}|{vol}" in allowed


__all__ = ["detect_regimes", "regime_allows", "TRENDS", "VOLS"]
