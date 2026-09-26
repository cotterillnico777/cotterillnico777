"""Strategie-Registry (v2)."""

from __future__ import annotations

from typing import Any

from .base import Strategy, StrategyContext
from .derivatives import FundingContrarian
from .mean_reversion import BollingerReversion, RsiReversion, VwapReversion, ZScoreReversion
from .momentum import BreakoutRetest, MultiTimeframeMomentum, RelativeStrength, VolumeMomentum
from .structure import MtfPullback, SwingStructure
from .trend import AdxDirectional, DonchianBreakout, EmaTrend, TimeSeriesMomentum
from .volatility import KeltnerBreakout, SqueezeBreakout

STRATEGIES: dict[str, type[Strategy]] = {
    cls.name: cls
    for cls in (
        EmaTrend, DonchianBreakout, TimeSeriesMomentum, AdxDirectional,
        RsiReversion, BollingerReversion, ZScoreReversion, VwapReversion,
        RelativeStrength, VolumeMomentum, BreakoutRetest, MultiTimeframeMomentum,
        SqueezeBreakout, KeltnerBreakout,
        SwingStructure, MtfPullback,
        FundingContrarian,
    )
}


def create(name: str, params: dict[str, Any] | None = None) -> Strategy:
    if name not in STRATEGIES:
        raise ValueError(f"Unbekannte Strategie {name!r}. Verfügbar: {', '.join(sorted(STRATEGIES))}")
    return STRATEGIES[name](**(params or {}))


__all__ = ["STRATEGIES", "Strategy", "StrategyContext", "create"]
