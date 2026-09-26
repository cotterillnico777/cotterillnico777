"""Basisklasse für alle Strategien."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class Strategy(ABC):
    """Eine Strategie wandelt OHLCV-Kerzen in eine Zielposition um.

    Rückgabe von ``generate_signals``: Serie mit demselben Index wie ``df``
    und Werten 1 (long / investiert) oder 0 (flat / in Quote-Währung).
    Der Wert in Zeile t darf nur Daten bis einschließlich Kerze t verwenden
    (kein Blick in die Zukunft). Ausgeführt wird er erst zur nächsten Kerze.
    """

    name: str = "base"
    default_params: dict[str, Any] = {}
    # Werte, die der Optimierer ausprobiert (geordnet, damit Nachbarn Sinn ergeben)
    param_grid: dict[str, list[Any]] = {}

    def __init__(self, **params: Any) -> None:
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(
                f"Unbekannte Parameter für {self.name}: {sorted(unknown)}. "
                f"Erlaubt: {sorted(self.default_params)}"
            )
        self.params = {**self.default_params, **params}
        self.validate()

    def validate(self) -> None:
        """Parameter prüfen. Bei Bedarf überschreiben."""

    @property
    def warmup(self) -> int:
        """Anzahl Kerzen, die für ein gültiges Signal nötig sind."""
        return 1

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.name}({args})"
