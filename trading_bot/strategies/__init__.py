"""Strategie-Registry. Neue Strategien hier eintragen."""

from __future__ import annotations

from typing import Any

from .base import Strategy
from .bollinger_breakout import BollingerBreakout
from .ma_crossover import MACrossover
from .rsi_reversion import RSIReversion

STRATEGIES: dict[str, type[Strategy]] = {
    cls.name: cls for cls in (MACrossover, RSIReversion, BollingerBreakout)
}


def create_strategy(name: str, params: dict[str, Any] | None = None) -> Strategy:
    try:
        cls = STRATEGIES[name]
    except KeyError:
        raise ValueError(
            f"Unbekannte Strategie '{name}'. Verfügbar: {', '.join(sorted(STRATEGIES))}"
        ) from None
    return cls(**(params or {}))


__all__ = ["STRATEGIES", "Strategy", "create_strategy"]
