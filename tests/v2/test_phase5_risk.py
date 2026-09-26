"""Phase 5: Risk Engine – jede Regel mit Grenzfall."""

import math

import numpy as np
import pandas as pd
import pytest

from quantbot.config.schema import CostConfig, RiskConfig
from quantbot.portfolio.account import Account
from quantbot.portfolio.correlation import RiskStats
from quantbot.risk.engine import RiskEngine, Signal

TS = pd.Timestamp("2024-01-01 12:00", tz="UTC")
PRICES = {"BTC": 100.0, "ETH": 100.0, "SOL": 100.0}
MMR = {"BTC": 0.004, "ETH": 0.005, "SOL": 0.01}


def risk(**kw):
    base = dict(risk_per_trade=0.01, max_leverage=3.0, max_symbol_exposure=2.0, max_gross_exposure=3.0,
                max_net_exposure=3.0, target_portfolio_vol=2.0, rebalance_threshold=0.0, min_signal=0.0,
                max_cost_in_r=10.0, liquidation_buffer=1.5)
    base.update(kw)
    return RiskConfig(**base)


def eng(cfg=None, stats=None, costs=None, **kw):
    return RiskEngine(cfg or risk(), costs or CostConfig(), MMR, stats, **kw)


def acc(cash=10_000.0):
    return Account(cash=cash, mmr=MMR)


def tgt(intents, s):
    return next((x.target_qty for x in intents if x.symbol == s), None)


def test_position_size_from_risk_and_stop():
    e = eng()
    out = e.targets(0, TS, acc(), PRICES, {"BTC": Signal("BTC", 1.0, stop_distance=5.0)})
    # 1 % von 10.000 = 100 Risiko / Stopabstand 5 = 20 Stück
    assert tgt(out, "BTC") == pytest.approx(20)
    x = next(i for i in out if i.symbol == "BTC")
    assert x.stop_price == pytest.approx(95)
    # Halbes Signal = halbe Größe, Short spiegelt
    out = e.targets(0, TS, acc(), PRICES, {"BTC": Signal("BTC", -0.5, stop_distance=5.0)})
    assert tgt(out, "BTC") == pytest.approx(-10)
    assert next(i for i in out if i.symbol == "BTC").stop_price == pytest.approx(105)


def test_leverage_is_result_not_input():
    """Engerer Stop -> größere Position -> höherer Hebel, aber gedeckelt."""
    e = eng(risk(max_symbol_exposure=1.0, max_gross_exposure=1.0, max_leverage=1.0))
    out = e.targets(0, TS, acc(), PRICES, {"BTC": Signal("BTC", 1.0, stop_distance=0.5)})
    # Ungedeckelt 200 Stück = 2x; Symbol-Obergrenze 1x -> 100 Stück
    assert tgt(out, "BTC") == pytest.approx(100)


def test_quality_filters():
    e = eng(risk(min_signal=0.2, min_stop_distance_frac=0.01, max_cost_in_r=0.2))
    assert tgt(e.targets(0, TS, acc(), PRICES, {"BTC": Signal("BTC", 0.1, 5.0)}), "BTC") is None
    assert tgt(e.targets(0, TS, acc(), PRICES, {"BTC": Signal("BTC", 1.0, 0.5)}), "BTC") is None  # Stop zu eng
    # Kosten: 2*0,05% + 2*2bps = 0,14 % von 100 = 0,14; Stop 0,6 -> 0,23 R > 0,2
    e2 = eng(risk(max_cost_in_r=0.2, min_stop_distance_frac=0.001))
    assert tgt(e2.targets(0, TS, acc(), PRICES, {"BTC": Signal("BTC", 1.0, 0.6)}), "BTC") is None
    assert e2.state.blocks["cost_too_high"] == 1


def test_gross_and_net_exposure_caps():
    e = eng(risk(max_gross_exposure=1.5, max_net_exposure=1.0, max_leverage=1.5))
    sigs = {s: Signal(s, 1.0, stop_distance=1.0) for s in PRICES}  # je 100 Stück = 1x
    out = e.targets(0, TS, acc(), PRICES, sigs)
    notional = sum(abs(tgt(out, s)) * 100 for s in PRICES)
    assert notional <= 1.0 * 10_000 + 1e-6  # Netto-Grenze (alle long) greift nach Brutto-Grenze


def test_net_cap_only_scales_dominant_side():
    e = eng(risk(max_gross_exposure=3.0, max_net_exposure=0.5))
    sigs = {"BTC": Signal("BTC", 1.0, 1.0), "ETH": Signal("ETH", 1.0, 1.0), "SOL": Signal("SOL", -1.0, 1.0)}
    out = e.targets(0, TS, acc(), PRICES, sigs)
    assert tgt(out, "SOL") == pytest.approx(-100)  # Gegenseite unverändert
    net = sum(tgt(out, s) * 100 for s in PRICES)
    assert net == pytest.approx(0.5 * 10_000)


def test_correlated_positions_are_scaled_by_portfolio_vol():
    idx = pd.date_range("2024-01-01", periods=400, freq="1D", tz="UTC")
    rng = np.random.default_rng(0)
    common = rng.normal(0, 0.03, 400)
    closes = {s: pd.Series(100 * np.exp(np.cumsum(common + rng.normal(0, 0.003, 400))), index=idx)
              for s in PRICES}
    stats = RiskStats(closes, "1d", lookback_days=60)
    assert stats.correlation(399, "BTC", "ETH") > 0.9
    sigs = {s: Signal(s, 1.0, stop_distance=5.0) for s in PRICES}
    free = eng(risk(target_portfolio_vol=2.0), stats).targets(399, TS, acc(), PRICES, sigs)
    capped = eng(risk(target_portfolio_vol=0.3), stats).targets(399, TS, acc(), PRICES, sigs)
    w = np.array([tgt(capped, s) * 100 / 10_000 for s in PRICES])
    pvol = math.sqrt(w @ stats.covariance(399, list(PRICES)) @ w)
    assert pvol == pytest.approx(0.3, rel=1e-6)
    assert tgt(capped, "BTC") < tgt(free, "BTC")


def test_risk_sizing_alone_keeps_liquidation_far_away():
    e = eng(risk(risk_per_trade=0.02))
    q = tgt(e.targets(0, TS, acc(), PRICES, {"SOL": Signal("SOL", 1.0, stop_distance=2.0)}), "SOL")
    sim = acc()
    sim.apply_fill("SOL", q, 100, 0)
    liq = sim.liquidation_price("SOL", PRICES)
    assert liq is None or 100 - liq > 20 * 2.0  # Stop kostet 2 %, Liquidation erst viel später


class FlatVol:
    def volatility(self, s, i):
        return 0.1

    def covariance(self, i, syms):
        return None


def test_stop_is_far_before_liquidation():
    # Vol-Target würde 5x wählen; bei 15 % Stop läge die Liquidation (~19 %) zu nah
    e = eng(risk(sizing="vol_target", target_vol_per_position=0.5, max_symbol_exposure=5.0,
                 max_gross_exposure=5.0, max_leverage=5.0, max_net_exposure=5.0, liquidation_buffer=3.0),
            stats=FlatVol())
    out = e.targets(0, TS, acc(), PRICES, {"SOL": Signal("SOL", 1.0, stop_distance=15.0)})
    q = tgt(out, "SOL")
    assert 0 < q < 500 * 0.9  # deutlich unter 5x (500 Stück)
    sim = acc()
    sim.apply_fill("SOL", q, 100, 0)
    liq = sim.liquidation_price("SOL", PRICES)
    assert liq is None or 100 - liq >= 3.0 * 15.0 - 1e-9
    assert e.state.blocks.get("liquidation_buffer", 0) >= 1


def test_daily_loss_limit_blocks_new_but_allows_exit():
    e = eng(risk(daily_loss_limit=0.03, weekly_loss_limit=0.06, max_drawdown_limit=0.2))
    a = acc()
    e.targets(0, TS, a, PRICES, {})  # Tagesstart 10.000
    a.cash = 9_600  # -4 %
    out = e.targets(1, TS + pd.Timedelta(hours=1), a, PRICES, {"BTC": Signal("BTC", 1.0, 5.0)})
    assert not out or tgt(out, "BTC") in (None, 0.0)
    # Bestehende Position darf geschlossen werden
    a.apply_fill("ETH", 10, 100, 0)
    out = e.targets(2, TS + pd.Timedelta(hours=2), a, PRICES, {"ETH": Signal("ETH", 0.0, 5.0)})
    assert tgt(out, "ETH") == 0.0
    # Neuer Tag -> wieder frei
    out = e.targets(3, TS + pd.Timedelta(days=1), a, PRICES, {"BTC": Signal("BTC", 1.0, 5.0)})
    assert tgt(out, "BTC") > 0


def test_max_drawdown_triggers_kill_switch_and_flattens():
    e = eng(risk(max_drawdown_limit=0.1, daily_loss_limit=0.03, weekly_loss_limit=0.05))
    a = acc()
    e.targets(0, TS, a, PRICES, {})
    a.apply_fill("BTC", 10, 100, 0)
    a.cash = 8_900 - 0  # Equity 8.900 < 9.000
    out = e.targets(1, TS, a, PRICES, {"BTC": Signal("BTC", 1.0, 5.0), "ETH": Signal("ETH", 1.0, 5.0)})
    assert e.state.killed
    assert [(x.symbol, x.target_qty) for x in out] == [("BTC", 0.0)]
    # Bleibt aus, auch wenn sich das Konto erholt
    a.cash = 20_000
    assert e.targets(2, TS, a, PRICES, {"ETH": Signal("ETH", 1.0, 5.0)}) == [x for x in [] ] or all(
        x.target_qty == 0 for x in e.targets(3, TS, a, PRICES, {"ETH": Signal("ETH", 1.0, 5.0)}))


def test_kill_switch_file(tmp_path):
    f = tmp_path / "STOP"
    e = eng(kill_switch_file=str(f))
    assert tgt(e.targets(0, TS, acc(), PRICES, {"BTC": Signal("BTC", 1.0, 5.0)}), "BTC") > 0
    f.touch()
    assert e.targets(1, TS, acc(), PRICES, {"BTC": Signal("BTC", 1.0, 5.0)}) == []
    assert e.state.killed


def test_consecutive_losses_and_large_loss_cooldown():
    e = eng(risk(max_consecutive_losses=3, cooldown_bars=10, large_loss_threshold=0.05))
    for k in range(3):
        e.on_trade_closed(-10, 10_000, i=5)
    assert e.state.cooldown_until == 15
    out = e.targets(8, TS, acc(), PRICES, {"BTC": Signal("BTC", 1.0, 5.0)})
    assert tgt(out, "BTC") in (None, 0.0)
    assert tgt(e.targets(15, TS, acc(), PRICES, {"BTC": Signal("BTC", 1.0, 5.0)}), "BTC") > 0
    e.on_trade_closed(-600, 10_000, i=20)  # 6 % Einzelverlust
    assert e.state.cooldown_until == 30
    e.on_trade_closed(+50, 10_000, i=21)
    assert e.state.consecutive_losses == 0


def test_hysteresis_prevents_small_rebalances():
    e = eng(risk(rebalance_threshold=0.25))
    a = acc()
    a.apply_fill("BTC", 20, 100, 0)
    a.positions["BTC"].stop_price = 95
    out = e.targets(0, TS, a, PRICES, {"BTC": Signal("BTC", 0.9, 5.0)})  # 18 statt 20
    assert out == []
    out = e.targets(0, TS, a, PRICES, {"BTC": Signal("BTC", 0.5, 5.0)})  # 10 statt 20
    assert tgt(out, "BTC") == pytest.approx(10)


def test_trailing_stop_only_tightens():
    e = eng(risk(trailing_stop=True))
    a = acc()
    a.apply_fill("BTC", 20, 100, 0)
    a.positions["BTC"].stop_price = 95
    up = {"BTC": 110.0, "ETH": 100.0, "SOL": 100.0}
    out = e.targets(0, TS, a, up, {"BTC": Signal("BTC", 1.0, 5.0)})
    assert next(x for x in out if x.symbol == "BTC").stop_price == pytest.approx(105)
    a.positions["BTC"].stop_price = 105
    down = {"BTC": 104.0, "ETH": 100.0, "SOL": 100.0}
    out = e.targets(0, TS, a, down, {"BTC": Signal("BTC", 1.0, 5.0)})
    stops = [x.stop_price for x in out if x.symbol == "BTC"]
    assert not stops or stops[0] >= 105
