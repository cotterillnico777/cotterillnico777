"""Phase 2: Backtest-Engine. Referenzfälle sind von Hand nachgerechnet."""

import math

import numpy as np
import pandas as pd
import pytest

from quantbot.backtesting.costs import CostModel
from quantbot.backtesting.engine import BacktestEngine
from quantbot.backtesting.metrics import compute_metrics, drawdown_stats
from quantbot.core.types import Intent
from quantbot.data import MarketSeries
from quantbot.data.synthetic import synthetic_ohlcv
from quantbot.portfolio.account import Account

ZERO = CostModel(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def series(opens, closes=None, highs=None, lows=None, tf="1h", start="2024-01-01", funding=None, symbol="X"):
    opens = np.asarray(opens, float)
    closes = np.asarray(closes if closes is not None else opens, float)
    highs = np.asarray(highs if highs is not None else np.maximum(opens, closes), float)
    lows = np.asarray(lows if lows is not None else np.minimum(opens, closes), float)
    idx = pd.date_range(start, periods=len(opens), freq=tf, tz="UTC")
    df = pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": 1.0}, index=idx)
    if funding is None:
        funding = pd.DataFrame({"rate": [0.0]}, index=idx[:1])
    return MarketSeries(symbol, tf, df, funding, "h")


class Script:
    """Gibt zu festen Kerzenindizes vorgegebene Intents aus."""

    def __init__(self, plan):
        self.plan = plan
        self.seen = []

    def decide(self, view):
        self.seen.append(view.i)
        return self.plan.get(view.i, [])


def engine(markets, costs=ZERO, equity=1000.0, mmr=0.005, **kw):
    if isinstance(markets, MarketSeries):
        markets = {markets.symbol: markets}
    return BacktestEngine(markets, costs, equity, {s: mmr for s in markets}, **kw)


# ------------------------------------------------------------- Grundfälle
def test_long_pnl_exact_without_costs():
    m = series([100, 100, 110, 120, 120])
    res = engine(m).run(Script({0: [Intent("X", 2.0)], 2: [Intent("X", 0.0)]}))
    # Kauf zum Open von Kerze 1 (100), Verkauf zum Open von Kerze 3 (120)
    t = res.trades.iloc[0]
    assert t.entry_price == 100 and t.exit_price == 120
    assert t.gross_pnl == pytest.approx(40) and t.net_pnl == pytest.approx(40)
    assert res.equity.iloc[-1] == pytest.approx(1040)


def test_fees_and_slippage_exact():
    costs = CostModel(taker_fee=0.001, maker_fee=0.0, slippage_bps=10, slippage_range_frac=0.0,
                      funding_fallback_rate=0.0, liquidation_fee=0.0)
    m = series([100, 100, 100, 100])
    res = engine(m, costs).run(Script({0: [Intent("X", 1.0)], 1: [Intent("X", 0.0)]}))
    t = res.trades.iloc[0]
    assert t.entry_price == pytest.approx(100.1)  # +10 bps
    assert t.exit_price == pytest.approx(99.9)
    assert t.fees == pytest.approx(100.1 * 0.001 + 99.9 * 0.001)
    assert t.slippage_cost == pytest.approx(0.2)
    assert t.net_pnl == pytest.approx(-0.2 - 0.2)
    assert res.equity.iloc[-1] == pytest.approx(1000 - 0.4)


def test_short_receives_positive_funding():
    idx = pd.date_range("2024-01-01", periods=48, freq="1h", tz="UTC")
    funding = pd.DataFrame({"rate": 0.001}, index=idx[::8])  # 00, 08, 16 Uhr
    m = series([100] * 48, funding=funding)
    res = engine(m).run(Script({0: [Intent("X", -1.0)]}))
    # Short ab Open Kerze 1 (01:00) -> Funding um 08,16,00,08,16 = 5 Zahlungen à 0,1
    t = res.trades.iloc[0]
    assert t.funding == pytest.approx(-0.5)
    assert t.net_pnl == pytest.approx(0.5)


def test_funding_fallback_when_no_history():
    m = series([100] * 24)
    m.funding = None
    costs = CostModel(0, 0, 0, 0, funding_fallback_rate=0.0002, liquidation_fee=0)
    res = engine(m, costs).run(Script({0: [Intent("X", 1.0)]}))
    assert res.metrics["funding_fallback_symbols"] == ["X"]
    assert res.trades.iloc[0].funding == pytest.approx(2 * 100 * 0.0002)  # 08 und 16 Uhr


def test_stop_gap_fills_at_open():
    # Long zu 100, Stop 95; nächste Kerze eröffnet bei 90 (Gap)
    m = series([100, 100, 90, 90], closes=[100, 100, 92, 92], lows=[100, 99, 88, 90])
    res = engine(m).run(Script({0: [Intent("X", 1.0, stop_price=95)]}))
    t = res.trades.iloc[0]
    assert t.exit_reason == "stop_loss" and t.exit_price == 90


def test_stop_has_priority_over_take_profit_in_same_bar():
    m = series([100, 100, 100], highs=[100, 120, 100], lows=[100, 80, 100])
    res = engine(m).run(Script({0: [Intent("X", 1.0, stop_price=90, take_profit=110)]}))
    t = res.trades.iloc[0]
    assert t.exit_reason == "stop_loss" and t.exit_price == 90


def test_take_profit_fills_at_limit_with_maker_fee():
    costs = CostModel(0.001, 0.0002, 0, 0, 0, 0)
    m = series([100, 100, 105, 105], highs=[100, 104, 112, 105])
    res = engine(m, costs).run(Script({0: [Intent("X", 1.0, take_profit=110)]}))
    t = res.trades.iloc[0]
    assert t.exit_reason == "take_profit" and t.exit_price == 110
    assert t.fees == pytest.approx(100 * 0.001 + 110 * 0.0002)


def test_short_stop_and_mfe_mae():
    m = series([100, 100, 95, 97, 104], highs=[100, 101, 99, 100, 106], lows=[100, 96, 90, 94, 103])
    res = engine(m).run(Script({0: [Intent("X", -1.0, stop_price=105)]}))
    t = res.trades.iloc[0]
    assert t.direction == "short" and t.exit_reason == "stop_loss" and t.exit_price == 105
    assert t.mfe_pct == pytest.approx(10.0)  # Tief 90
    assert t.mae_pct == pytest.approx(-1.0)  # Hoch 101 vor dem Stop-Bar


def test_execution_delay():
    m = series(list(range(100, 110)))
    res = engine(m, delay_bars=2).run(Script({0: [Intent("X", 1.0)]}))
    assert res.trades.iloc[0].entry_time == m.ohlcv.index[3]  # 0 + 1 + 2
    assert res.trades.iloc[0].entry_price == 103


def test_flip_long_to_short_creates_two_trades():
    m = series([100, 100, 110, 100, 100])
    res = engine(m).run(Script({0: [Intent("X", 1.0)], 1: [Intent("X", -1.0)], 2: [Intent("X", 0.0)]}))
    assert list(res.trades.direction) == ["long", "short"]
    assert res.trades.gross_pnl.tolist() == pytest.approx([10.0, 10.0])


def test_partial_close_keeps_average_price():
    m = series([100, 100, 110, 120, 120])
    res = engine(m).run(Script({0: [Intent("X", 2.0)], 1: [Intent("X", 1.0)], 2: [Intent("X", 0.0)]}))
    t = res.trades.iloc[0]
    assert t.gross_pnl == pytest.approx(10 + 20)
    assert t.qty == 2.0 and t.exit_price == pytest.approx(115)


# ------------------------------------------------------ Margin / Liquidation
def test_liquidation_at_high_leverage():
    # 4,9x Hebel long, Kurs fällt um 25 % -> Liquidation
    m = series([100, 100, 100, 75, 75], lows=[100, 100, 100, 70, 75])
    res = engine(m, CostModel(0, 0, 0, 0, 0, 0.0125), equity=1000).run(Script({0: [Intent("X", 49.0)]}))
    assert res.metrics["liquidations"] == 1
    assert res.trades.iloc[0].exit_reason == "liquidation"
    assert res.equity.iloc[-1] < 1000 * 0.1
    assert (res.equity.iloc[3:] == res.equity.iloc[3]).all()  # danach kein Handel mehr


def test_no_liquidation_at_moderate_leverage():
    m = series([100, 100, 100, 75, 75], lows=[100, 100, 100, 70, 75])
    res = engine(m).run(Script({0: [Intent("X", 10.0)]}))  # 1x
    assert res.metrics["liquidations"] == 0
    assert res.equity.iloc[-1] == pytest.approx(1000 - 250)


def test_liquidation_price_consistent_with_check():
    acc = Account(cash=1000, mmr={"X": 0.005})
    acc.apply_fill("X", 30.0, 100.0, 0.0)  # 3x long
    liq = acc.liquidation_price("X", {"X": 100.0})
    assert liq == pytest.approx((0 - 1000 + 3000) / (30 - 30 * 0.005))
    assert acc.liquidation_check({"X": liq - 0.01}) and not acc.liquidation_check({"X": liq + 0.01})
    acc2 = Account(cash=1000, mmr={"X": 0.005})
    acc2.apply_fill("X", -30.0, 100.0, 0.0)
    liq_s = acc2.liquidation_price("X", {"X": 100.0})
    assert liq_s > 100 and acc2.liquidation_check({"X": liq_s + 0.01})


def test_hard_leverage_cap_is_enforced():
    m = series([100] * 5)
    res = engine(m).run(Script({0: [Intent("X", 100.0)]}))  # 10x gewünscht
    assert any(e["type"] == "hard_leverage_cap" for e in res.events)
    assert res.trades.iloc[0].qty == pytest.approx(50.0)  # 5x Obergrenze


# ---------------------------------------------------- mehrere Märkte / Daten
def test_multi_symbol_with_missing_bar():
    a = series([100, 100, 110, 110, 110], symbol="A")
    b = series([50, 50, 50, 60, 60], symbol="B")
    b.ohlcv = b.ohlcv.drop(b.ohlcv.index[2])  # B hat Kerze 2 nicht
    res = engine({"A": a, "B": b}).run(Script({0: [Intent("A", 1.0)], 1: [Intent("B", 2.0)]}))
    tb = res.trades[res.trades.symbol == "B"].iloc[0]
    assert tb.entry_time == a.ohlcv.index[3]  # auf nächste vorhandene Kerze verschoben
    assert res.equity.iloc[-1] == pytest.approx(1000 + 10 + 0)


def test_decisions_only_see_past_and_end_closes_positions():
    m = series(list(range(100, 120)))
    model = Script({})
    res = engine(m).run(model)
    assert model.seen == list(range(19))  # letzte Kerze: keine Entscheidung mehr
    assert res.trades.empty


def test_prefix_consistency_no_lookahead():
    """Ein Modell, das nur Vergangenheit nutzt, liefert auf verkürzten Daten dieselbe Kurve."""
    df = synthetic_ohlcv(600, "1h", seed=7)

    class Momentum:
        def __init__(self, closes):
            self.closes = closes

        def decide(self, view):
            i = view.i
            if i < 20:
                return []
            ret = self.closes[i] / self.closes[i - 20] - 1
            return [Intent("X", 1.0 if ret > 0 else -1.0, stop_price=None)]

    costs = CostModel(0.0005, 0.0002, 2, 0.02, 0.0001, 0.0125)
    full_m = MarketSeries("X", "1h", df, None, "h")
    part_m = MarketSeries("X", "1h", df.iloc[:400], None, "h")
    full = engine(full_m, costs).run(Momentum(df["close"].values))
    part = engine(part_m, costs).run(Momentum(df["close"].values[:400]))
    # Bis vor das Datenende (dort werden Positionen geschlossen) identisch
    pd.testing.assert_series_equal(full.equity.iloc[:399], part.equity.iloc[:399])


# --------------------------------------------------------------- Metriken
def test_metrics_known_values():
    idx = pd.date_range("2024-01-01", periods=5, freq="1D", tz="UTC")
    eq = pd.Series([100, 110, 99, 120, 120.0], index=idx)
    dd = drawdown_stats(eq)
    assert dd["max_drawdown"] == pytest.approx(99 / 110 - 1)
    assert dd["recovery_bars"] == 1
    trades = pd.DataFrame({"net_pnl": [10, -5, 20, -5], "fees": 1.0, "funding": 0.0, "slippage_cost": 0.0,
                           "bars": 1, "leverage": 1.0, "r_multiple": [1, -0.5, 2, -0.5]})
    exposure = pd.DataFrame({"gross": [0, 1, 1, 0, 0.0], "net": 0.0}, index=idx)
    m = compute_metrics(eq, trades, exposure, "1d", 100)
    assert m["profit_factor"] == pytest.approx(30 / 10)
    assert m["win_rate"] == 0.5 and m["payoff_ratio"] == pytest.approx(15 / 5)
    assert m["expectancy"] == pytest.approx(5.0) and m["expectancy_r"] == pytest.approx(0.5)
    assert m["longest_losing_streak"] == 1
    assert m["time_in_market"] == pytest.approx(0.4)
    assert m["total_return"] == pytest.approx(0.2)
    assert math.isfinite(m["sharpe"]) and m["sortino"] > 0 and m["calmar"] > 0


def test_numpy_quantities_are_accepted():
    m = series([100, 100, 110, 110])
    res = engine(m).run(Script({0: [Intent("X", np.float64(1.0))], 1: [Intent("X", np.float32(0.0))]}))
    assert res.trades.iloc[0].gross_pnl == pytest.approx(10.0)
