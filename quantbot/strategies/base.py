"""Strategie-Schnittstelle (v2).

Eine Strategie berechnet je Kerze:
  signal               -1..+1  gewünschte Richtung × Stärke (0 = kein Trade / NO TRADE)
  stop_distance        > 0     Preisabstand zum Schutz-Stop (Grundlage der Positionsgröße)
  take_profit_distance >= 0    optional (NaN = keins)
  f_*                          optionale Features für Journal und Analyse

Regeln:
  - Zeile t nutzt nur Daten bis einschließlich Kerze t (Test: Präfix-Konsistenz)
  - keine Kenntnis von Kontostand, Positionsgröße oder Hebel (das macht die Risk Engine)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..core.timeframes import pandas_rule, tf_delta, tf_seconds


@dataclass
class StrategyContext:
    """Zusatzdaten, die manche Strategien brauchen (alle bereits zeitlich ausgerichtet)."""

    symbol: str
    timeframe: str
    universe_closes: dict[str, pd.Series] = field(default_factory=dict)  # für Relative Stärke
    funding: pd.Series | None = None  # Funding-Rate je Funding-Zeitpunkt (Index = Zeitpunkt)


class Strategy(ABC):
    name: str = "base"
    family: str = "none"  # trend | mean_reversion | momentum | volatility | structure | derivatives | baseline
    version: str = "1"
    default_params: dict[str, Any] = {}
    param_grid: dict[str, list[Any]] = {}

    def __init__(self, **params: Any) -> None:
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name}: unbekannte Parameter {sorted(unknown)}")
        self.params = {**self.default_params, **params}
        self.validate()

    def validate(self) -> None:
        pass

    @property
    def warmup(self) -> int:
        return 50

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"

    @abstractmethod
    def compute(self, df: pd.DataFrame, ctx: StrategyContext) -> pd.DataFrame: ...

    def __repr__(self) -> str:
        return f"{self.name}({', '.join(f'{k}={v}' for k, v in self.params.items())})"

    # --------------------------------------------------------- Hilfen
    @staticmethod
    def output(signal: pd.Series, stop_distance: pd.Series, take_profit: pd.Series | None = None,
               **features: pd.Series) -> pd.DataFrame:
        out = pd.DataFrame({
            "signal": signal.fillna(0.0).clip(-1, 1).astype(float),
            "stop_distance": stop_distance.astype(float),
            "take_profit_distance": (take_profit if take_profit is not None else
                                     pd.Series(np.nan, index=signal.index)).astype(float),
        })
        for k, v in features.items():
            out[f"f_{k}"] = v.astype(float)
        # Ohne gültigen Stop kein Trade
        out.loc[~np.isfinite(out["stop_distance"]) | (out["stop_distance"] <= 0), "signal"] = 0.0
        return out


def htf_candles(df: pd.DataFrame, base_tf: str, htf: str) -> pd.DataFrame:
    """Vollständige Kerzen des höheren Zeitrahmens. Index = Zeitpunkt, ab dem sie sichtbar sind.

    Eine höhere Kerze mit Beginn H ist ab der Basis-Kerze sichtbar, deren Ende H + htf ist,
    also ab Basis-Kerzenbeginn H + htf - base_tf. Unvollständige Kerzen werden verworfen.
    """
    if tf_seconds(htf) <= tf_seconds(base_tf):
        return df.copy()
    kw = {"label": "left", "closed": "left"}
    if htf[-1] in "mh":
        kw["origin"] = "epoch"
    agg = df.resample(pandas_rule(htf), **kw).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    counts = df["close"].resample(pandas_rule(htf), **kw).count()
    agg = agg[counts == tf_seconds(htf) // tf_seconds(base_tf)].dropna()
    agg.index = agg.index + tf_delta(htf) - tf_delta(base_tf)
    return agg


def align_htf(values: pd.Series | pd.DataFrame, index: pd.DatetimeIndex):
    """Werte vom höheren Zeitrahmen auf die Basis-Kerzen übertragen (letzter bekannter Wert)."""
    return values.reindex(index.union(values.index)).ffill().reindex(index)


def higher_tf(df: pd.DataFrame, base_tf: str, htf: str) -> pd.DataFrame:
    """Höhere Kerzen, auf die Basis-Kerzen ausgerichtet (für Filter wie 'Tagesschluss > EMA')."""
    return align_htf(htf_candles(df, base_tf, htf), df.index)
