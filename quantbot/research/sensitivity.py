"""Parameterraster und Nachbarschafts-Robustheit.

Ein einzelner Spitzenwert, dessen Nachbarn schlecht sind, ist ein Warnsignal (Zufall/Overfitting).
Bewertet wird deshalb der Mittelwert über die Kombination und ihre direkten Rasternachbarn.
"""

from __future__ import annotations

import itertools
import math
import random
from typing import Any

import numpy as np
import pandas as pd


def grid_combos(grid: dict[str, list[Any]], defaults: dict[str, Any], max_combos: int | None = None,
                seed: int = 42) -> list[tuple[tuple[int, ...], dict[str, Any]]]:
    keys = list(grid)
    combos = []
    for idx in itertools.product(*(range(len(grid[k])) for k in keys)):
        combos.append((idx, {**defaults, **{k: grid[k][i] for k, i in zip(keys, idx)}}))
    if max_combos and len(combos) > max_combos:
        rng = random.Random(seed)
        # Standardparameter immer behalten, Rest zufällig (reproduzierbar)
        default_idx = [c for c in combos if all(c[1][k] == defaults[k] for k in keys)]
        rest = [c for c in combos if c not in default_idx]
        combos = default_idx + rng.sample(rest, max_combos - len(default_idx))
    return combos


def neighborhood_scores(rows: pd.DataFrame, grid: dict[str, list[Any]], metric: str = "sharpe") -> pd.Series:
    """Mittel des Scores über Kombination + Nachbarn (±1 Schritt bei Zahlen, kategorisch getrennt).

    Nicht getestete oder ungültige Nachbarn werden übersprungen; Nachbarn ohne Trades zählen
    mit dem schlechtesten Score (konservativ).
    """
    keys = list(grid)
    numeric = [all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in grid[k]) for k in keys]
    by_idx = dict(zip(rows["idx"], rows[metric]))
    valid = rows[metric].replace([np.inf, -np.inf], np.nan).dropna()
    penalty = float(valid.min()) if len(valid) else 0.0
    out = []
    for idx, s in zip(rows["idx"], rows[metric]):
        if s is None or not math.isfinite(s):
            out.append(np.nan)
            continue
        vals = []
        steps = [(-1, 0, 1) if num else (0,) for num in numeric]
        for delta in itertools.product(*steps):
            nb = tuple(i + d for i, d in zip(idx, delta))
            if nb in by_idx:
                v = by_idx[nb]
                vals.append(v if v is not None and math.isfinite(v) else penalty)
        out.append(float(np.mean(vals)))
    return pd.Series(out, index=rows.index)


def summarize_grid(rows: pd.DataFrame, metric: str = "sharpe") -> dict:
    s = rows[metric].replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return {"combos": len(rows), "positive_share": 0.0}
    best = rows.loc[rows[metric].idxmax()]
    robust = rows.loc[rows["robust"].idxmax()] if rows["robust"].notna().any() else best
    return {
        "combos": int(len(rows)),
        "positive_share": float((s > 0).mean()),
        "median": float(s.median()),
        "best": float(best[metric]),
        "best_params": best["params"],
        "robust_score": float(robust["robust"]),
        "robust_params": robust["params"],
        "robust_own": float(robust[metric]),
        # < 0.5: Spitze ohne tragfähige Nachbarschaft
        "plateau_ratio": float(robust["robust"] / best[metric]) if best[metric] > 0 else float("nan"),
    }
