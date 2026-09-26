"""Phase 6: Execution Engine, simulierte Börse, Ledger, Paper-Handelsschleife."""

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from quantbot.backtesting.costs import CostModel
from quantbot.config.schema import Config, RegimeConfig, StrategySlot
from quantbot.core.timeframes import to_ms
from quantbot.core.types import Intent, Mode, Order, OrderStatus, OrderType, Side
from quantbot.data.synthetic import synthetic_funding, synthetic_ohlcv
from quantbot.exchanges.base import ExchangeAdapter
from quantbot.exchanges.simulated import SimulatedExchange
from quantbot.execution.engine import ExecConfig, ExecutionEngine, ExecutionHalted, client_id
from quantbot.execution.ledger import TradeLedger
from quantbot.execution.trader import Trader
from quantbot.monitoring.journal import Journal

COST = CostModel(0.0005, 0.0002, 0.0, 0.0, 0.0, 0.0125)
S = "BTC/USDT:USDT"


def setup(price=100.0):
    ex = SimulatedExchange(None, COST, 10_000, {S: 0.004})
    ex.set_price(S, price)
    j = Journal(":memory:")
    j.run_id = "t"
    eng = ExecutionEngine(ex, j, "tag", ExecConfig(retry_delay=0, min_notional=5), sleep=lambda s: None)
    return ex, j, eng


def pos(ex):
    p = ex.account.positions.get(S)
    return p.qty if p else 0.0


def fills(j):
    return j.query("SELECT * FROM fills ORDER BY id")


def test_client_id_is_deterministic_and_short():
    a = client_id("run", S, "2024-01-01 04:00", "open")
    assert a == client_id("run", S, "2024-01-01 04:00", "open")
    assert a != client_id("run", S, "2024-01-01 08:00", "open")
    assert len(a) <= 36


def test_open_with_server_side_stop_and_take_profit():
    ex, j, eng = setup()
    eng.rebalance([Intent(S, 2.0, stop_price=95.0, take_profit=110.0, reason="entry")], "b1", {S: 0.0}, {S: 100.0})
    assert pos(ex) == 2.0
    opens = ex.get_open_orders(S)
    kinds = {o.type: o for o in opens}
    assert kinds[OrderType.STOP_MARKET].stop_price == 95.0 and kinds[OrderType.STOP_MARKET].reduce_only
    assert kinds[OrderType.TAKE_PROFIT_MARKET].qty == 2.0
    assert len(fills(j)) == 1 and fills(j)[0]["fee"] == pytest.approx(200 * 0.0005)


def test_same_decision_twice_creates_no_duplicate():
    ex, j, eng = setup()
    o = Order(client_id("tag", S, "b1", "open"), S, Side.BUY, OrderType.MARKET, 1.0)
    eng.submit(o)
    eng.submit(Order(o.client_id, S, Side.BUY, OrderType.MARKET, 1.0))
    assert pos(ex) == 1.0 and len(fills(j)) == 1


def test_timeout_after_acceptance_is_not_resent():
    ex, j, eng = setup()
    ex.fault_queue = ["timeout_after"]
    o = eng.submit(Order("cid1", S, Side.BUY, OrderType.MARKET, 1.0))
    assert o.status is OrderStatus.FILLED and pos(ex) == 1.0 and len(fills(j)) == 1
    assert j.query("SELECT COUNT(*) AS n FROM events WHERE type='order_timeout'")[0]["n"] == 1


def test_timeout_before_acceptance_is_retried_once():
    ex, j, eng = setup()
    ex.fault_queue = ["timeout_before"]
    o = eng.submit(Order("cid2", S, Side.BUY, OrderType.MARKET, 1.0))
    assert o.status is OrderStatus.FILLED and pos(ex) == 1.0 and len(fills(j)) == 1


def test_repeated_rejections_halt_execution():
    ex, j, eng = setup()
    ex.fault_queue = ["reject"] * 3
    for k in range(3):
        assert eng.submit(Order(f"r{k}", S, Side.BUY, OrderType.MARKET, 1.0)).status is OrderStatus.REJECTED
    with pytest.raises(ExecutionHalted):
        eng.submit(Order("r4", S, Side.BUY, OrderType.MARKET, 1.0))


def test_partial_fill_is_completed_next_cycle():
    ex, j, eng = setup()
    ex.fault_queue = ["partial"]
    eng.rebalance([Intent(S, 2.0)], "b1", {S: 0.0}, {S: 100.0})
    assert pos(ex) == pytest.approx(1.0)
    eng.rebalance([Intent(S, 2.0)], "b2", {S: pos(ex)}, {S: 100.0})
    assert pos(ex) == pytest.approx(2.0)


def test_flip_uses_reduce_only_close_then_open_and_resizes_stop():
    ex, j, eng = setup()
    eng.rebalance([Intent(S, 1.0, stop_price=95.0)], "b1", {S: 0.0}, {S: 100.0})
    eng.rebalance([Intent(S, 3.0)], "b2", {S: 1.0}, {S: 100.0})  # aufstocken, Stop bleibt 95
    stop = [o for o in ex.get_open_orders(S) if o.type is OrderType.STOP_MARKET]
    assert len(stop) == 1 and stop[0].qty == 3.0 and stop[0].stop_price == 95.0
    eng.rebalance([Intent(S, -1.0, stop_price=106.0)], "b3", {S: 3.0}, {S: 100.0})
    assert pos(ex) == pytest.approx(-1.0)
    close = j.query("SELECT * FROM orders WHERE reduce_only=1 AND type='market'")
    assert len(close) == 1 and close[0]["qty"] == 3.0
    stops = [o for o in ex.get_open_orders(S) if o.type is OrderType.STOP_MARKET]
    assert len(stops) == 1 and stops[0].side is Side.BUY and stops[0].stop_price == 106.0


def test_triggered_stop_is_synced_and_booked_as_trade():
    ex, j, eng = setup()
    ledger = TradeLedger(j)
    ledger.set_meta(S, {"strategy": "x@1", "regime": "bull|low", "signal_strength": 0.8})
    eng.rebalance([Intent(S, 2.0, stop_price=95.0)], "b1", {S: 0.0}, {S: 100.0})
    ledger.process("t", 10_000, 200, {})
    ex.process_bar(S, high=101, low=94, close=96)  # Stop bei 95 ausgelöst
    eng.sync_orders()
    closed = ledger.process("t", 10_000, 0, {})
    assert pos(ex) == 0.0
    assert len(closed) == 1
    t = closed[0]
    assert t["exit_reason"] == "stop_loss" and t["exit_price"] == pytest.approx(95.0)
    assert t["gross_pnl"] == pytest.approx(-10.0)
    assert t["strategy"] == "x@1" and t["regime"] == "bull|low"
    assert j.query("SELECT COUNT(*) AS n FROM trades")[0]["n"] == 1


def test_ledger_partial_close_and_flip():
    j = Journal(":memory:")
    j.run_id = "t"
    led = TradeLedger(j)
    for cid, side, qty, px in [("a", "buy", 2, 100), ("b", "sell", 1, 110), ("c", "sell", 3, 120), ("d", "buy", 2, 100)]:
        j.fill(cid, S, side, qty, px, 0.0)
    closed = led.process("t", 1000, 0, {})
    assert [c["direction"] for c in closed] == ["long", "short"]
    assert closed[0]["gross_pnl"] == pytest.approx(10 + 20)  # 1 zu 110 (+10), 1 zu 120 (+20)
    assert closed[1]["gross_pnl"] == pytest.approx(2 * 20)  # short 2 @120, zurück @100
    assert led.process("t", 1000, 0, {}) == []  # jeder Fill nur einmal


# ------------------------------------------------------- Paper-Schleife
class FeedAdapter(ExchangeAdapter):
    """Marktdaten-Feed mit verschiebbarer Uhr (inkl. laufender Kerze wie eine echte Börse)."""

    name = "feed"

    def __init__(self, frames, funding):
        self.frames, self.funding = frames, funding
        self.now = None
        self.stale = False

    def get_ohlcv(self, symbol, timeframe, since=None, limit=500):
        df = self.frames[symbol]
        cut = self.now - pd.Timedelta(hours=12) if self.stale else self.now
        sel = df[(df.index <= cut) & (to_ms(df.index) >= (since or 0))].iloc[:limit]
        return [[int(t.timestamp() * 1000), *r] for t, r in zip(sel.index, sel.values.tolist())]

    def get_funding_history(self, symbol, since=None, limit=1000):
        f = self.funding[symbol]
        sel = f[(f.index <= self.now) & (to_ms(f.index) >= (since or 0))].iloc[:limit]
        return [(int(t.timestamp() * 1000), float(r)) for t, r in zip(sel.index, sel["rate"])]

    def get_ticker_price(self, symbol):
        df = self.frames[symbol]
        return float(df[df.index <= self.now]["open"].iloc[-1])

    def get_balance(self): raise NotImplementedError
    def get_positions(self): raise NotImplementedError
    def set_leverage(self, symbol, leverage): raise NotImplementedError
    def place_order(self, order): raise NotImplementedError
    def cancel_order(self, symbol, client_id): raise NotImplementedError
    def get_order(self, symbol, client_id): raise NotImplementedError
    def get_open_orders(self, symbol=None): raise NotImplementedError


def paper_setup(tmp_path, days=260):
    frames, funding = {}, {}
    for k, s in enumerate(["BTC/USDT:USDT", "ETH/USDT:USDT"]):
        df = synthetic_ohlcv(days * 6, "4h", seed=20 + k, trend_blocks_days=40, trend_drift=2.0, start="2023-01-01")
        frames[s], funding[s] = df, synthetic_funding(df.index, seed=k)
    feed = FeedAdapter(frames, funding)
    cfg = Config()
    cfg.instruments = [i for i in cfg.instruments if i.base in ("BTC", "ETH")]
    cfg.regime = RegimeConfig(trend_ma_days=30, slope_days=10, vol_rank_days=60)
    cfg.risk.correlation_lookback_days = 30
    cfg.strategies = [StrategySlot("ema_trend", {"fast": 10, "slow": 60}, timeframe="4h")]
    cfg.runtime.kill_switch_file = str(tmp_path / "STOP")
    cfg.runtime.max_data_age_bars = 1.5
    ex = SimulatedExchange(feed, CostModel.from_config(cfg.costs), 10_000, {i.symbol: i.maintenance_margin_rate for i in cfg.instruments})
    return feed, cfg, ex, frames


def test_paper_loop_end_to_end_and_restart(tmp_path):
    feed, cfg, ex, frames = paper_setup(tmp_path)
    idx = frames["BTC/USDT:USDT"].index
    journal = Journal(tmp_path / "j.sqlite")
    clock = {"t": None}
    trader = Trader(cfg, Mode.PAPER, ex, journal, clock=lambda: clock["t"], sleep=lambda s: None)
    statuses = []
    for k in range(200, 700):
        feed.now = idx[k] + pd.Timedelta(minutes=5)  # kurz nach Kerzenbeginn -> Kerze k läuft noch
        clock["t"] = feed.now.to_pydatetime()
        statuses.append(trader.tick())
    assert statuses.count("ok") > 400, set(statuses)
    n_trades = journal.query("SELECT COUNT(*) AS n FROM trades")[0]["n"]
    assert n_trades > 0
    t = journal.query("SELECT * FROM trades LIMIT 1")[0]
    assert t["strategy"] and t["regime"] and t["mfe_pct"] >= 0 >= t["mae_pct"]
    assert journal.query("SELECT COUNT(*) AS n FROM equity")[0]["n"] > 400
    # Jede Entscheidung lief über die gleiche Risk Engine: Hebel nie über der Grenze
    eq = journal.query("SELECT MAX(gross_exposure) AS g FROM equity")[0]["g"]
    assert eq <= cfg.risk.max_leverage * 1.3
    # Neustart: gleicher Journal-Stand, gleiche Kerze -> keine neuen Orders
    n_orders = journal.query("SELECT COUNT(*) AS n FROM orders")[0]["n"]
    trader2 = Trader(cfg, Mode.PAPER, ex, journal, clock=lambda: clock["t"], sleep=lambda s: None)
    assert trader2.tick() == "waiting"
    assert journal.query("SELECT COUNT(*) AS n FROM orders")[0]["n"] == n_orders


def test_stale_data_triggers_kill_switch_and_flatten(tmp_path):
    feed, cfg, ex, frames = paper_setup(tmp_path)
    idx = frames["BTC/USDT:USDT"].index
    journal = Journal(tmp_path / "j.sqlite")
    clock = {"t": None}
    trader = Trader(cfg, Mode.PAPER, ex, journal, clock=lambda: clock["t"], sleep=lambda s: None)
    for k in range(200, 400):
        feed.now = idx[k] + pd.Timedelta(minutes=5)
        clock["t"] = feed.now.to_pydatetime()
        trader.tick()
    feed.stale = True
    results = []
    for k in range(400, 404):
        feed.now = idx[k] + pd.Timedelta(minutes=5)
        clock["t"] = feed.now.to_pydatetime()
        results.append(trader.tick())
    assert results[:3] == ["data_error"] * 3
    assert trader.risk.state.killed and "Datenfehler" in trader.risk.state.kill_reason
    assert all(p.qty == 0 for p in ex.get_positions())


def test_trader_refuses_backtest_mode(tmp_path):
    feed, cfg, ex, _ = paper_setup(tmp_path, days=10)
    with pytest.raises(ValueError):
        Trader(cfg, Mode.BACKTEST, ex, Journal(":memory:"))


def test_paper_exchange_state_survives_restart():
    ex, j, eng = setup()
    eng.rebalance([Intent(S, 2.0, stop_price=95.0)], "b1", {S: 0.0}, {S: 100.0})
    st = ex.to_state()
    ex2 = SimulatedExchange(None, COST, 0, {S: 0.004})
    ex2.load_state(st)
    assert ex2.account.positions[S].qty == 2.0
    assert ex2.account.cash == pytest.approx(ex.account.cash)
    stops = [o for o in ex2.get_open_orders(S) if o.type is OrderType.STOP_MARKET]
    assert len(stops) == 1 and stops[0].stop_price == 95.0
    ex2.process_bar(S, 100, 94, 96)
    assert ex2.account.positions[S].qty == 0


def test_status_report_after_paper_run(tmp_path):
    from quantbot.monitoring.status import format_status, status_report

    feed, cfg, ex, frames = paper_setup(tmp_path)
    idx = frames["BTC/USDT:USDT"].index
    journal = Journal(tmp_path / "j.sqlite")
    clock = {"t": None}
    trader = Trader(cfg, Mode.PAPER, ex, journal, clock=lambda: clock["t"], sleep=lambda s: None)
    for k in range(200, 320):
        feed.now = idx[k] + pd.Timedelta(minutes=5)
        clock["t"] = feed.now.to_pydatetime()
        trader.tick()
    st = status_report(journal, cfg.runtime.kill_switch_file)
    assert st["heartbeat"]["status"] == "ok" and st["equity"]["equity"] > 0
    text = format_status(st)
    assert "Equity" in text and "Kill Switch aus" in text


def test_cli_live_is_blocked_by_default(monkeypatch, tmp_path):
    from quantbot.cli import main
    from quantbot.config import LiveTradingDisabled

    monkeypatch.delenv("QUANTBOT_LIVE_CONFIRM", raising=False)
    with pytest.raises(LiveTradingDisabled):
        main(["run", "--mode", "live", "--journal", str(tmp_path / "x.sqlite")])
