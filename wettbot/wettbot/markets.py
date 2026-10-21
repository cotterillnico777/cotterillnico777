"""Wettmärkte aus der Ergebnismatrix + Margenbereinigung von Buchmacherquoten."""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

# Markt -> Selektionen (Reihenfolge = vollständige, sich ausschließende Menge)
MARKETS = {
    "1X2": ("H", "D", "A"),
    "OU1.5": ("O", "U"),
    "OU2.5": ("O", "U"),
    "OU3.5": ("O", "U"),
    "BTTS": ("Y", "N"),
}


def market_probs(m: np.ndarray) -> dict[str, dict[str, float]]:
    """Wahrscheinlichkeiten aller Märkte aus der Ergebnismatrix m[heim, gast]."""
    n = m.shape[0]
    hg, ag = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    tot = hg + ag
    out = {
        "1X2": {"H": float(m[hg > ag].sum()), "D": float(np.trace(m)), "A": float(m[hg < ag].sum())},
        "BTTS": {"Y": float(m[(hg > 0) & (ag > 0)].sum())},
    }
    out["BTTS"]["N"] = 1 - out["BTTS"]["Y"]
    for line in (1.5, 2.5, 3.5):
        o = float(m[tot > line].sum())
        out[f"OU{line}"] = {"O": o, "U": 1 - o}
    return out


def sharpen(probs: dict[str, float], k: float) -> dict[str, float]:
    """p_i^k normalisiert. k > 1 macht Prognosen entschiedener; das regularisierte
    Modell ist leicht unterkonfident (Backtest-Optimum k ≈ 1,15)."""
    q = {s: p ** k for s, p in probs.items()}
    t = sum(q.values())
    return {s: v / t for s, v in q.items()}


def devig(odds, method: str = "power") -> np.ndarray:
    """Faire Wahrscheinlichkeiten aus einem vollständigen Quotensatz.

    'power' (p_i = (1/o_i)^k, Σp = 1) berücksichtigt den Favoriten-Außenseiter-
    Effekt besser als einfaches Normalisieren ('proportional')."""
    inv = 1.0 / np.asarray(odds, float)
    if method == "proportional" or inv.sum() <= 1.0:
        return inv / inv.sum()
    k = brentq(lambda k: np.sum(inv ** k) - 1.0, 1.0, 10.0)
    return inv ** k


def overround(odds) -> float:
    return float(np.sum(1.0 / np.asarray(odds, float)) - 1.0)
