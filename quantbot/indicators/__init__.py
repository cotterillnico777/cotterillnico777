"""Technische Indikatoren. Wert in Zeile t nutzt nur Daten bis einschließlich Kerze t."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def wilder(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return wilder(true_range(df), n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up, down = wilder(d.clip(lower=0), n), wilder(-d.clip(upper=0), n)
    out = 100 - 100 / (1 + up / down)
    out = out.where(down != 0, 100.0).where(~((up == 0) & (down == 0)), 50.0)
    return out.where(up.notna())


def adx(df: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(ADX, +DI, -DI)."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = wilder(true_range(df), n)
    plus_di = 100 * wilder(plus_dm, n) / tr
    minus_di = 100 * wilder(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return wilder(dx, n), plus_di, minus_di


def donchian(df: pd.DataFrame, n: int) -> tuple[pd.Series, pd.Series]:
    """Hoch/Tief der VORHERIGEN n Kerzen (ohne aktuelle)."""
    return (
        df["high"].rolling(n, min_periods=n).max().shift(1),
        df["low"].rolling(n, min_periods=n).min().shift(1),
    )


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return mid - k * sd, mid, mid + k * sd


def zscore(x: pd.Series, n: int) -> pd.Series:
    m = x.rolling(n, min_periods=n).mean()
    s = x.rolling(n, min_periods=n).std(ddof=0)
    return (x - m) / s.replace(0, np.nan)


def rolling_vwap(df: pd.DataFrame, n: int) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    pv = (tp * df["volume"]).rolling(n, min_periods=n).sum()
    v = df["volume"].rolling(n, min_periods=n).sum()
    return pv / v.replace(0, np.nan)


def realized_vol(close: pd.Series, n: int, periods_per_year: float) -> pd.Series:
    return np.log(close).diff().rolling(n, min_periods=n).std() * np.sqrt(periods_per_year)


def percentile_rank(x: pd.Series, n: int) -> pd.Series:
    """Rang des aktuellen Werts unter den letzten n Werten (0..1), nur Vergangenheit."""
    return x.rolling(n, min_periods=max(n // 4, 2)).rank(pct=True)


def hold_state(entry_long: pd.Series, exit_long: pd.Series, entry_short: pd.Series | None = None,
               exit_short: pd.Series | None = None) -> pd.Series:
    """Zustandsautomat: +1 ab Long-Einstieg bis Long-Ausstieg, -1 analog für Short.

    Gleichzeitige Signale: Ausstieg vor Einstieg; Richtungswechsel nur über ein Einstiegssignal.
    """
    el = entry_long.fillna(False).values
    xl = exit_long.fillna(False).values
    es = entry_short.fillna(False).values if entry_short is not None else np.zeros(len(el), bool)
    xs = exit_short.fillna(False).values if exit_short is not None else np.zeros(len(el), bool)
    out = np.zeros(len(el))
    state = 0
    for i in range(len(el)):
        if state > 0 and xl[i]:
            state = 0
        elif state < 0 and xs[i]:
            state = 0
        if el[i] and not xl[i]:
            state = 1
        elif es[i] and not xs[i]:
            state = -1
        out[i] = state
    return pd.Series(out, index=entry_long.index)
