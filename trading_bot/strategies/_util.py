from __future__ import annotations

import pandas as pd


def hold_between(entries: pd.Series, exits: pd.Series) -> pd.Series:
    """Position 1 ab einem Einstiegssignal bis zum nächsten Ausstiegssignal."""
    state = pd.Series(pd.NA, index=entries.index, dtype="Float64")
    state[entries.fillna(False).astype(bool)] = 1.0
    state[exits.fillna(False).astype(bool)] = 0.0
    return state.ffill().fillna(0).astype(int)
