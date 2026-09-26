"""Parameter-Scan und Walk-Forward-Analyse.

Idee: Parameter werden immer nur auf einem *Trainingsfenster* ausgewählt und
dann auf dem direkt folgenden, *ungesehenen* Testfenster geprüft. Nur die
Ergebnisse der Testfenster (Out-of-Sample) zählen. So sieht man, ob eine
Optimierung echten Nutzen bringt oder nur die Vergangenheit auswendig lernt.

Gegen Zufallstreffer wird nicht die beste Einzelkombination gewählt, sondern
die mit dem besten Durchschnitt über sich und ihre Nachbarn im Raster
("robuster Score"). Ein einsamer Spitzenwert inmitten schlechter Nachbarn
fällt dadurch heraus.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .backtest import periods_per_year, run_backtest
from .config import Config
from .strategies import STRATEGIES, create_strategy

GridIndex = tuple[int, ...]


# ------------------------------------------------------------------ raster
def strategy_grid(name: str, cfg: Config) -> dict[str, list[Any]]:
    grid = dict(STRATEGIES[name].param_grid)
    grid.update(cfg.optimize.grids.get(name, {}))
    unknown = set(grid) - set(STRATEGIES[name].default_params)
    if unknown:
        raise ValueError(f"Unbekannte Rasterparameter für {name}: {sorted(unknown)}")
    return grid


def grid_combos(grid: dict[str, list[Any]]) -> list[tuple[GridIndex, dict[str, Any]]]:
    keys = list(grid)
    out = []
    for idx in itertools.product(*(range(len(grid[k])) for k in keys)):
        out.append((idx, {k: grid[k][i] for k, i in zip(keys, idx)}))
    return out


@dataclass
class Candidate:
    idx: GridIndex
    params: dict[str, Any]
    signals: pd.Series


def precompute(df: pd.DataFrame, name: str, grid: dict[str, list[Any]]) -> list[Candidate]:
    """Signale jeder gültigen Kombination einmal auf der ganzen Historie berechnen.

    Das ist erlaubt, weil Strategien keinen Blick in die Zukunft haben dürfen
    (per Test abgesichert). Fenster schneiden die Signale dann nur aus.
    """
    cands = []
    for idx, params in grid_combos(grid):
        try:
            strat = create_strategy(name, params)
        except ValueError:
            continue  # z. B. fast >= slow
        cands.append(Candidate(idx, params, strat.generate_signals(df)))
    if not cands:
        raise ValueError(f"Keine gültige Parameterkombination für {name}")
    return cands


# ------------------------------------------------------------- bewertung
def score(metrics: dict[str, float], metric: str) -> float:
    if metric == "sharpe":
        return metrics["sharpe"]
    if metric == "return":
        return metrics["total_return_pct"]
    if metric == "calmar":
        return metrics["total_return_pct"] / max(abs(metrics["max_drawdown_pct"]), 1.0)
    raise ValueError(metric)


def evaluate(
    df: pd.DataFrame, cands: list[Candidate], cfg: Config, name: str
) -> pd.DataFrame:
    """Jede Kombination auf ``df`` backtesten. Eine Zeile pro Kombination."""
    strat = create_strategy(name)  # nur für run_backtest-Signatur
    rows = []
    for c in cands:
        res = run_backtest(
            df, strat, cfg.risk, cfg.backtest, cfg.timeframe, signals=c.signals.loc[df.index]
        )
        m = res.metrics
        valid = m["trades"] >= cfg.optimize.min_trades
        rows.append(
            {
                "idx": c.idx,
                "params": c.params,
                "score": score(m, cfg.optimize.metric) if valid else math.nan,
                "return_pct": m["total_return_pct"],
                "max_dd_pct": m["max_drawdown_pct"],
                "sharpe": m["sharpe"],
                "trades": m["trades"],
            }
        )
    out = pd.DataFrame(rows)
    out["robust"] = robust_scores(out)
    return out


def robust_scores(rows: pd.DataFrame) -> pd.Series:
    """Mittelwert des Scores über die Kombination und alle Rasternachbarn (±1 Schritt).

    Nachbarn mit zu wenigen Trades zählen mit dem schlechtesten gültigen Score,
    damit Randlagen nicht bevorzugt werden. Nicht erlaubte Kombinationen
    (z. B. fast >= slow) fehlen im Raster und werden übersprungen.
    """
    valid = rows["score"].dropna()
    if valid.empty:
        return pd.Series(math.nan, index=rows.index)
    penalty = float(valid.min())
    by_idx = dict(zip(rows["idx"], rows["score"]))
    # Kategorische Parameter (z. B. kind=ema/sma) haben keine Nachbarn
    first = rows["params"].iloc[0]
    steps = [
        (-1, 0, 1) if isinstance(v, (int, float)) and not isinstance(v, bool) else (0,)
        for v in first.values()
    ]
    out = []
    for idx, s in zip(rows["idx"], rows["score"]):
        if math.isnan(s):
            out.append(math.nan)
            continue
        vals = []
        for delta in itertools.product(*steps):
            n = tuple(i + d for i, d in zip(idx, delta))
            if n in by_idx:
                v = by_idx[n]
                vals.append(penalty if math.isnan(v) else v)
        out.append(float(np.mean(vals)))
    return pd.Series(out, index=rows.index)


def best_row(rows: pd.DataFrame) -> pd.Series | None:
    ranked = rows.dropna(subset=["robust"])
    if ranked.empty:
        return None
    return ranked.sort_values(["robust", "score"], ascending=False).iloc[0]


# ---------------------------------------------------------- walk-forward
@dataclass
class Fold:
    train_start: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    params: dict[str, Any] | None
    train_score: float
    test_score: float
    test_return_pct: float
    buy_hold_pct: float
    trades: int
    default_return_pct: float


@dataclass
class WalkForwardResult:
    strategy: str
    market: str
    folds: list[Fold]
    equity: pd.Series  # verkettete Out-of-Sample-Kapitalkurve
    summary: dict[str, float] = field(default_factory=dict)

    def fold_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Test ab": [f.test_start.strftime("%Y-%m-%d") for f in self.folds],
                "Parameter": [_fmt(f.params) for f in self.folds],
                "Score Train": [round(f.train_score, 2) for f in self.folds],
                "Score Test": [round(f.test_score, 2) for f in self.folds],
                "Test %": [round(f.test_return_pct, 2) for f in self.folds],
                "Standard %": [round(f.default_return_pct, 2) for f in self.folds],
                "Buy&Hold %": [round(f.buy_hold_pct, 1) for f in self.folds],
                "Trades": [f.trades for f in self.folds],
            }
        )


def _fmt(params: dict[str, Any] | None) -> str:
    if not params:
        return "(nichts gültig -> kein Handel)"
    return ", ".join(f"{k}={v}" for k, v in params.items())


def windows(
    index: pd.DatetimeIndex, train_days: int, test_days: int
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    train, test = pd.Timedelta(days=train_days), pd.Timedelta(days=test_days)
    out = []
    test_start = index[0] + train
    while test_start < index[-1]:
        test_end = min(test_start + test, index[-1] + pd.Timedelta(seconds=1))
        # Zu kurze Resttestfenster verwerfen
        if test_end - test_start >= test / 2:
            out.append((test_start - train, test_start, test_end))
        test_start += test
    return out


def walk_forward(
    df: pd.DataFrame, name: str, cfg: Config, market: str = ""
) -> WalkForwardResult:
    o = cfg.optimize
    cands = precompute(df, name, strategy_grid(name, cfg))
    default_signals = create_strategy(name).generate_signals(df)
    strat = create_strategy(name)
    wins = windows(df.index, o.train_days, o.test_days)
    if not wins:
        raise ValueError(
            f"Zu wenig Historie ({(df.index[-1] - df.index[0]).days} Tage) für "
            f"train_days={o.train_days} + test_days={o.test_days}"
        )

    folds: list[Fold] = []
    pieces: list[pd.Series] = []
    capital = cfg.backtest.initial_balance
    for train_start, test_start, test_end in wins:
        train = df[(df.index >= train_start) & (df.index < test_start)]
        test = df[(df.index >= test_start) & (df.index < test_end)]
        if len(train) < 2 or len(test) < 2:
            continue
        rows = evaluate(train, cands, cfg, name)
        best = best_row(rows)
        if best is None:
            # Keine Kombination erfüllt min_trades: in diesem Fenster nicht handeln
            sig = pd.Series(0, index=df.index)
            params, train_score = None, math.nan
        else:
            params, train_score = best["params"], float(best["score"])
            sig = next(c.signals for c in cands if c.idx == best["idx"])
        res = run_backtest(test, strat, cfg.risk, cfg.backtest, cfg.timeframe, signals=sig)
        base = run_backtest(
            test, strat, cfg.risk, cfg.backtest, cfg.timeframe, signals=default_signals
        )
        m = res.metrics
        folds.append(
            Fold(
                train_start,
                test_start,
                test_end,
                params,
                train_score,
                score(m, o.metric),
                m["total_return_pct"],
                m["buy_hold_pct"],
                int(m["trades"]),
                base.metrics["total_return_pct"],
            )
        )
        piece = res.equity / cfg.backtest.initial_balance * capital
        capital = float(piece.iloc[-1])
        pieces.append(piece)

    equity = pd.concat(pieces)
    return WalkForwardResult(name, market, folds, equity, _summary(df, folds, equity, cfg))


def _summary(df, folds: list[Fold], equity: pd.Series, cfg: Config) -> dict[str, float]:
    init = cfg.backtest.initial_balance
    rets = equity.pct_change().dropna()
    std = rets.std()
    sharpe = (
        rets.mean() / std * math.sqrt(periods_per_year(cfg.timeframe)) if std and std > 0 else 0.0
    )
    oos = df[(df.index >= folds[0].test_start) & (df.index < folds[-1].test_end)]
    default_total = float(np.prod([1 + f.default_return_pct / 100 for f in folds]) - 1) * 100
    train_scores = [f.train_score for f in folds if not math.isnan(f.train_score)]
    return {
        "oos_return_pct": (equity.iloc[-1] / init - 1) * 100,
        "default_return_pct": default_total,
        "buy_hold_pct": (oos["close"].iloc[-1] / oos["open"].iloc[0] - 1) * 100,
        "oos_sharpe": float(sharpe),
        "oos_max_dd_pct": float(((equity - equity.cummax()) / equity.cummax()).min() * 100),
        "folds": len(folds),
        "profitable_folds_pct": sum(f.test_return_pct > 0 for f in folds) / len(folds) * 100,
        "avg_train_score": float(np.mean(train_scores)) if train_scores else math.nan,
        "avg_test_score": float(np.mean([f.test_score for f in folds])),
        "trades": sum(f.trades for f in folds),
        "param_changes": sum(
            1 for a, b in zip(folds, folds[1:]) if a.params != b.params
        ),
    }


# --------------------------------------------------- marktübergreifend
def recommend(
    datasets: dict[str, pd.DataFrame], name: str, cfg: Config
) -> tuple[dict[str, Any] | None, pd.DataFrame]:
    """Parameter, die über *alle* Märkte im Schnitt am robustesten sind.

    Gibt (beste Parameter oder None, Tabelle der Top-Kombinationen) zurück.
    """
    grid = strategy_grid(name, cfg)
    per_market = []
    for market, df in datasets.items():
        rows = evaluate(df, precompute(df, name, grid), cfg, name)
        per_market.append(rows.set_index("idx")[["params", "robust", "return_pct"]].add_suffix(f"|{market}"))
    table = pd.concat(per_market, axis=1)
    robust_cols = [c for c in table.columns if c.startswith("robust|")]
    ret_cols = [c for c in table.columns if c.startswith("return_pct|")]
    table["robust_avg"] = table[robust_cols].mean(axis=1, skipna=False)
    table["return_avg_pct"] = table[ret_cols].mean(axis=1)
    table["params"] = table[f"params|{next(iter(datasets))}"]
    table = table.dropna(subset=["robust_avg"]).sort_values("robust_avg", ascending=False)
    top = table[["params", "robust_avg", "return_avg_pct"]].head(5).copy()
    top["params"] = top["params"].map(_fmt)
    top.columns = ["Parameter", "Robust-Score Ø", "Rendite Ø %"]
    top = top.round({"Robust-Score Ø": 3, "Rendite Ø %": 2})
    best = table["params"].iloc[0] if not table.empty else None
    return best, top.reset_index(drop=True)
