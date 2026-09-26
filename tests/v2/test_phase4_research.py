"""Phase 4: Splits, Walk-Forward, Sensitivität, Monte Carlo, Pipeline (Funktion, nicht Performance)."""

import numpy as np
import pandas as pd
import pytest

from quantbot.config.schema import Config, RegimeConfig
from quantbot.data import MarketSeries
from quantbot.data.synthetic import synthetic_funding, synthetic_ohlcv
from quantbot.research.montecarlo import monte_carlo
from quantbot.research.pipeline import Researcher
from quantbot.research.report import write_report
from quantbot.research.sensitivity import grid_combos, neighborhood_scores
from quantbot.research.splits import make_splits, walk_forward_windows


def test_splits_are_ordered_and_disjoint():
    idx = pd.date_range("2020-01-01", periods=1000, freq="1D", tz="UTC")
    sp = make_splits(idx, 0.6, 0.2, warmup_days=100)
    assert sp.train.start == idx[0] + pd.Timedelta(days=100)
    assert sp.train.end == sp.validation.start and sp.validation.end == sp.oos.start
    assert sp.oos.end > idx[-1]
    assert sp.research.end == sp.oos.start  # Forschung endet vor OOS


def test_walk_forward_never_reaches_beyond_period():
    idx = pd.date_range("2020-01-01", periods=1000, freq="1D", tz="UTC")
    sp = make_splits(idx, 0.6, 0.2)
    wins = walk_forward_windows(sp.research, 365, 90)
    assert wins and all(te.end <= sp.research.end for _, te in wins)
    for (tr, te), (tr2, te2) in zip(wins, wins[1:]):
        assert te.end == te2.start and tr.end == te.start


def test_grid_sampling_is_reproducible_and_keeps_defaults():
    grid = {"a": [1, 2, 3, 4], "b": [10, 20, 30]}
    c1 = grid_combos(grid, {"a": 2, "b": 20}, max_combos=5, seed=1)
    c2 = grid_combos(grid, {"a": 2, "b": 20}, max_combos=5, seed=1)
    assert c1 == c2 and len(c1) == 5
    assert any(p == {"a": 2, "b": 20} for _, p in c1)


def test_neighborhood_penalizes_isolated_peak():
    grid = {"n": [1, 2, 3, 4, 5, 6, 7]}
    rows = pd.DataFrame({"idx": [(i,) for i in range(7)], "params": [{"n": i} for i in range(7)],
                         "sharpe": [0.0, 0.0, 3.0, 0.0, 1.5, 1.5, 1.5]})
    r = neighborhood_scores(rows, grid)
    assert r.iloc[5] > r.iloc[2]  # Plateau schlägt Einzelspitze


def test_monte_carlo_properties():
    rng = np.random.default_rng(0)
    good = rng.normal(0.01, 0.02, 200)
    mc = monte_carlo(good, runs=500, seed=1)
    assert mc["prob_loss"] < 0.05 and mc["return_p50"] > 0
    assert mc["max_dd_p95"] <= mc["max_dd_p50"] <= 0
    bad = rng.normal(-0.005, 0.02, 200)
    assert monte_carlo(bad, runs=500, seed=1)["prob_loss"] > 0.8
    assert monte_carlo(good[:3])["runs"] == 0


def trending_universe(tf="1d", days=1400):
    n = days if tf == "1d" else days * 6
    out = {}
    for k, s in enumerate(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]):
        df = synthetic_ohlcv(n, tf, seed=10 + k, annual_vol=0.5, trend_blocks_days=90, trend_drift=2.0,
                             start="2020-01-01")
        out[s] = MarketSeries(s, tf, df, synthetic_funding(df.index, seed=k), f"t{k}", True)
    return out


def test_pipeline_runs_all_stages_on_trending_data(tmp_path):
    cfg = Config()
    cfg.regime = RegimeConfig(trend_ma_days=50, vol_rank_days=200)
    cfg.research.monte_carlo_runs = 200
    cfg.research.max_grid = 8
    cfg.research.wf_train_days, cfg.research.wf_test_days = 300, 120
    r = Researcher(cfg, trending_universe())
    result = r.run_all(["ema_trend", "ts_momentum", "rsi_reversion"])
    reps = {x.name: x for x in result["reports"]}
    trend = reps["ts_momentum"]
    # Auf Daten mit eingebauten Trends muss Trendfolge mindestens die Stufen A-C erreichen
    stage_names = [c.name for c in trend.checks]
    assert any(n.startswith("C:") for n in stage_names), trend.checks
    # OOS nur für Kandidaten, die alles vor OOS bestanden haben
    for rep in result["reports"] + result["ensembles"]:
        pre = [c for c in rep.checks if not c.name.startswith("F:")]
        if rep.oos is not None:
            assert all(c.passed for c in pre)
        else:
            assert not all(c.passed for c in pre) or rep.family == "ensemble"
    meta = {s: {"rows": 1, "hash": "x", "synthetic": True, "funding_history": True} for s in r.markets}
    path = write_report(result, meta, tmp_path)
    text = path.read_text()
    assert "SYNTHETISCHE DATEN" in text and "ts_momentum" in text
    assert (tmp_path / "results.json").exists()
