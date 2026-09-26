"""Trendfilter auf einem höheren Zeitrahmen.

Beispiel: Die Strategie handelt auf 1h-Kerzen, gekauft wird aber nur, wenn der
Tagesschlusskurs über seinem 200-Tage-Durchschnitt liegt ("Aufwärtstrend").

Kein Blick in die Zukunft: Eine Tageskerze zählt erst, wenn sie abgeschlossen
ist. Bei 1h-Kerzen ist das die 23-Uhr-Kerze, deren Schluss mit dem Tagesschluss
zusammenfällt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import TIMEFRAME_SECONDS
from .config import TrendFilterConfig
from .indicators import ema, sma


def timeframe_delta(tf: str) -> pd.Timedelta:
    unit = tf[-1]
    if unit not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unbekannter Timeframe: {tf}")
    return pd.Timedelta(seconds=int(tf[:-1]) * TIMEFRAME_SECONDS[unit])


def _resample_rule(tf: str) -> str:
    n, unit = int(tf[:-1]), tf[-1]
    if unit == "w":
        if n != 1:
            raise ValueError("Wochen-Trendfilter nur als 1w möglich")
        return "W-MON"
    return {"m": f"{n}min", "h": f"{n}h", "d": f"{n}D"}[unit]


def resample_close(df: pd.DataFrame, tf: str) -> pd.Series:
    """Schlusskurse des höheren Zeitrahmens, indiziert nach Kerzenbeginn."""
    rule = _resample_rule(tf)
    kwargs = {"label": "left", "closed": "left"}
    if rule.endswith(("h", "min")):
        kwargs["origin"] = "epoch"  # Börsen-Kerzen sind an 00:00 UTC ausgerichtet
    return df["close"].resample(rule, **kwargs).last().dropna()


def trend_up(htf_close: pd.Series, cfg: TrendFilterConfig) -> pd.Series:
    """True, wo der Schluss über dem gleitenden Durchschnitt liegt (NaN = unbekannt)."""
    ma = (ema if cfg.kind == "ema" else sma)(htf_close, cfg.period)
    return (htf_close > ma).where(ma.notna())


def align(
    cond: pd.Series, htf: str, base_tf: str, base_index: pd.DatetimeIndex
) -> pd.Series:
    """Bedingung des höheren Zeitrahmens auf die Basis-Kerzen übertragen.

    Eine Basis-Kerze mit Beginn T endet bei T + base_tf. Sie darf die höhere
    Kerze mit Beginn H nutzen, sobald T + base_tf >= H + htf.
    """
    shift = timeframe_delta(htf) - timeframe_delta(base_tf)
    shifted = cond.copy()
    shifted.index = shifted.index + shift
    out = shifted.reindex(base_index.union(shifted.index)).ffill().reindex(base_index)
    return out.astype("boolean").fillna(False).astype(bool)


def condition(df: pd.DataFrame, base_tf: str, cfg: TrendFilterConfig) -> pd.Series:
    """Trendbedingung für jede Basis-Kerze aus den Basis-Kerzen selbst (Backtest)."""
    if timeframe_delta(cfg.timeframe) < timeframe_delta(base_tf):
        raise ValueError("trend_filter.timeframe muss >= dem Handels-Timeframe sein")
    return align(trend_up(resample_close(df, cfg.timeframe), cfg), cfg.timeframe, base_tf, df.index)


def condition_from_htf(
    htf_df: pd.DataFrame, base_tf: str, base_index: pd.DatetimeIndex, cfg: TrendFilterConfig
) -> pd.Series:
    """Wie ``condition``, aber mit direkt von der Börse geladenen HTF-Kerzen (Live)."""
    return align(trend_up(htf_df["close"], cfg), cfg.timeframe, base_tf, base_index)


def strategy_signals(strategy, df: pd.DataFrame, base_tf: str, cfg: TrendFilterConfig) -> pd.Series:
    """Signale der Strategie, bei aktivem Trendfilter bereits gefiltert."""
    signals = strategy.generate_signals(df)
    if not cfg.enabled:
        return signals
    return apply(signals, condition(df, base_tf, cfg), cfg.mode)


def apply(signals: pd.Series, trend_ok: pd.Series, mode: str) -> pd.Series:
    """Strategiesignal mit dem Trendfilter kombinieren.

    ``exit``:  investiert nur, solange Signal UND Trend passen (Trendbruch = Verkauf).
    ``entry``: Einstieg nur bei passendem Trend; eine offene Position wird aber
               erst durch das Strategiesignal geschlossen.
    """
    trend_ok = trend_ok.reindex(signals.index).fillna(False).astype(bool)
    # Gewichte (z. B. Ensemble 2/3) bleiben erhalten, der Filter setzt nur auf 0
    if mode == "exit":
        return signals.astype(float).where(trend_ok, 0.0)
    sig = signals.values.astype(float)
    ok = trend_ok.values
    out = np.zeros(len(sig))
    held = False
    for i in range(len(sig)):
        held = sig[i] > 0 and (held or ok[i])
        out[i] = sig[i] if held else 0.0
    return pd.Series(out, index=signals.index)
