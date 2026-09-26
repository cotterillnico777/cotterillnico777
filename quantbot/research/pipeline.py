"""Forschungspipeline: Screening -> Validierung -> Walk-Forward -> Stress -> Ensemble -> OOS.

Der Out-of-Sample-Zeitraum wird genau einmal und nur für Kandidaten ausgewertet, die alle
vorherigen Stufen bestanden haben. Negative Ergebnisse werden vollständig berichtet.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..config.schema import Config, StrategySlot
from ..data import MarketSeries
from ..strategies import STRATEGIES
from .montecarlo import monte_carlo, trade_returns
from .runner import Prepared, Shared, run
from .sensitivity import grid_combos, neighborhood_scores, summarize_grid
from .splits import Period, Splits, make_splits, walk_forward_windows

log = logging.getLogger(__name__)

TREND_FAMILIES = {"trend", "momentum", "volatility", "structure"}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class CandidateReport:
    name: str
    family: str
    params: dict
    stages: dict[str, Any] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    oos: dict | None = None

    @property
    def passed_pre_oos(self) -> bool:
        return all(c.passed for c in self.checks)

    def check(self, name: str, passed: bool, detail: str) -> bool:
        self.checks.append(Check(name, bool(passed), detail))
        return bool(passed)


def _m(res) -> dict:
    keep = ("total_return", "cagr", "sharpe", "sortino", "calmar", "max_drawdown", "profit_factor",
            "expectancy_r", "win_rate", "payoff_ratio", "trades", "fees", "funding", "slippage_cost",
            "avg_gross_exposure", "time_in_market", "longest_losing_streak", "recovery_days",
            "liquidations", "avg_leverage_at_entry", "max_leverage_at_entry", "turnover_per_year",
            "var_95_daily", "es_95_daily", "longest_underwater_days")
    m = {k: res.metrics.get(k) for k in keep}
    m["benchmark_sharpe"] = res.metrics.get("benchmark", {}).get("sharpe")
    m["benchmark_return"] = res.metrics.get("benchmark", {}).get("total_return")
    m["benchmark_max_dd"] = res.metrics.get("benchmark", {}).get("max_drawdown")
    return m


def _fin(x, default=float("-inf")) -> float:
    return x if isinstance(x, (int, float)) and math.isfinite(x) else default


class Researcher:
    def __init__(self, cfg: Config, markets: dict[str, MarketSeries]) -> None:
        self.cfg = cfg
        self.markets = markets
        self.tf = next(iter(markets.values())).timeframe
        self.shared = Shared(cfg, markets)
        idx = None
        for m in markets.values():
            idx = m.ohlcv.index if idx is None else idx.union(m.ohlcv.index)
        r = cfg.research
        self.splits: Splits = make_splits(idx, r.train_frac, r.validation_frac,
                                          warmup_days=max(cfg.regime.trend_ma_days, 60))
        self._prep_cache: dict[str, Prepared] = {}

    # --------------------------------------------------------------- helpers
    def prep(self, slots: list[StrategySlot]) -> Prepared:
        key = repr([(s.name, sorted(s.params.items()), s.weight, s.regimes) for s in slots])
        if key not in self._prep_cache:
            self._prep_cache[key] = Prepared(self.cfg, self.markets, slots, self.shared)
        return self._prep_cache[key]

    def evaluate(self, slots, period: Period, **kw):
        return run(self.prep(slots), start=period.start, end=period.end, label=period.name, **kw)

    # -------------------------------------------------------------- Stufen
    def screen(self, name: str) -> tuple[pd.DataFrame, dict]:
        cls = STRATEGIES[name]
        rows = []
        for idx, params in grid_combos(cls.param_grid, cls.default_params, self.cfg.research.max_grid,
                                       self.cfg.research.seed):
            try:
                cls(**params)
            except ValueError:
                continue  # ungültige Kombination (z. B. fast >= slow)
            slot = StrategySlot(name, params, timeframe=self.tf)
            try:
                res = self.evaluate([slot], self.splits.train)
            except ValueError as exc:
                log.warning("%s %s übersprungen: %s", name, params, exc)
                continue
            m = res.metrics
            sharpe = m["sharpe"] if m["trades"] >= 3 else float("nan")
            rows.append({"idx": idx, "params": params, "sharpe": sharpe, "trades": m["trades"],
                         "total_return": m["total_return"], "max_drawdown": m["max_drawdown"]})
        grid = pd.DataFrame(rows)
        if grid.empty:
            return grid, {"combos": 0}
        grid["robust"] = neighborhood_scores(grid, cls.param_grid)
        return grid, summarize_grid(grid)

    def walk_forward(self, name: str, fixed_params: dict) -> dict:
        cls = STRATEGIES[name]
        r = self.cfg.research
        windows = walk_forward_windows(self.splits.research, r.wf_train_days, r.wf_test_days)
        combos = [(idx, p) for idx, p in grid_combos(cls.param_grid, cls.default_params, r.max_grid, r.seed)
                  if _valid(cls, p)]
        fixed_rets, adaptive_rets, rows = [], [], []
        for tr, te in windows:
            scores = []
            for idx, p in combos:
                res = self.evaluate([StrategySlot(name, p, timeframe=self.tf)], tr)
                scores.append({"idx": idx, "params": p,
                               "sharpe": res.metrics["sharpe"] if res.metrics["trades"] >= 3 else float("nan")})
            sdf = pd.DataFrame(scores)
            sdf["robust"] = neighborhood_scores(sdf, cls.param_grid)
            best = sdf.loc[sdf["robust"].idxmax()]["params"] if sdf["robust"].notna().any() else fixed_params
            ad = self.evaluate([StrategySlot(name, best, timeframe=self.tf)], te)
            fx = self.evaluate([StrategySlot(name, fixed_params, timeframe=self.tf)], te)
            adaptive_rets.append(ad.equity.pct_change().dropna())
            fixed_rets.append(fx.equity.pct_change().dropna())
            rows.append({"test_start": str(te.start.date()), "adaptive_return": ad.metrics["total_return"],
                         "fixed_return": fx.metrics["total_return"], "adaptive_params": best,
                         "trades_fixed": fx.metrics["trades"]})
        return {"windows": rows, "fixed": _stitch(fixed_rets, self.tf), "adaptive": _stitch(adaptive_rets, self.tf)}

    def stress(self, slots) -> dict:
        r = self.cfg.research
        out = {}
        for f in r.fee_stress:
            out[f"fees_x{f:g}"] = _m(self.evaluate(slots, self.splits.research, cost_mult=(f, 1.0)))
        for s in r.slippage_stress:
            out[f"slippage_x{s:g}"] = _m(self.evaluate(slots, self.splits.research, cost_mult=(1.0, s)))
        for d in r.delay_stress:
            out[f"delay_{d}"] = _m(self.evaluate(slots, self.splits.research, delay_bars=d))
        return out

    def breakdown(self, res) -> dict:
        t = res.trades
        eq = res.equity
        yearly = eq.resample("YE").last().pct_change()
        first_year = eq.resample("YE").last().iloc[:1] / eq.iloc[0] - 1
        yearly = pd.concat([first_year, yearly.iloc[1:]])
        out = {"yearly_return": {str(k.year): float(v) for k, v in yearly.items()}}
        if t.empty or "regime" not in t:
            out["by_regime"] = {}
            return out
        t = t.copy()
        t["trend"] = t["regime"].str.split("|").str[0]
        t["vol"] = t["regime"].str.split("|").str[1]
        agg = {}
        for col in ("trend", "vol"):
            for k, g in t.groupby(col):
                agg[f"{col}:{k}"] = {"trades": int(len(g)), "win_rate": float((g.net_pnl > 0).mean()),
                                     "mean_return_pct": float(g.return_pct.mean()),
                                     "net_pnl": float(g.net_pnl.sum())}
        out["by_regime"] = agg
        return out

    # --------------------------------------------------------------- Ablauf
    def study_strategy(self, name: str) -> CandidateReport:
        r = self.cfg.research
        cls = STRATEGIES[name]
        grid, summary = self.screen(name)
        rep = CandidateReport(name, cls.family, dict(summary.get("robust_params") or cls.default_params))
        rep.stages["A_screen"] = {"summary": summary,
                                  "grid": grid.drop(columns=["idx"]).to_dict("records") if len(grid) else []}
        if grid.empty or summary.get("combos", 0) == 0:
            rep.check("A: Parameterraster auswertbar", False, "keine auswertbaren Kombinationen")
            return rep
        params = rep.params
        slots = [StrategySlot(name, params, timeframe=self.tf)]
        train = self.evaluate(slots, self.splits.train)
        tm = _m(train)
        rep.stages["A_train"] = tm
        ok = rep.check("A: Train Sharpe > 0 und Profit Factor > 1",
                       _fin(tm["sharpe"]) > 0 and _fin(tm["profit_factor"], 0) > 1,
                       f"Sharpe {tm['sharpe']:.2f}, PF {_fmt(tm['profit_factor'])}")
        ok &= rep.check("A: Parameter-Robustheit",
                        summary["positive_share"] >= r.min_positive_grid_share
                        and _fin(summary.get("plateau_ratio"), 0) >= r.min_plateau_ratio,
                        f"{summary['positive_share']:.0%} der Kombinationen Sharpe > 0, "
                        f"Plateau {summary.get('plateau_ratio', float('nan')):.2f}")
        if not ok:
            return rep  # früh abbrechen: kein Grund, Zeit in weitere Stufen zu stecken

        val = self.evaluate(slots, self.splits.validation)
        vm = _m(val)
        rep.stages["B_validation"] = vm
        if not rep.check("B: Validation Sharpe > 0 und PF > 1",
                         _fin(vm["sharpe"]) > 0 and _fin(vm["profit_factor"], 0) > 1,
                         f"Sharpe {vm['sharpe']:.2f}, PF {_fmt(vm['profit_factor'])}, Trades {vm['trades']}"):
            return rep

        wf = self.walk_forward(name, params)
        rep.stages["C_walk_forward"] = wf
        share = np.mean([w["fixed_return"] > 0 for w in wf["windows"]]) if wf["windows"] else 0.0
        if not rep.check("C: Walk-Forward (feste Parameter) Sharpe > 0",
                         _fin(wf["fixed"]["sharpe"]) > 0 and share >= r.wf_min_profitable_share,
                         f"Sharpe {wf['fixed']['sharpe']:.2f}, {share:.0%} Fenster profitabel; "
                         f"adaptiv Sharpe {wf['adaptive']['sharpe']:.2f}"):
            return rep

        self._stage_d(rep, slots)
        return rep

    def _stage_d(self, rep: CandidateReport, slots) -> None:
        r = self.cfg.research
        full = self.evaluate(slots, self.splits.research)
        fm = _m(full)
        rep.stages["D_research_period"] = fm
        rep.check("D: genug Trades", fm["trades"] >= r.min_trades, f"{fm['trades']} Trades (min. {r.min_trades})")
        rep.check("D: Max-Drawdown akzeptabel", fm["max_drawdown"] >= -r.max_drawdown_accept,
                  f"{fm['max_drawdown']:.1%} (Grenze -{r.max_drawdown_accept:.0%})")
        rep.check("D: keine Liquidation", not fm["liquidations"], f"{fm['liquidations']} Liquidationen")
        st = self.stress(slots)
        rep.stages["D_stress"] = st
        for key in ("fees_x2", "slippage_x2", "delay_1"):
            if key in st:
                rep.check(f"D: Stress {key} Sharpe > 0", _fin(st[key]["sharpe"]) > 0,
                          f"Sharpe {st[key]['sharpe']:.2f}, Rendite {st[key]['total_return']:.1%}")
        mc = monte_carlo(trade_returns(full.trades), r.monte_carlo_runs, r.seed,
                         extra_cost=self.cfg.costs.taker_fee)
        rep.stages["D_monte_carlo"] = mc
        if mc.get("runs"):
            rep.check("D: Monte Carlo 95%-Drawdown", mc["max_dd_p95"] >= -r.mc_drawdown_p95_limit,
                      f"{mc['max_dd_p95']:.1%} (Grenze -{r.mc_drawdown_p95_limit:.0%})")
            rep.check("D: Monte Carlo Verlustwahrscheinlichkeit", mc["prob_loss"] <= r.mc_prob_loss_max,
                      f"{mc['prob_loss']:.0%} (max. {r.mc_prob_loss_max:.0%})")
        else:
            rep.check("D: Monte Carlo", False, mc.get("note", "nicht möglich"))
        bd = self.breakdown(full)
        rep.stages["D_breakdown"] = bd
        trend_keys = [k for k in bd["by_regime"] if k.startswith("trend:") and k != "trend:unknown"]
        neg = [k for k in trend_keys if bd["by_regime"][k]["net_pnl"] < 0]
        rep.check("D: übersteht mehrere Marktregime", len(trend_keys) >= 2 and len(neg) < len(trend_keys),
                  f"negativ in: {', '.join(neg) or 'keinem'} von {', '.join(trend_keys) or '-'}")

    def study_ensemble(self, candidates: list[CandidateReport], gated: bool) -> CandidateReport:
        slots = []
        for c in candidates:
            regimes = []
            if gated:
                regimes = ["bull", "bear"] if c.family in TREND_FAMILIES else ["sideways"]
            slots.append(StrategySlot(c.name, c.params, timeframe=self.tf, weight=1.0, regimes=regimes))
        name = "ensemble_regime" if gated else "ensemble_equal"
        rep = CandidateReport(name, "ensemble", {"members": [c.name for c in candidates]})
        train = _m(self.evaluate(slots, self.splits.train))
        val = _m(self.evaluate(slots, self.splits.validation))
        rep.stages["A_train"], rep.stages["B_validation"] = train, val
        rep.check("B: Validation Sharpe > 0", _fin(val["sharpe"]) > 0, f"Sharpe {val['sharpe']:.2f}")
        best_single = max((_fin(c.stages.get("B_validation", {}).get("sharpe")) for c in candidates), default=0)
        rep.stages["best_single_validation_sharpe"] = best_single
        self._stage_d(rep, slots)
        rep.params["slots"] = [s.__dict__ for s in slots]
        return rep

    def final_oos(self, rep: CandidateReport, slots) -> None:
        """Einmalige Auswertung auf dem zurückgehaltenen Zeitraum."""
        res = self.evaluate(slots, self.splits.oos)
        rep.oos = _m(res)
        rep.oos["breakdown"] = self.breakdown(res)
        rep.check("F: Out-of-Sample Sharpe > 0 und Rendite > 0",
                  _fin(rep.oos["sharpe"]) > 0 and _fin(rep.oos["total_return"]) > 0,
                  f"Sharpe {rep.oos['sharpe']:.2f}, Rendite {rep.oos['total_return']:.1%}, "
                  f"Max-DD {rep.oos['max_drawdown']:.1%}")

    def study_safe(self, name: str) -> CandidateReport:
        log.info("Untersuche %s auf %s", name, self.tf)
        try:
            return self.study_strategy(name)
        except ValueError as exc:
            rep = CandidateReport(name, STRATEGIES[name].family, {})
            rep.check("ausführbar", False, str(exc))
            return rep

    def run_all(self, names: list[str], jobs: int = 1) -> dict:
        if jobs > 1 and len(names) > 1:
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor(max_workers=jobs, initializer=_init_worker,
                                     initargs=(self.cfg, self.markets)) as pool:
                reports = list(pool.map(_study_in_worker, names))
        else:
            reports = [self.study_safe(n) for n in names]
        candidates = [r for r in reports if r.passed_pre_oos]
        ensembles = []
        if len(candidates) >= 2:
            ensembles = [self.study_ensemble(candidates, gated=False), self.study_ensemble(candidates, gated=True)]
        finalists = candidates + [e for e in ensembles if e.passed_pre_oos]
        for rep in finalists:
            if rep.family == "ensemble":
                slots = [StrategySlot(**s) for s in rep.params["slots"]]
            else:
                slots = [StrategySlot(rep.name, rep.params, timeframe=self.tf)]
            self.final_oos(rep, slots)
        return {"timeframe": self.tf, "splits": {k: str(getattr(self.splits, k)) for k in ("train", "validation", "oos")},
                "reports": reports, "ensembles": ensembles}


_WORKER: "Researcher | None" = None


def _init_worker(cfg, markets) -> None:
    global _WORKER
    _WORKER = Researcher(cfg, markets)


def _study_in_worker(name: str) -> CandidateReport:
    return _WORKER.study_safe(name)


def _fmt(x) -> str:
    return f"{x:.2f}" if isinstance(x, (int, float)) and math.isfinite(x) else str(x)


def _valid(cls, params) -> bool:
    try:
        cls(**params)
        return True
    except ValueError:
        return False


def _stitch(rets: list[pd.Series], tf: str) -> dict:
    from ..core.timeframes import periods_per_year

    if not rets:
        return {"sharpe": float("nan"), "total_return": float("nan")}
    r = pd.concat(rets)
    std = r.std()
    sharpe = r.mean() / std * math.sqrt(periods_per_year(tf)) if std and std > 0 else 0.0
    eq = (1 + r).cumprod()
    return {"sharpe": float(sharpe), "total_return": float(eq.iloc[-1] - 1),
            "max_drawdown": float((eq / eq.cummax() - 1).min())}
