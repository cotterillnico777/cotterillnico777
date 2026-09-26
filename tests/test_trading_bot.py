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
    assert full.between(0, 1).all()


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
        # True: Ticker = Eröffnungskurs der laufenden Kerze (wie die Ausführung im Backtest)
        self.ticker_at_open = False

    def parse_timeframe(self, tf):
        return {"1h": 3600, "4h": 4 * 3600, "1d": 86400}[tf]

    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        rows = []
        for i in range(self.now_index + 1):
            c = self.closes[i]
            o = self.closes[i - 1] if i else c
            rows.append([self.start_ms + i * HOUR_MS, o, max(o, c), min(o, c), c, 1.0])
        if timeframe != "1h":
            # Höheren Zeitrahmen wie eine Börse liefern (inkl. laufender Kerze)
            df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
            df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
            agg = df.set_index("ts").resample(timeframe.replace("d", "D"), label="left", closed="left").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            ).dropna()
            rows = [[int(t.timestamp() * 1000), *r] for t, r in zip(agg.index, agg.values.tolist())]
        return rows[-limit:]

    def fetch_ticker(self, symbol):
        if self.ticker_at_open and self.now_index > 0:
            return {"last": self.closes[self.now_index - 1]}
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


# ------------------------------------------------- trailing / ATR / sizing
from trading_bot.indicators import atr as atr_indicator  # noqa: E402
from trading_bot.risk import stop_price, trail_stop  # noqa: E402


def test_atr_constant_range():
    df = make_df(np.full(50, 100.0))
    df["high"], df["low"] = 101.0, 99.0
    assert atr_indicator(df, 14).iloc[-1] == pytest.approx(2.0)
    assert atr_indicator(df, 14).iloc[:13].isna().all()


def test_trail_stop_only_moves_up():
    r = RiskConfig(stop_loss_pct=0.1, trailing_stop=True)
    assert stop_price(100, r) == pytest.approx(90)
    assert trail_stop(90, 120, r) == pytest.approx(108)
    assert trail_stop(108, 110, r) == pytest.approx(108)  # nie nach unten
    r_atr = RiskConfig(stop_mode="atr", atr_multiplier=2, trailing_stop=True)
    assert stop_price(100, r_atr, atr=3) == pytest.approx(94)
    assert trail_stop(94, 110, r_atr, atr=3) == pytest.approx(104)
    assert trail_stop(94, 110, RiskConfig(stop_loss_pct=0.1)) == 94  # Trailing aus


def test_risk_based_sizing():
    r = RiskConfig(
        sizing="risk", risk_per_trade=0.01, stop_mode="atr", atr_multiplier=2,
        position_fraction=1.0, max_order_value=1e9, min_order_value=0,
    )
    # 1 % von 1000 = 10 Risiko; Stopabstand 2×2.5 = 5 bei Preis 100 -> 2 Stück = 200
    assert entry_order_value(1000, r, price=100, atr=2.5) == pytest.approx(200)
    # Doppelte Volatilität -> halbe Position
    assert entry_order_value(1000, r, price=100, atr=5) == pytest.approx(100)
    # Obergrenzen gelten weiter
    capped = RiskConfig(**{**r.__dict__, "max_order_value": 50})
    assert entry_order_value(1000, capped, price=100, atr=2.5) == 50
    # Ohne ATR kein Stop -> keine Order
    assert entry_order_value(1000, r, price=100, atr=float("nan")) == 0


def test_config_validation_for_new_risk_options(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("risk:\n  sizing: risk\n  stop_loss_pct: 0\n")
    with pytest.raises(ValueError, match="Stop-Loss"):
        load_config(p)
    p.write_text("risk:\n  trailing_stop: true\n  stop_loss_pct: 0\n")
    with pytest.raises(ValueError):
        load_config(p)
    p.write_text("risk:\n  stop_mode: atr\n  trailing_stop: true\n  sizing: risk\n")
    assert load_config(p).risk.needs_atr


def test_backtest_trailing_stop_locks_in_profit():
    # Anstieg auf 150, dann Absturz auf 140: fester Stop (bei ~96) greift nicht,
    # Trailing-Stop (5 % unter dem Hoch) sichert den Gewinn noch in der Absturzkerze
    closes = np.concatenate([np.linspace(100, 150, 60), np.full(10, 140.0)])
    df = make_df(closes)
    strat = create_strategy("ma_crossover", {"fast": 3, "slow": 10})
    bt = BacktestConfig(fee=0.0, slippage=0.0)
    base = dict(position_fraction=1.0, max_order_value=1e9, stop_loss_pct=0.05)
    fixed = run_backtest(df, strat, RiskConfig(**base), bt, "1h")
    trail = run_backtest(df, strat, RiskConfig(**base, trailing_stop=True), bt, "1h")
    stop_trades = [t for t in trail.trades if t.exit_reason == "stop_loss"]
    assert stop_trades and stop_trades[0].pnl > 0
    assert stop_trades[0].exit_price >= 150 * 0.95 * 0.99
    assert trail.metrics["final"] >= fixed.metrics["final"]


def test_backtest_is_prefix_consistent_with_atr_trailing():
    """Kein Blick in die Zukunft: Kapitalkurve eines verkürzten Datensatzes = Anfang der vollen."""
    df = make_df(random_walk(800, seed=9))
    risk = RiskConfig(
        stop_mode="atr", atr_multiplier=2, trailing_stop=True, sizing="risk",
        position_fraction=1.0, max_order_value=1e9,
    )
    strat = create_strategy("ma_crossover", {"fast": 5, "slow": 20})
    bt = BacktestConfig(fee=0.001, slippage=0.0005)
    full = run_backtest(df, strat, risk, bt, "1h")
    part = run_backtest(df.iloc[:500], strat, risk, bt, "1h")
    pd.testing.assert_series_equal(part.equity, full.equity.iloc[:500])
    assert full.metrics["trades"] > 0


def test_bot_trailing_stop_follows_candles(tmp_path):
    closes = list(np.linspace(100, 150, 40))
    bot, ex, _ = make_bot(tmp_path, closes, stop_loss_pct=0.05, trailing_stop=True)
    stops = []
    for i in range(len(closes)):
        ex.now_index = i
        bot.tick()
        if bot.state.position is not None:
            stops.append(bot.state.position.stop)
    assert len(stops) > 3
    assert all(b >= a for a, b in zip(stops, stops[1:]))  # nur nach oben
    assert stops[-1] > stops[0]
    pos = bot.state.position
    assert pos.stop == pytest.approx(pos.highest * 0.95)


def test_bot_atr_risk_sizing(tmp_path):
    closes = list(np.linspace(100, 150, 40))
    bot, ex, broker = make_bot(
        tmp_path, closes, stop_mode="atr", atr_multiplier=2, sizing="risk",
        risk_per_trade=0.01, position_fraction=1.0, max_order_value=1e9,
    )
    for i in range(len(closes)):
        ex.now_index = i
        bot.tick()
        if bot.state.position is not None:
            break
    pos = bot.state.position
    assert pos is not None
    # Verlust bis zum Stop ~ 1 % des Startguthabens
    assert pos.amount * (pos.entry_price - pos.stop) == pytest.approx(10, rel=0.05)


# --------------------------------------------------------------- trendfilter
from trading_bot import trend  # noqa: E402
from trading_bot.config import TrendFilterConfig  # noqa: E402
from trading_bot.data import candles_to_frame  # noqa: E402


def step_df(levels, hours_per_level=24, start="2024-01-01"):
    closes = np.repeat(np.asarray(levels, dtype=float), hours_per_level)
    return make_df(closes, start=start)


def test_trend_condition_uses_only_closed_daily_candles():
    df = step_df([100, 100, 100, 200, 200, 200])
    cond = trend.condition(df, "1h", TrendFilterConfig(enabled=True, period=2))
    # Tag 4 (Schluss 200 > SMA2 = 150) gilt ab der 23-Uhr-Kerze, deren Schluss der Tagesschluss ist
    assert cond.idxmax() == pd.Timestamp("2024-01-04 23:00", tz="UTC")
    assert not cond[: pd.Timestamp("2024-01-04 22:00", tz="UTC")].any()


def test_trend_apply_entry_vs_exit():
    sig = pd.Series([0, 1, 1, 1, 1, 0, 1, 1])
    ok = pd.Series([1, 0, 1, 0, 0, 0, 0, 1]).astype(bool)
    # exit: nur investiert, solange beides passt
    assert trend.apply(sig, ok, "exit").tolist() == [0, 0, 1, 0, 0, 0, 0, 1]
    # entry: Einstieg erst bei Trend, dann halten bis Signal 0
    assert trend.apply(sig, ok, "entry").tolist() == [0, 0, 1, 1, 1, 0, 0, 1]


def test_trend_filtered_signals_have_no_lookahead():
    df = make_df(random_walk(24 * 40, seed=21))
    cfg = TrendFilterConfig(enabled=True, period=5, kind="ema")
    strat = create_strategy("rsi_reversion")
    full = trend.strategy_signals(strat, df, "1h", cfg)
    for cut in (24 * 10 + 7, 24 * 25 + 23, 24 * 33):
        part = trend.strategy_signals(strat, df.iloc[:cut], "1h", cfg)
        pd.testing.assert_series_equal(part, full.iloc[:cut], check_names=False)


def test_live_and_backtest_trend_condition_agree():
    df = make_df(random_walk(24 * 30, seed=22))
    cfg = TrendFilterConfig(enabled=True, period=4, timeframe="1d")
    backtest_cond = trend.condition(df, "1h", cfg)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ex = FakeExchange(df["close"].tolist(), start)
    ex.now_index = len(df) - 1
    rows = ex.fetch_ohlcv("X", "1d", limit=1000)
    now_ms = (start + timedelta(hours=len(df))).timestamp() * 1000
    rows = [r for r in rows if r[0] + 86_400_000 <= now_ms]  # nur abgeschlossene Tage
    live_cond = trend.condition_from_htf(candles_to_frame(rows), "1h", df.index, cfg)
    pd.testing.assert_series_equal(live_cond, backtest_cond, check_names=False)


def test_trend_filter_config_validation(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("trend_filter:\n  mode: sometimes\n")
    with pytest.raises(ValueError):
        load_config(p)
    p.write_text("trend_filter:\n  enabled: true\n  timeframe: 1d\n  period: 50\n")
    assert load_config(p).trend_filter.period == 50


def make_trend_bot(tmp_path, closes, mode="entry"):
    bot, ex, broker = make_bot(tmp_path, closes, stop_loss_pct=0)
    bot.cfg.trend_filter = TrendFilterConfig(enabled=True, timeframe="1d", period=3, mode=mode)
    return bot, ex, broker


def run_ticks(bot, ex, upto):
    for i in range(upto):
        ex.now_index = i
        bot.tick()


def test_bot_trend_filter_blocks_entry_in_downtrend(tmp_path):
    # 5 Tage fallend, dann ein kurzer stündlicher Anstieg: MA-Signal 1, Tagestrend aber ab
    # Tag 6 schließt bei ~111,6 und damit unter SMA3 (120, 110, 111,6) = 113,9
    closes = list(np.repeat([150, 140, 130, 120, 110], 24)) + list(np.linspace(110, 112, 30))
    bot, ex, _ = make_trend_bot(tmp_path, closes)
    run_ticks(bot, ex, len(closes))
    assert bot.state.position is None
    assert not bot.state.trades


def test_bot_trend_filter_allows_entry_in_uptrend(tmp_path):
    closes = list(np.repeat([100, 110, 120, 130, 140], 24)) + list(np.linspace(140, 150, 30))
    bot, ex, _ = make_trend_bot(tmp_path, closes)
    run_ticks(bot, ex, len(closes))
    assert bot.state.position is not None


def test_bot_trend_filter_exit_mode_sells_on_trend_break(tmp_path):
    up = list(np.repeat([100, 110, 120, 130, 140], 24)) + list(np.linspace(140, 150, 24))
    # Danach Tagesschlüsse deutlich unter dem 3-Tage-Durchschnitt, stündlich aber leicht steigend
    down = list(np.linspace(90, 92, 48))
    closes = up + down
    bot, ex, _ = make_trend_bot(tmp_path, closes, mode="exit")
    run_ticks(bot, ex, len(up))
    assert bot.state.position is not None
    run_ticks(bot, ex, len(closes))
    sells = [t for t in bot.state.trades if t["side"] == "sell"]
    assert sells  # spätestens nach dem ersten Tagesschluss unter dem Durchschnitt verkauft


# ---------------------------------------- Teilpositionen / Vol-Target / Ensemble
from trading_bot.backtest import vol_for  # noqa: E402
from trading_bot.risk import plan_rebalance, position_value  # noqa: E402


def full_risk(**kw):
    return RiskConfig(**{"position_fraction": 1.0, "max_order_value": 1e12, "min_order_value": 1,
                         "stop_loss_pct": 0, **kw})


def test_plan_rebalance_fixed_steps():
    r = full_risk()
    o = plan_rebalance(1 / 3, 0, 0, 0, 900, 900, r, 100)
    assert o.action == "open" and o.value == pytest.approx(300) and o.unit_value == 900
    o = plan_rebalance(2 / 3, 1 / 3, 900, 330, 930, 600, r, 110)
    assert o.action == "buy" and o.value == pytest.approx(300)  # Einheit bleibt fest
    o = plan_rebalance(1 / 3, 2 / 3, 900, 700, 1000, 300, r, 110)
    assert o.action == "sell" and o.value == pytest.approx(0.5)
    assert plan_rebalance(1 / 3, 1 / 3, 900, 500, 1000, 500, r, 150).action is None  # Gewinner laufen lassen
    assert plan_rebalance(0, 1 / 3, 900, 500, 1000, 500, r, 150).action == "close"


def test_plan_rebalance_vol_target():
    r = full_risk(sizing="vol_target", target_vol=0.25, rebalance_threshold=0.25)
    assert position_value(1000, r, vol=0.5) == pytest.approx(500)
    assert position_value(1000, r, vol=0.1) == pytest.approx(1000)  # max. 100 %, kein Hebel
    assert position_value(1000, r, vol=float("nan")) == 0
    o = plan_rebalance(1, 0, 0, 0, 1000, 1000, r, 100, vol=0.5)
    assert o.action == "open" and o.value == pytest.approx(500)
    # 10 % Abweichung < 25 % Schwelle -> nichts tun
    assert plan_rebalance(1, 1, 0, 550, 1050, 500, r, 110, vol=0.5).action is None
    # Volatilität verdoppelt -> Ziel halbiert -> Teilverkauf
    o = plan_rebalance(1, 1, 0, 500, 1000, 500, r, 100, vol=1.0)
    assert o.action == "sell" and o.value == pytest.approx(0.5)


def test_trend_ensemble_steps_in_and_out():
    closes = np.concatenate([np.full(40, 100.0), np.linspace(100, 200, 60), np.linspace(200, 120, 60)])
    df = make_df(closes)
    sig = create_strategy("trend_ensemble", {"short": 5, "mid": 10, "long": 20}).generate_signals(df)
    levels = set(np.round(sig.unique(), 4))
    assert levels <= {0, 0.3333, 0.6667, 1}
    assert sig.iloc[99] == 1  # langer Anstieg: alle drei Systeme long
    # Beim Rückgang steigen die Systeme nacheinander aus: 1 -> 2/3 -> 1/3 -> 0
    falling = sig.iloc[100:].round(4)
    steps = list(dict.fromkeys(falling.tolist()))
    assert steps == [1.0, 0.6667, 0.3333, 0.0]
    assert sig.iloc[-1] == 0
    with pytest.raises(ValueError):
        create_strategy("trend_ensemble", {"short": 50, "mid": 40, "long": 100})


def test_backtest_partial_positions_exposure():
    df = make_df(random_walk(600, seed=31))
    half = pd.Series(0.5, index=df.index)
    bt = BacktestConfig(fee=0.0, slippage=0.0)
    res = run_backtest(df, create_strategy("ma_crossover"), full_risk(), bt, "1h", signals=half)
    assert res.metrics["orders"] == 1  # einmal halb rein, danach nichts (Gewinner laufen)
    assert res.metrics["trades"] == 0 and res.metrics["open_position"] == 1
    exposure0 = 0.5
    # Kapital = 50 % Cash + 50 % mit dem Kurs
    expected = 1000 * (1 - exposure0) + 1000 * exposure0 * df["close"].iloc[-1] / df["open"].iloc[1]
    assert res.metrics["final"] == pytest.approx(expected)


def test_backtest_vol_target_matches_target_on_average():
    rng = np.random.default_rng(32)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 24 * 200)))  # ~94 % Jahresvola
    df = make_df(closes)
    r = full_risk(sizing="vol_target", target_vol=0.3, vol_lookback_days=10)
    res = run_backtest(df, create_strategy("ma_crossover"), r, BacktestConfig(fee=0, slippage=0),
                       "1h", signals=pd.Series(1.0, index=df.index))
    realized = res.equity.pct_change().dropna().std() * np.sqrt(24 * 365)
    assert realized == pytest.approx(0.3, rel=0.25)
    assert res.metrics["avg_exposure_pct"] < 50


def test_backtest_prefix_consistent_with_ensemble_and_vol_target():
    df = make_df(random_walk(24 * 60, seed=33))
    r = full_risk(sizing="vol_target", target_vol=0.4, vol_lookback_days=5, stop_loss_pct=0.05,
                  trailing_stop=True)
    strat = create_strategy("trend_ensemble", {"short": 10, "mid": 30, "long": 60})
    bt = BacktestConfig(fee=0.001, slippage=0.0005)
    full = run_backtest(df, strat, r, bt, "1h")
    part = run_backtest(df.iloc[:900], strat, r, bt, "1h")
    pd.testing.assert_series_equal(part.equity, full.equity.iloc[:900])
    assert full.metrics["orders"] > full.metrics["trades"]  # Teilkäufe/-verkäufe fanden statt


@pytest.mark.parametrize("sizing", ["fixed", "vol_target"])
def test_bot_matches_backtest_with_partial_positions(tmp_path, sizing):
    """Live-Bot und Backtest müssen bei gleichen Kursen identisch handeln."""
    closes = random_walk(24 * 20, seed=34) * 100
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ex = FakeExchange(closes, start)
    ex.ticker_at_open = True  # Bot handelt zum Eröffnungskurs, wie der Backtest
    ex.now_index = len(closes) - 1
    df = candles_to_frame(ex.fetch_ohlcv("X", "1h", limit=10_000))

    cfg = Config()
    cfg.risk = full_risk(sizing=sizing, target_vol=0.5, vol_lookback_days=3,
                         rebalance_threshold=0.2, min_order_value=5, max_daily_loss=1e9)
    cfg.runtime.kill_switch_file = str(tmp_path / "STOP")
    strat = create_strategy("trend_ensemble", {"short": 6, "mid": 12, "long": 24})
    # Der Bot handelt erst, wenn genug Kerzen für den Vorlauf da sind (live immer der Fall)
    signals = strat.generate_signals(df)
    signals.iloc[: strat.warmup - 1] = 0
    res = run_backtest(df, strat, cfg.risk, BacktestConfig(fee=0.001, slippage=0.0), "1h",
                       signals=signals)

    broker = PaperBroker(quote=1000, fee=0.001, slippage=0.0)
    bot = TradingBot(cfg, strat, ex, broker, state_path=tmp_path / "s.json",
                     clock=lambda: start + timedelta(hours=ex.now_index, minutes=1))
    for i in range(1, len(closes)):
        ex.now_index = i
        bot.tick()

    assert res.metrics["orders"] > res.metrics["trades"] > 0
    assert len(bot.state.trades) == res.metrics["orders"]
    base, quote = broker.balances()
    # Gleiche Bestände -> gleicher Wert zum Schlusskurs der letzten Kerze
    assert quote + base * closes[-1] == pytest.approx(res.equity.iloc[-1], rel=1e-9)
