"""Einheitlicher Backtest-Aufruf für Forschung und Robustheitstests."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from ..backtesting.costs import CostModel
from ..backtesting.engine import BacktestEngine, BacktestResult
from ..backtesting.metadata import run_metadata
from ..backtesting.metrics import compute_metrics
from ..config.schema import Config, StrategySlot
from ..data import MarketSeries
from ..portfolio.allocator import SlotFrames, StrategyPortfolio, compute_slot
from ..portfolio.correlation import RiskStats
from ..risk.engine import RiskEngine


class Prepared:
    """Einmal vorberechnete Signale/Statistiken, wiederverwendbar für viele Zeiträume und Stresstests."""

    def __init__(self, cfg: Config, markets: dict[str, MarketSeries], slots: list[StrategySlot]) -> None:
        self.cfg = cfg
        self.markets = markets
        self.slots = slots
        self.computed: list[SlotFrames] = [compute_slot(s, markets) for s in slots]
        tf = next(iter(markets.values())).timeframe
        self.timeframe = tf
        self.stats = RiskStats({s: m.ohlcv["close"] for s, m in markets.items()}, tf,
                               cfg.risk.correlation_lookback_days)


def run(
    prep: Prepared,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    cost_mult: tuple[float, float] = (1.0, 1.0),
    delay_bars: int | None = None,
    risk_overrides: dict | None = None,
    label: str = "",
) -> BacktestResult:
    cfg = prep.cfg
    risk_cfg = replace(cfg.risk, **(risk_overrides or {}))
    costs = CostModel.from_config(cfg.costs).stressed(*cost_mult)
    mmr = {i.symbol: i.maintenance_margin_rate for i in cfg.instruments if i.symbol in prep.markets}
    engine = BacktestEngine(
        prep.markets, costs, cfg.initial_equity, mmr,
        delay_bars=cfg.execution.delay_bars if delay_bars is None else delay_bars,
        min_notional=cfg.risk.min_trade_notional, start=start, end=end,
    )
    stats_view = _StatsView(prep.stats, engine.index)
    risk = RiskEngine(risk_cfg, replace(cfg.costs, taker_fee=costs.taker_fee, slippage_bps=costs.slippage_bps),
                      mmr, stats_view)
    model = StrategyPortfolio(prep.markets, prep.slots, risk, cfg.regime, computed=prep.computed)
    meta = run_metadata(cfg, prep.markets, {
        "label": label, "period": [str(engine.index[0]), str(engine.index[-1])],
        "slots": [s.__dict__ for s in prep.slots], "cost_mult": list(cost_mult),
        "delay_bars": engine.delay, "risk_overrides": risk_overrides or {},
    })
    res = engine.run(model, meta)
    res.metrics["risk_blocks"] = dict(risk.state.blocks)
    res.metrics["kill_switch"] = risk.state.kill_reason
    res.metrics["benchmark"] = benchmark(prep.markets, engine.index, cfg.initial_equity, prep.timeframe)
    return res


class _StatsView:
    """RiskStats über die Zeitstempel der Engine abfragen (Stats liegen auf dem vollen Index)."""

    def __init__(self, stats: RiskStats, index: pd.DatetimeIndex) -> None:
        self.stats = stats
        self.map = stats.index.get_indexer(index)

    def volatility(self, s, i):
        j = self.map[i]
        return self.stats.volatility(s, j) if j >= 0 else float("nan")

    def covariance(self, i, syms):
        j = self.map[i]
        return self.stats.covariance(j, syms) if j >= 0 else None


def benchmark(markets: dict[str, MarketSeries], index: pd.DatetimeIndex, initial: float, tf: str) -> dict:
    """Gleichgewichtetes Buy & Hold (1x, ohne Kosten) als Vergleich."""
    rets = []
    for m in markets.values():
        c = m.ohlcv["close"].reindex(index).ffill()
        rets.append(c.pct_change().fillna(0.0))
    port = pd.concat(rets, axis=1).mean(axis=1)
    eq = initial * (1 + port).cumprod()
    empty = pd.DataFrame(columns=["net_pnl"])
    exp = pd.DataFrame({"gross": np.ones(len(index)), "net": np.ones(len(index))}, index=index)
    m = compute_metrics(eq, empty, exp, tf, initial)
    return {k: m[k] for k in ("total_return", "cagr", "sharpe", "sortino", "max_drawdown", "calmar")}
