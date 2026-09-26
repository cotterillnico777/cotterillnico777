import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from trading_bot.backtest import run_backtest
from trading_bot.bot import TradingBot
from trading_bot.broker import PaperBroker
from trading_bot.config import BacktestConfig, Config, RiskConfig, load_config
from trading_bot.indicators import rsi, sma
from trading_bot.risk import RiskManager, entry_order_value
from trading_bot.strategies import STRATEGIES, create_strategy

HOUR_MS = 3_600_000


def make_df(closes, start="2024-01-01"):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range(start, periods=len(closes), freq="1h", tz="UTC")
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * 1.001,
            "low": np.minimum(opens, closes) * 0.999,
            "close": closes,
            "volume": 1.0,
        },
        index=idx,
    )


def random_walk(n=600, seed=1):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))


# ---------------------------------------------------------------- indicators
def test_sma_and_rsi_basics():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert sma(s, 3).tolist()[2:] == [2, 3, 4]
    up = pd.Series(np.arange(1, 40, dtype=float))
    assert rsi(up, 14).iloc[-1] == 100
    down = pd.Series(np.arange(40, 1, -1, dtype=float))
    assert rsi(down, 14).iloc[-1] == pytest.approx(0)


# ---------------------------------------------------------------- strategies
@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_strategies_have_no_lookahead(name):
    """Das Signal für Kerze t darf sich nicht ändern, wenn spätere Kerzen dazukommen."""
    df = make_df(random_walk())
    strat = create_strategy(name)
    full = strat.generate_signals(df)
    for cut in (150, 300, 450):
        partial = strat.generate_signals(df.iloc[:cut])
        pd.testing.assert_series_equal(partial, full.iloc[:cut], check_names=False)
    assert set(full.unique()) <= {0, 1}


def test_strategy_param_validation():
    with pytest.raises(ValueError):
        create_strategy("ma_crossover", {"fast": 50, "slow": 20})
    with pytest.raises(ValueError):
        create_strategy("ma_crossover", {"typo": 1})
    with pytest.raises(ValueError):
        create_strategy("does_not_exist")


def test_ma_crossover_goes_long_in_uptrend():
    df = make_df(np.linspace(100, 200, 200))
    sig = create_strategy("ma_crossover", {"fast": 5, "slow": 20}).generate_signals(df)
    assert sig.iloc[-1] == 1


# ------------------------------------------------------------------ backtest
def test_backtest_uptrend_profitable_and_consistent():
    df = make_df(np.linspace(100, 200, 300))
    risk = RiskConfig(position_fraction=1.0, max_order_value=1e9, stop_loss_pct=0)
    bt = BacktestConfig(initial_balance=1000, fee=0.0, slippage=0.0)
    res = run_backtest(df, create_strategy("ma_crossover", {"fast": 5, "slow": 20}), risk, bt, "1h")
    assert res.metrics["total_return_pct"] > 50
    assert res.metrics["max_drawdown_pct"] <= 0
    # Endkapital = Cash + offene Position
    assert res.equity.iloc[-1] == pytest.approx(res.metrics["final"])


def test_backtest_stop_loss_triggers():
    # Kurz nach dem Einstieg bricht der Kurs um 20 % ein
    closes = np.concatenate([np.linspace(100, 110, 30), [88, 87, 86]])
    df = make_df(closes)
    risk = RiskConfig(position_fraction=1.0, max_order_value=1e9, stop_loss_pct=0.03)
    bt = BacktestConfig(fee=0.001, slippage=0.0)
    res = run_backtest(df, create_strategy("ma_crossover", {"fast": 5, "slow": 20}), risk, bt, "1h")
    assert res.metrics["stops"] >= 1
    stop_trade = next(t for t in res.trades if t.exit_reason == "stop_loss")
    assert stop_trade.exit_price <= stop_trade.entry_price * 0.97 + 1e-9


def test_backtest_order_cap_limits_exposure():
    df = make_df(np.linspace(100, 200, 300))
    risk = RiskConfig(position_fraction=0.25, max_order_value=100, stop_loss_pct=0)
    bt = BacktestConfig(initial_balance=1000, fee=0.0, slippage=0.0)
    res = run_backtest(df, create_strategy("ma_crossover", {"fast": 5, "slow": 20}), risk, bt, "1h")
    # Nur 100 von 1000 investiert -> Gewinn höchstens ~ +100 %*100
    assert res.metrics["final"] < 1000 + 100 * 1.1


# ---------------------------------------------------------------------- risk
def test_entry_order_value_and_risk_manager(tmp_path):
    r = RiskConfig(position_fraction=0.5, max_order_value=100, min_order_value=10)
    assert entry_order_value(1000, r) == 100
    assert entry_order_value(60, r) == 30
    assert entry_order_value(15, r) == 0  # 7,50 < Minimum
    rm = RiskManager(r, tmp_path / "STOP")
    assert rm.check_entry(50, 0).allowed
    assert not rm.check_entry(50, -r.max_daily_loss).allowed
    (tmp_path / "STOP").touch()
    assert not rm.check_entry(50, 0).allowed


def test_config_rejects_unknown_keys(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("risk:\n  stoploss: 0.1\n")
    with pytest.raises(ValueError, match="stoploss"):
        load_config(p)
    p.write_text("runtime:\n  mode: yolo\n")
    with pytest.raises(ValueError):
        load_config(p)


def test_repo_config_is_valid():
    cfg = load_config("config.yaml")
    assert cfg.runtime.mode == "paper"
    create_strategy(cfg.strategy.name, cfg.strategy.params)


# -------------------------------------------------------------------- broker
def test_paper_broker_round_trip():
    b = PaperBroker(quote=1000, fee=0.001, slippage=0.0)
    buy = b.market_buy(100, 50)
    assert buy.quote_delta == -100
    assert buy.amount == pytest.approx(99.9 / 50)
    sell = b.market_sell(buy.amount, 55)
    assert sell.quote_delta == pytest.approx(buy.amount * 55 * 0.999)
    base, quote = b.balances()
    assert base == pytest.approx(0)
    assert quote == pytest.approx(900 + sell.quote_delta)


# ----------------------------------------------------------------------- bot
class FakeExchange:
    id = "fake"

    def __init__(self, closes, start):
        self.closes = list(closes)
        self.start_ms = int(start.timestamp() * 1000)
        self.now_index = 0  # Index der gerade laufenden Kerze
        self.price_override = None

    def parse_timeframe(self, tf):
        return 3600

    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        rows = []
        for i in range(self.now_index + 1):
            c = self.closes[i]
            o = self.closes[i - 1] if i else c
            rows.append([self.start_ms + i * HOUR_MS, o, max(o, c), min(o, c), c, 1.0])
        return rows[-limit:]

    def fetch_ticker(self, symbol):
        return {"last": self.price_override or self.closes[self.now_index]}


def make_bot(tmp_path, closes, **risk):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ex = FakeExchange(closes, start)
    cfg = Config()
    cfg.risk = RiskConfig(**{"position_fraction": 0.5, "max_order_value": 200, **risk})
    cfg.runtime.kill_switch_file = str(tmp_path / "STOP")
    broker = PaperBroker(quote=1000, fee=0.0, slippage=0.0)
    clock = lambda: start + timedelta(hours=ex.now_index, minutes=30)  # noqa: E731
    bot = TradingBot(
        cfg,
        create_strategy("ma_crossover", {"fast": 3, "slow": 10}),
        ex,
        broker,
        state_path=tmp_path / "state.json",
        clock=clock,
    )
    return bot, ex, broker


def test_bot_enters_exits_and_persists(tmp_path):
    closes = list(np.linspace(100, 150, 40)) + list(np.linspace(150, 90, 40))
    bot, ex, broker = make_bot(tmp_path, closes, stop_loss_pct=0)
    entered = exited = False
    for i in range(len(closes)):
        ex.now_index = i
        bot.tick()
        bot.save()
        if bot.state.position is not None:
            entered = True
            assert -bot.state.trades[-1]["quote_delta"] == pytest.approx(200)
        elif entered:
            exited = True
            break
    assert entered and exited
    assert bot.state.trades[-1]["reason"] == "signal"
    assert bot.state.trades[-1]["pnl"] > 0
    assert (tmp_path / "state.json").exists()
    _, quote = broker.balances()
    assert quote == pytest.approx(1000 + bot.state.realized_pnl_total)


def test_bot_stop_loss_blocks_reentry_until_reset(tmp_path):
    closes = list(np.linspace(100, 150, 40))
    bot, ex, _ = make_bot(tmp_path, closes, stop_loss_pct=0.05)
    for i in range(len(closes)):
        ex.now_index = i
        bot.tick()
    assert bot.state.position is not None
    ex.price_override = bot.state.position.stop * 0.99
    bot.tick()
    assert bot.state.position is None
    assert bot.state.trades[-1]["reason"] == "stop_loss"
    assert bot.state.wait_for_reset
    # Neue Kerze mit weiterhin Long-Signal -> kein Wiedereinstieg
    ex.price_override = None
    ex.closes.append(151)
    ex.now_index += 1
    bot.tick()
    assert bot.state.position is None


def test_bot_respects_kill_switch(tmp_path):
    closes = list(np.linspace(100, 150, 40))
    bot, ex, _ = make_bot(tmp_path, closes)
    (tmp_path / "STOP").touch()
    for i in range(len(closes)):
        ex.now_index = i
        bot.tick()
    assert bot.state.position is None
    assert not bot.state.trades


def test_bot_ignores_running_candle(tmp_path):
    closes = list(np.linspace(100, 150, 40))
    bot, ex, _ = make_bot(tmp_path, closes)
    ex.now_index = 20
    df = bot.closed_candles()
    assert len(df) == 20  # Kerze 20 läuft noch
    assert not math.isnan(df["close"].iloc[-1])


# ------------------------------------------------------------------ optimize
from trading_bot.optimize import (  # noqa: E402
    evaluate,
    precompute,
    recommend,
    robust_scores,
    walk_forward,
    windows,
)


def wf_config(**opt):
    cfg = Config()
    cfg.risk = RiskConfig(position_fraction=1.0, max_order_value=1e9, stop_loss_pct=0.05)
    cfg.backtest = BacktestConfig(fee=0.001, slippage=0.0)
    cfg.optimize.train_days = opt.get("train_days", 20)
    cfg.optimize.test_days = opt.get("test_days", 10)
    cfg.optimize.min_trades = opt.get("min_trades", 1)
    cfg.optimize.grids = {"ma_crossover": {"fast": [3, 5, 8], "slow": [15, 25], "kind": ["ema"]}}
    return cfg


def test_windows_do_not_overlap_and_roll():
    idx = pd.date_range("2024-01-01", periods=24 * 60, freq="1h", tz="UTC")
    wins = windows(idx, 20, 10)
    assert len(wins) == 4
    for train_start, test_start, test_end in wins:
        assert test_start - train_start == pd.Timedelta(days=20)
        assert test_end > test_start
    for a, b in zip(wins, wins[1:]):
        assert b[1] == a[2]  # Testfenster schließen lückenlos aneinander an


def test_robust_score_penalizes_isolated_peak():
    rows = pd.DataFrame(
        {
            "idx": [(0,), (1,), (2,), (3,), (4,)],
            "params": [{"p": i} for i in range(5)],
            "score": [0.0, 0.0, 5.0, 0.0, 0.0],
        }
    )
    rows.loc[len(rows)] = [(6,), {"p": 6}, 3.0]
    rows.loc[len(rows)] = [(7,), {"p": 7}, 3.0]
    rows.loc[len(rows)] = [(8,), {"p": 8}, 3.0]
    r = robust_scores(rows)
    # Spitze 5.0 mit Nachbarn 0 -> 1.67; Plateau 3.0 -> 3.0
    assert r[rows["idx"] == (7,)].iloc[0] > r[rows["idx"] == (2,)].iloc[0]


def test_robust_score_keeps_categorical_params_apart():
    rows = pd.DataFrame(
        {
            "idx": [(0, 0), (0, 1)],
            "params": [{"n": 1, "kind": "ema"}, {"n": 1, "kind": "sma"}],
            "score": [1.0, 3.0],
        }
    )
    assert robust_scores(rows).tolist() == [1.0, 3.0]


def test_walk_forward_has_no_lookahead():
    """Ergebnisse eines Fensters dürfen sich nicht ändern, wenn spätere Daten fehlen."""
    df = make_df(random_walk(24 * 70, seed=3))
    cfg = wf_config()
    full = walk_forward(df, "ma_crossover", cfg)
    cut = full.folds[1].test_end
    partial = walk_forward(df[df.index < cut], "ma_crossover", cfg)
    for a, b in zip(partial.folds[:2], full.folds[:2]):
        assert a.params == b.params
        assert a.test_return_pct == pytest.approx(b.test_return_pct)


def test_walk_forward_equity_chains_fold_returns():
    df = make_df(random_walk(24 * 70, seed=4))
    wf = walk_forward(df, "ma_crossover", wf_config())
    chained = np.prod([1 + f.test_return_pct / 100 for f in wf.folds]) - 1
    assert wf.summary["oos_return_pct"] == pytest.approx(chained * 100)
    assert wf.equity.index.is_monotonic_increasing


def test_walk_forward_min_trades_means_no_trading():
    df = make_df(random_walk(24 * 50, seed=5))
    wf = walk_forward(df, "ma_crossover", wf_config(min_trades=10_000))
    assert all(f.params is None and f.trades == 0 for f in wf.folds)
    assert wf.summary["oos_return_pct"] == pytest.approx(0)


def test_walk_forward_rejects_short_history():
    df = make_df(random_walk(24 * 10))
    with pytest.raises(ValueError, match="Zu wenig Historie"):
        walk_forward(df, "ma_crossover", wf_config())


def test_evaluate_skips_invalid_combos_and_recommend_returns_params():
    df = make_df(random_walk(24 * 30, seed=6))
    cfg = wf_config()
    cfg.optimize.grids = {"ma_crossover": {"fast": [5, 20], "slow": [10, 20], "kind": ["ema"]}}
    cands = precompute(df, "ma_crossover", cfg.optimize.grids["ma_crossover"])
    assert len(cands) == 2  # (20,10) und (20,20) sind ungültig
    rows = evaluate(df, cands, cfg, "ma_crossover")
    assert len(rows) == 2
    best, top = recommend({"A": df, "B": make_df(random_walk(24 * 30, seed=7))}, "ma_crossover", cfg)
    assert best in [c.params for c in cands]
    assert len(top) == 2
