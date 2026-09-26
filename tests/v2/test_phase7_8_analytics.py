"""Phase 7/8: Analytics, Backtest-vs-Forward, Hebel-Skalierung, Live-Readiness."""

import json

import numpy as np
import pandas as pd
import pytest

from quantbot.analytics import breakdown, drawdown_episodes, enrich, full_report, winner_loser_profile
from quantbot.config.schema import Config, RegimeConfig, StrategySlot
from quantbot.core.types import Mode
from quantbot.data import MarketSeries
from quantbot.data.synthetic import synthetic_funding, synthetic_ohlcv
from quantbot.execution.trader import Trader
from quantbot.monitoring.journal import Journal
from quantbot.monitoring.readiness import format_readiness, readiness
from quantbot.research.forward import compare_forward, format_forward
from quantbot.research.leverage import risk_scaling
from quantbot.research.runner import Prepared
from quantbot.research.splits import Period

from test_phase6_execution import paper_setup


def sample_trades():
    rng = np.random.default_rng(0)
    n = 60
    return pd.DataFrame({
        "symbol": rng.choice(["BTC", "ETH"], n), "strategy": "s@1", "direction": rng.choice(["long", "short"], n),
        "entry_time": pd.date_range("2024-01-01", periods=n, freq="7h", tz="UTC"),
        "exit_time": pd.date_range("2024-01-02", periods=n, freq="7h", tz="UTC"),
        "net_pnl": rng.normal(1, 10, n), "regime": rng.choice(["bull|high", "bear|low"], n),
        "signal_strength": rng.uniform(0.1, 1, n), "leverage": rng.uniform(0.2, 2, n),
        "exit_reason": rng.choice(["signal", "stop_loss"], n), "mfe_pct": rng.uniform(0, 5, n),
        "features": [json.dumps({"x": float(v)}) for v in rng.normal(0, 1, n)],
    })


def test_analytics_breakdowns_and_profile():
    t = enrich(sample_trades())
    assert {"entry_hour_utc", "trend_regime", "strength_bucket", "feat_x"} <= set(t.columns)
    b = breakdown(t, "symbol")
    assert set(b.index) == {"BTC", "ETH"} and b["trades"].sum() == 60
    prof = winner_loser_profile(t)
    assert "mfe_pct" in prof.index
    txt = full_report(sample_trades(), pd.Series([100, 90, 95, 120.0],
                                                  index=pd.date_range("2024", periods=4, tz="UTC")))
    assert "Nach Trend-Regime" in txt and "Größte Drawdowns" in txt


def test_drawdown_episodes():
    eq = pd.Series([100, 110, 90, 95, 115, 100, 120.0], index=pd.date_range("2024", periods=7, tz="UTC"))
    ep = drawdown_episodes(eq)
    assert ep.iloc[0]["tiefe"] == pytest.approx(90 / 110 - 1)
    assert len(ep) == 2


def test_risk_scaling_shows_drawdown_growth():
    cfg = Config()
    cfg.regime = RegimeConfig(trend_ma_days=20, vol_rank_days=60)
    mk = {}
    for k, s in enumerate(["BTC/USDT:USDT", "ETH/USDT:USDT"]):
        df = synthetic_ohlcv(24 * 300, "1h", seed=k, trend_blocks_days=30)
        mk[s] = MarketSeries(s, "1h", df, synthetic_funding(df.index), "h", True)
    prep = Prepared(cfg, mk, [StrategySlot("ema_trend", {"fast": 20, "slow": 60}, timeframe="1h")])
    idx = mk["BTC/USDT:USDT"].ohlcv.index
    rows = risk_scaling(prep, Period("x", idx[0], idx[-1]))
    assert [r["risk_multiplier"] for r in rows] == [0.5, 1.0, 2.0, 4.0]
    exp = [r["avg_gross_exposure"] for r in rows]
    assert exp[0] < exp[1] < exp[3]  # mehr Risiko = mehr Exposure
    assert all(r["max_leverage"] <= 5 for r in rows)


def test_forward_compare_paper_matches_backtest(tmp_path):
    feed, cfg, ex, frames = paper_setup(tmp_path)
    idx = frames["BTC/USDT:USDT"].index
    journal = Journal(tmp_path / "j.sqlite")
    clock = {"t": None}
    trader = Trader(cfg, Mode.PAPER, ex, journal, clock=lambda: clock["t"], sleep=lambda s: None)
    for k in range(200, 600):
        feed.now = idx[k] + pd.Timedelta(minutes=5)
        clock["t"] = feed.now.to_pydatetime()
        trader.tick()
    markets = {s: MarketSeries(s, "4h", frames[s].iloc[:600], None, "x") for s in frames}
    r = compare_forward(cfg, journal, markets)
    assert r["signal_drift"]["compared"] > 100
    # Gleiche Strategie + gleiche abgeschlossene Kerzen -> (fast) identische Signale
    assert r["signal_drift"]["share_identical"] > 0.8
    assert r["trades"]["paper"] > 0 and r["trades"]["matched"] > 0
    assert "Signal-Drift" in format_forward(r)


def test_readiness_is_not_ready_without_evidence(tmp_path):
    cfg = Config()
    cfg.strategies = [StrategySlot("ema_trend", {}, timeframe="4h")]
    items = readiness(cfg, None, None, None)
    text = format_readiness(items)
    assert "NICHT BEREIT" in text and "LIVE wird hierdurch nicht aktiviert" in text
    assert cfg.live.enabled is False


def test_readiness_rejects_synthetic_research(tmp_path):
    cfg = Config()
    cfg.strategies = [StrategySlot("ema_trend", {"fast": 20}, timeframe="4h")]
    res = {"data": {"X": {"synthetic": True}}, "reports": [
        {"name": "ema_trend", "params": {"fast": 20}, "oos": {"sharpe": 1}, "checks": [{"passed": True}]}]}
    p = tmp_path / "results.json"
    p.write_text(json.dumps(res))
    items = readiness(cfg, str(p), None, None)
    names = {i.name: i.ok for i in items}
    assert names["Forschung bestanden: ema_trend"] is True
    assert names["Forschung auf echten Daten"] is False


def test_ml_meta_filter_detects_signal_and_rejects_noise():
    from quantbot.research.ml import auc, evaluate_meta_filter

    rng = np.random.default_rng(3)

    def trades(n, informative):
        x = rng.normal(0, 1, n)
        pnl = (2 * x if informative else 0) + rng.normal(0, 1, n)
        return pd.DataFrame({"net_pnl": pnl, "signal_strength": rng.uniform(0.1, 1, n), "direction": "long",
                             "regime": "bull|normal", "features": [json.dumps({"x": float(v)}) for v in x]})

    good = evaluate_meta_filter(trades(300, True), trades(150, True))
    assert good["val_auc"] > 0.75 and good["use_ml"]
    noise = evaluate_meta_filter(trades(300, False), trades(150, False))
    assert not noise["use_ml"]
    assert evaluate_meta_filter(trades(5, True), trades(5, True))["use_ml"] is False
    assert auc(np.array([0, 0, 1, 1.0]), np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
