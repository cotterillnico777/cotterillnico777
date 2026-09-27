"""Synthetische Marktdaten AUSSCHLIESSLICH für Funktionstests.

Ergebnisse auf diesen Daten sind keine Performance-Aussagen. Datensätze werden im
Manifest mit ``synthetic: true`` markiert.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.timeframes import normalize_index, pandas_rule, periods_per_year


def synthetic_ohlcv(
    n: int,
    timeframe: str = "1h",
    seed: int = 0,
    annual_vol: float = 0.6,
    annual_drift: float = 0.0,
    start: str = "2022-01-01",
    price: float = 100.0,
    regime_switch: bool = False,
    trend_blocks_days: int = 0,
    trend_drift: float = 1.5,
) -> pd.DataFrame:
    """Geometrische Brownsche Bewegung, optional mit Volatilitäts-Regimewechseln."""
    rng = np.random.default_rng(seed)
    ppy = periods_per_year(timeframe)
    sigma = np.full(n, annual_vol / np.sqrt(ppy))
    if regime_switch:
        # Blöcke mit halber/doppelter Volatilität
        block = max(n // 8, 1)
        mult = rng.choice([0.5, 1.0, 2.0], size=n // block + 1)
        sigma *= np.repeat(mult, block)[:n]
    mu = annual_drift / ppy - 0.5 * sigma**2
    if trend_blocks_days:
        # Persistente Auf-/Abwärtsphasen (nur für Tests der Pipeline-Logik!)
        block = max(int(trend_blocks_days * ppy / 365), 1)
        signs = rng.choice([-1.0, 1.0], size=n // block + 1)
        mu = mu + np.repeat(signs, block)[:n] * trend_drift / ppy
    rets = rng.normal(mu, sigma)
    close = price * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[price], close[:-1]])
    wick = np.abs(rng.normal(0, sigma * 0.6))
    high = np.maximum(open_, close) * np.exp(wick)
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, sigma * 0.6)))
    idx = pd.date_range(start, periods=n, freq=pandas_rule(timeframe), tz="UTC", name="timestamp")
    vol = rng.lognormal(10, 0.5, n)
    return normalize_index(
        pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)
    )


def synthetic_funding(index: pd.DatetimeIndex, seed: int = 0, mean: float = 0.0001) -> pd.DataFrame:
    """Funding alle 8 h im Zeitraum von ``index``."""
    rng = np.random.default_rng(seed + 1)
    start = index[0].floor("8h")
    ts = pd.date_range(start, index[-1], freq="8h", tz="UTC", name="timestamp")
    rate = mean + rng.normal(0, mean, len(ts))
    return normalize_index(pd.DataFrame({"rate": rate}, index=ts))
