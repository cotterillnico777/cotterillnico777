"""Monte-Carlo-Analyse auf Trade-Ebene: Wie schlimm hätte es mit Pech werden können?"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _max_dd(path: np.ndarray) -> np.ndarray:
    """Maximaler Drawdown je Zeile einer Matrix kumulierter Kapitalwerte."""
    peak = np.maximum.accumulate(path, axis=1)
    return (path / peak - 1).min(axis=1)


def monte_carlo(trade_returns: np.ndarray, runs: int = 1000, seed: int = 42,
                extra_cost: float = 0.0) -> dict:
    """Trade-Renditen (Anteil des Kontos je Trade) neu ziehen bzw. mischen.

    bootstrap: Ziehen mit Zurücklegen (andere Trade-Mischung, gleiche Anzahl)
    shuffle:   gleiche Trades, andere Reihenfolge (nur Drawdown ändert sich)
    extra_cost: zufällige Zusatzkosten je Trade, gleichverteilt in [0, 2*extra_cost]
    """
    r = np.asarray(trade_returns, float)
    r = r[np.isfinite(r)]
    if len(r) < 5:
        return {"runs": 0, "note": "zu wenige Trades für Monte Carlo"}
    rng = np.random.default_rng(seed)
    n = len(r)
    boot = r[rng.integers(0, n, size=(runs, n))]
    if extra_cost:
        boot = boot - rng.uniform(0, 2 * extra_cost, size=boot.shape)
    boot_path = np.cumprod(1 + np.clip(boot, -0.99, None), axis=1)
    shuf = np.array([rng.permutation(r) for _ in range(runs)])
    shuf_path = np.cumprod(1 + np.clip(shuf, -0.99, None), axis=1)
    b_dd, s_dd = _max_dd(boot_path), _max_dd(shuf_path)
    final = boot_path[:, -1] - 1
    return {
        "runs": runs,
        "trades": n,
        "return_p05": float(np.quantile(final, 0.05)),
        "return_p50": float(np.quantile(final, 0.50)),
        "return_p95": float(np.quantile(final, 0.95)),
        "prob_loss": float((final < 0).mean()),
        "max_dd_p50": float(np.quantile(b_dd, 0.50)),
        "max_dd_p95": float(np.quantile(b_dd, 0.05)),  # 95 % der Fälle besser als dieser Wert
        "shuffle_max_dd_p95": float(np.quantile(s_dd, 0.05)),
        "historical_order_max_dd": float(_max_dd(np.cumprod(1 + r)[None, :])[0]),
    }


def trade_returns(trades: pd.DataFrame) -> np.ndarray:
    if trades is None or trades.empty:
        return np.array([])
    return (trades["return_pct"] / 100).values
