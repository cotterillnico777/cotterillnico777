"""Phase 1: Konfiguration, Betriebsmodi, Datenpipeline, Adapter-Abstraktion."""

import numpy as np
import pandas as pd
import pytest

from quantbot.config import (
    LiveTradingDisabled,
    load_config,
    resolve_mode,
)
from quantbot.config.schema import Config
from quantbot.core.timeframes import periods_per_year, tf_seconds, to_ms
from quantbot.core.types import Mode
from quantbot.data import DataStore, MarketData, resample_ohlcv, validate_ohlcv
from quantbot.data.download import download_funding, download_ohlcv
from quantbot.data.synthetic import synthetic_funding, synthetic_ohlcv
from quantbot.exchanges.base import ExchangeAdapter


# ------------------------------------------------------------------ Config
def test_default_config_is_valid_and_conservative():
    cfg = Config()
    cfg.validate()
    assert cfg.live.enabled is False
    assert cfg.risk.max_leverage <= 2.0
    assert [i.base for i in cfg.instruments] == ["BTC", "ETH", "SOL"]


def test_config_rejects_unknown_keys_and_hard_leverage(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("risk:\n  risk_per_trad: 0.01\n")
    with pytest.raises(ValueError, match="risk_per_trad"):
        load_config(p)
    p.write_text("risk:\n  max_leverage: 10\n")
    with pytest.raises(ValueError, match="harte Obergrenze"):
        load_config(p)
    p.write_text("strategies:\n  - name: x\n    timeframe: 7x\n")
    with pytest.raises(ValueError):
        load_config(p)


def test_nested_strategy_slots_are_built(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("strategies:\n  - name: donchian\n    params: {n: 20}\n    regimes: [bull]\n")
    cfg = load_config(p)
    assert cfg.strategies[0].name == "donchian" and cfg.strategies[0].params == {"n": 20}


def test_live_mode_requires_three_explicit_steps(monkeypatch):
    cfg = Config()
    monkeypatch.delenv("TRADING_MODE", raising=False)
    monkeypatch.delenv("QUANTBOT_LIVE_CONFIRM", raising=False)
    assert resolve_mode(cfg) is Mode.PAPER  # Standard
    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(LiveTradingDisabled):
        resolve_mode(cfg)
    cfg.live.enabled = True
    with pytest.raises(LiveTradingDisabled, match="QUANTBOT_LIVE_CONFIRM"):
        resolve_mode(cfg)
    monkeypatch.setenv("QUANTBOT_LIVE_CONFIRM", "yes")
    with pytest.raises(LiveTradingDisabled):
        resolve_mode(cfg)
    monkeypatch.setenv("QUANTBOT_LIVE_CONFIRM", "I_ACCEPT_REAL_MONEY_RISK")
    assert resolve_mode(cfg) is Mode.LIVE


def test_timeframes():
    assert tf_seconds("15m") == 900 and tf_seconds("4h") == 14400
    assert periods_per_year("1d") == 365
    with pytest.raises(ValueError):
        tf_seconds("0h")


# -------------------------------------------------------------- Validierung
def test_validation_detects_problems():
    df = synthetic_ohlcv(500, "1h", seed=1)
    assert validate_ohlcv(df, "1h").ok
    broken = df.drop(df.index[100:105])  # Lücke von 5 Kerzen
    broken = pd.concat([broken, broken.iloc[[10]]]).sort_index()  # Duplikat
    broken.iloc[20, broken.columns.get_loc("high")] = broken.iloc[20]["low"] * 0.9  # OHLC kaputt
    rep = validate_ohlcv(broken, "1h")
    assert rep.duplicates == 1
    assert rep.missing_bars == 5 and len(rep.gaps) == 1
    assert rep.ohlc_violations >= 1
    assert not rep.ok


def test_validation_flags_outliers_without_removing():
    df = synthetic_ohlcv(1000, "1h", seed=2)
    df.iloc[500, df.columns.get_loc("close")] *= 1.5
    df.iloc[500, df.columns.get_loc("high")] = df.iloc[500]["close"]
    rep = validate_ohlcv(df, "1h")
    assert rep.outliers and rep.rows == 1000


# ------------------------------------------------------------------- Store
def test_store_roundtrip_and_tamper_detection(tmp_path):
    store = DataStore(tmp_path)
    df = synthetic_ohlcv(300, "4h", seed=3)
    info = store.save(df, "ohlcv", "sim", "BTC/USDT:USDT", "4h", synthetic=True)
    back = store.load("ohlcv", "sim", "BTC/USDT:USDT", "4h")
    pd.testing.assert_frame_equal(back, df, check_freq=False, check_names=False, rtol=1e-12)
    assert store.info("ohlcv", "sim", "BTC/USDT:USDT", "4h")["synthetic"] is True
    assert info.sha
    # Manipulation wird erkannt
    p = store.path("ohlcv", "sim", "BTC/USDT:USDT", "4h")
    tampered = back.copy()
    tampered.iloc[5, 0] += 1
    t = tampered.copy()
    t.index = to_ms(t.index)
    t.index.name = "timestamp"
    t.to_csv(p, compression="gzip")
    with pytest.raises(ValueError, match="Hash"):
        store.load("ohlcv", "sim", "BTC/USDT:USDT", "4h")


# ---------------------------------------------------------------- Resample
def test_resample_only_complete_candles():
    df = synthetic_ohlcv(24 * 3 + 5, "1h", seed=4)  # 3 volle Tage + 5 Stunden
    d = resample_ohlcv(df, "1h", "1d")
    assert len(d) == 3
    first = df.iloc[:24]
    assert d.iloc[0]["open"] == first["open"].iloc[0]
    assert d.iloc[0]["high"] == first["high"].max()
    assert d.iloc[0]["close"] == first["close"].iloc[-1]
    with pytest.raises(ValueError):
        resample_ohlcv(df, "4h", "1h")


# ------------------------------------------------------ Download mit Adapter
class FakeAdapter(ExchangeAdapter):
    name = "fake"

    def __init__(self, df, funding):
        self.df, self.funding = df, funding
        self.calls = 0

    def get_ohlcv(self, symbol, timeframe, since=None, limit=500):
        self.calls += 1
        ms = to_ms(self.df.index)
        sel = self.df[ms >= since].iloc[:limit]
        return [[int(t.timestamp() * 1000), *r] for t, r in zip(sel.index, sel.values.tolist())]

    def get_funding_history(self, symbol, since=None, limit=1000):
        ms = to_ms(self.funding.index)
        sel = self.funding[ms >= since].iloc[:limit]
        return [(int(t.timestamp() * 1000), float(r)) for t, r in zip(sel.index, sel["rate"])]

    def get_ticker_price(self, symbol):
        return float(self.df["close"].iloc[-1])

    def get_balance(self): raise NotImplementedError
    def get_positions(self): raise NotImplementedError
    def set_leverage(self, symbol, leverage): raise NotImplementedError
    def place_order(self, order): raise NotImplementedError
    def cancel_order(self, symbol, client_id): raise NotImplementedError
    def get_order(self, symbol, client_id): raise NotImplementedError
    def get_open_orders(self, symbol=None): raise NotImplementedError


def test_download_pages_and_pipeline(tmp_path):
    df = synthetic_ohlcv(2500, "1h", seed=5, start="2023-01-01")
    fund = synthetic_funding(df.index, seed=5)
    ad = FakeAdapter(df, fund)
    got = download_ohlcv(ad, "X", "1h", df.index[0], until=df.index[-1] + pd.Timedelta(hours=1), page=1000)
    assert ad.calls >= 3
    pd.testing.assert_frame_equal(got, df.astype(float), check_freq=False, check_names=False)
    f = download_funding(ad, "X", df.index[0], until=df.index[-1], page=100)
    assert len(f) == len(fund[fund.index <= df.index[-1]])

    md = MarketData(DataStore(tmp_path), "fake")
    # Fake-Adapter liefert nur bis df.index[-1]; update lädt ab start
    rep = md.update(ad, "BTC/USDT:USDT", "1h", df.index[0])
    assert rep.ok and rep.rows == 2500
    s = md.load("BTC/USDT:USDT", "1h")
    assert len(s.ohlcv) == 2500 and s.funding is not None and s.data_hash


def test_incomplete_last_candle_is_excluded():
    from quantbot.data.download import FINALIZE_GRACE_MS

    now = pd.Timestamp.now(tz="UTC").floor("h")
    df = synthetic_ohlcv(10, "1h", seed=6, start=str(now - pd.Timedelta(hours=9)))
    ad = FakeAdapter(df, synthetic_funding(df.index))
    got = download_ohlcv(ad, "X", "1h", df.index[0])
    # letzte übernommene Kerze: endet spätestens FINALIZE_GRACE vor jetzt (laufende Kerze fehlt)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(milliseconds=FINALIZE_GRACE_MS)
    assert got.index[-1] == cutoff.floor("h") - pd.Timedelta(hours=1)
    assert np.isfinite(got.values).all()


# ----------------------------------------------------------------- Logging
def test_logging_redacts_secrets(monkeypatch, tmp_path):
    import json
    import logging

    from quantbot.monitoring.logs import setup_logging

    monkeypatch.setenv("QUANTBOT_API_SECRET", "supersecretvalue123")
    log_file = tmp_path / "x.log"
    setup_logging(str(log_file))
    logging.getLogger("t").warning("Schlüssel %s benutzt", "supersecretvalue123",
                                   extra={"data": {"k": "supersecretvalue123"}})
    for h in logging.getLogger().handlers:
        h.flush()
    text = log_file.read_text()
    assert "supersecretvalue123" not in text
    entry = json.loads(text.strip().splitlines()[-1])
    assert entry["level"] == "WARNING" and "***" in entry["msg"] and entry["data"]["k"] == "***"


def test_cli_help_runs():
    from quantbot.cli import build_parser

    p = build_parser()
    args = p.parse_args(["data", "validate", "--timeframes", "4h"])
    assert args.timeframes == ["4h"]
