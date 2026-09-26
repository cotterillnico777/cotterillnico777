"""Phase 3: Strategien, Regime, Portfolio-Kombination."""

import numpy as np
import pandas as pd
import pytest

from quantbot.config.schema import Config, RegimeConfig, StrategySlot
from quantbot.data import MarketSeries
from quantbot.data.synthetic import synthetic_funding, synthetic_ohlcv
from quantbot.regimes import detect_regimes, regime_allows
from quantbot.research.runner import Prepared, run
from quantbot.strategies import STRATEGIES, StrategyContext, create
from quantbot.strategies.base import higher_tf


def universe(n=24 * 200, tf="1h", seed=0):
    out = {}
    for k, s in enumerate(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]):
        df = synthetic_ohlcv(n, tf, seed=seed + k, regime_switch=True)
        out[s] = MarketSeries(s, tf, df, synthetic_funding(df.index, seed=seed + k), f"h{k}", True)
    return out


MK = universe()


def ctx_for(sym, mk, cut=None):
    closes = {s: (m.ohlcv["close"] if cut is None else m.ohlcv["close"].iloc[:cut]) for s, m in mk.items()}
    f = mk[sym].funding["rate"]
    if cut is not None:
        f = f[f.index <= mk[sym].ohlcv.index[cut - 1]]
    return StrategyContext(sym, "1h", closes, f)


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_strategy_has_no_lookahead_and_valid_output(name):
    sym = "ETH/USDT:USDT"
    strat = create(name)
    df = MK[sym].ohlcv
    full = strat.compute(df, ctx_for(sym, MK))
    assert set(["signal", "stop_distance", "take_profit_distance"]) <= set(full.columns)
    assert full["signal"].between(-1, 1).all()
    active = full["signal"] != 0
    assert active.any(), f"{name} erzeugt auf 200 Tagen kein einziges Signal"
    assert (full.loc[active, "stop_distance"] > 0).all()
    for cut in (1500, 3000, 4100):
        part = strat.compute(df.iloc[:cut], ctx_for(sym, MK, cut))
        pd.testing.assert_series_equal(part["signal"], full["signal"].iloc[:cut], check_names=False,
                                       obj=f"{name} Signal bei cut={cut}")
        pd.testing.assert_series_equal(part["stop_distance"], full["stop_distance"].iloc[:cut],
                                       check_names=False)


def test_param_grids_are_valid():
    for name, cls in STRATEGIES.items():
        for k, values in cls.param_grid.items():
            assert k in cls.default_params, f"{name}: {k} nicht in default_params"
            for v in values:
                try:
                    cls(**{k: v})
                except ValueError:
                    pass  # ungültige Kombinationen werden im Raster übersprungen


def test_higher_tf_uses_only_completed_days():
    idx = pd.date_range("2024-01-01", periods=24 * 3, freq="1h", tz="UTC")
    close = np.concatenate([np.full(24, 100.0), np.full(24, 200.0), np.full(24, 300.0)])
    df = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1.0}, index=idx)
    d = higher_tf(df, "1h", "1d")
    assert d["close"].iloc[22] != d["close"].iloc[22] or np.isnan(d["close"].iloc[22])  # Tag 1 noch offen
    assert d["close"].iloc[23] == 100  # letzte Stunde von Tag 1: Tag 1 abgeschlossen
    assert d["close"].iloc[46] == 100 and d["close"].iloc[47] == 200


def test_regimes_trend_and_volatility():
    n = 500
    idx = pd.date_range("2022-01-01", periods=n, freq="1D", tz="UTC")
    rng = np.random.default_rng(1)
    up = 100 * np.exp(np.cumsum(0.004 + rng.normal(0, 0.01, n)))
    down = 100 * np.exp(np.cumsum(-0.004 + rng.normal(0, 0.01, n)))
    flat = 100 * np.exp(rng.normal(0, 0.01, n))

    def frame(c):
        return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1.0}, index=idx)

    cfg = RegimeConfig()
    assert (detect_regimes(frame(up), "1d", cfg)["trend"].iloc[-100:] == "bull").mean() > 0.9
    assert (detect_regimes(frame(down), "1d", cfg)["trend"].iloc[-100:] == "bear").mean() > 0.9
    assert (detect_regimes(frame(flat), "1d", cfg)["trend"].iloc[-100:] == "sideways").mean() > 0.9
    # Volatilitätssprung am Ende -> high
    vol = np.concatenate([rng.normal(0, 0.01, 450), rng.normal(0, 0.06, 50)])
    r = detect_regimes(frame(100 * np.exp(np.cumsum(vol))), "1d", cfg)
    assert r["vol"].iloc[-1] == "high"
    assert regime_allows([], "bull", "high") and regime_allows(["bull"], "bull", "low")
    assert not regime_allows(["sideways|low"], "bull", "low")


def test_regimes_have_no_lookahead():
    df = MK["BTC/USDT:USDT"].ohlcv
    full = detect_regimes(df, "1h", RegimeConfig(trend_ma_days=20, vol_rank_days=60))
    part = detect_regimes(df.iloc[:3000], "1h", RegimeConfig(trend_ma_days=20, vol_rank_days=60))
    pd.testing.assert_series_equal(part["label"], full["label"].iloc[:3000])


def test_portfolio_end_to_end_with_metadata():
    cfg = Config()
    cfg.regime = RegimeConfig(trend_ma_days=20, vol_rank_days=60)
    slots = [StrategySlot("ema_trend", {"fast": 20, "slow": 60}, timeframe="1h"),
             StrategySlot("donchian_breakout", timeframe="1h", weight=0.5)]
    prep = Prepared(cfg, MK, slots)
    res = run(prep, label="test")
    assert res.metrics["trades"] > 0
    assert res.metadata["data"]["BTC/USDT:USDT"]["synthetic"] is True
    assert res.metadata["git_commit"]
    assert "benchmark" in res.metrics and "sharpe" in res.metrics["benchmark"]
    t = res.trades.iloc[0]
    assert "strategy" in res.trades.columns and "regime" in res.trades.columns
    assert "|" in t["regime"] and t["leverage"] <= cfg.risk.max_leverage + 1e-6
    assert res.exposure["gross"].max() <= cfg.risk.max_leverage * 1.25  # Kursdrift zwischen Rebalances


def test_regime_gating_blocks_strategy():
    cfg = Config()
    cfg.regime = RegimeConfig(trend_ma_days=20, vol_rank_days=60)
    slots = [StrategySlot("ema_trend", {"fast": 20, "slow": 60}, timeframe="1h", regimes=["nonexistent"])]
    res = run(Prepared(cfg, MK, slots))
    assert res.metrics["trades"] == 0
