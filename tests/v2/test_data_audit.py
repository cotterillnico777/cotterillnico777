"""Datenprüfung vor der Forschung. Synthetische Daten = reine Funktionstests."""

import numpy as np
import pandas as pd

from quantbot.data import DataStore, closed_candles, resample_ohlcv, validate_ohlcv
from quantbot.data.audit import audit_all, write_audit
from quantbot.data.synthetic import synthetic_funding, synthetic_ohlcv

SYMS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]


def test_outlier_count_is_not_capped_at_50():
    df = synthetic_ohlcv(20_000, "15m", seed=1)
    spikes = df.index[100::200][:80]
    for ts in spikes:  # 80 echte Sprünge von +20 %
        i = df.index.get_loc(ts)
        df.iloc[i:, :4] *= 1.2
    rep = validate_ohlcv(df, "15m")
    assert rep.outlier_count >= 80
    assert len(rep.outliers) == 50  # Beispielliste bleibt gekürzt
    assert rep.outlier_threshold > 0
    assert f"{rep.outlier_count} extreme" in rep.summary()


def test_open_candle_is_error_and_excluded_on_load():
    df = synthetic_ohlcv(100, "15m", start="2024-01-01")
    last_end = df.index[-1] + pd.Timedelta("15min")
    assert validate_ohlcv(df, "15m", now=last_end).open_candle is None
    rep = validate_ohlcv(df, "15m", now=last_end - pd.Timedelta("1min"))
    assert rep.open_candle == str(df.index[-1]) and not rep.ok
    kept = closed_candles(df, "15m", now=last_end - pd.Timedelta("1min"))
    assert len(kept) == len(df) - 1 and kept.index[-1] == df.index[-2]
    assert len(df) == 100  # Original unverändert


def test_zero_volume_flat_is_warning_moving_is_error_negative_is_error():
    df = synthetic_ohlcv(200, "1h")
    t = df.index[50]
    df.loc[t, ["open", "high", "low", "close"]] = df["close"].iloc[49]
    df.loc[t, "volume"] = 0
    rep = validate_ohlcv(df, "1h")
    assert rep.zero_volume == 1 and rep.ok
    df.loc[df.index[60], "volume"] = 0  # bewegte Kerze ohne Volumen
    df.loc[df.index[70], "volume"] = -1
    rep = validate_ohlcv(df, "1h")
    assert rep.zero_volume_moving == 1 and rep.negative_volume == 1 and not rep.ok


def _store(tmp_path, n_days=40, mutate=None):
    store = DataStore(tmp_path)
    now = pd.Timestamp("2024-03-01", tz="UTC")
    for k, s in enumerate(SYMS):
        base = synthetic_ohlcv(n_days * 96, "15m", seed=k, start="2024-01-01")
        if mutate:
            base = mutate(s, base)
        store.save(base, "ohlcv", "ex", s, "15m")
        for tf in ("1h", "4h", "1d"):
            store.save(resample_ohlcv(base, "15m", tf), "ohlcv", "ex", s, tf)
        store.save(synthetic_funding(base.index, seed=k), "funding", "ex", s)
    return store, now


def test_audit_clean_data_passes(tmp_path):
    store, now = _store(tmp_path)
    res = audit_all(store, "ex", SYMS, ["15m", "1h", "4h", "1d"], now=now)
    grades = {(a.symbol, a.timeframe): a.grade for a in res["series"]}
    assert set(grades.values()) == {"PASS"}, [(a.symbol, a.timeframe, a.reasons) for a in res["series"]]
    assert all(g == "PASS" for g, _, _ in res["funding"].values())
    path = write_audit(res, tmp_path / "audit")
    assert "| BTC/USDT:USDT | PASS | PASS | PASS | PASS | PASS |" in path.read_text()


def test_audit_real_move_confirmed_and_maintenance_detected(tmp_path):
    maint = pd.date_range("2024-01-20 06:00", periods=4, freq="15min", tz="UTC")
    crash = pd.Timestamp("2024-01-25 12:00", tz="UTC")

    def mutate(s, df):
        df = df.copy()
        i = df.index.get_loc(crash)
        df.iloc[i:, :4] *= 0.8  # marktweiter Einbruch, bleibt bestehen
        df.iloc[i, df.columns.get_loc("open")] = df["close"].iloc[i - 1]
        df.iloc[i, df.columns.get_loc("high")] = df.iloc[i][["open", "close", "high"]].max()
        for t in maint:  # Wartung: flach auf letztem Kurs, Volumen 0, bei allen Symbolen
            j = df.index.get_loc(t)
            df.iloc[j, :4] = df["close"].iloc[j - 1]
            df.iloc[j, df.columns.get_loc("volume")] = 0.0
        return df

    store, now = _store(tmp_path, mutate=mutate)
    res = audit_all(store, "ex", SYMS, ["15m", "1h", "4h", "1d"], now=now)
    a = next(x for x in res["series"] if x.symbol == SYMS[0] and x.timeframe == "15m")
    assert a.grade == "WARN"  # Wartung = Hinweis, keine Verletzung
    assert crash in a.outliers.index
    assert a.outliers.loc[crash, "bewertung"].startswith("echt")
    assert SYMS[1] in a.outliers.loc[crash, "gleichzeitig_bei"]
    assert len(a.zero_volume) == 4 and a.zero_volume["ursache"].str.contains("Börsenwartung").all()
    assert not any(x.grade == "FAIL" for x in res["series"])


def test_audit_fails_on_crosstf_mismatch_and_open_candle(tmp_path):
    store, now = _store(tmp_path)
    h = store.load("ohlcv", "ex", SYMS[0], "1h")
    h.iloc[10, h.columns.get_loc("high")] *= 1.05  # 1h-Hoch passt nicht zu den 15m-Kerzen
    store.save(h, "ohlcv", "ex", SYMS[0], "1h")
    res = audit_all(store, "ex", SYMS, ["15m", "1h"], now=now)
    a = next(x for x in res["series"] if x.symbol == SYMS[0] and x.timeframe == "1h")
    assert a.grade == "FAIL" and len(a.crosstf) == 1

    # Kerze, die beim Speichern noch lief
    df = store.load("ohlcv", "ex", SYMS[1], "15m")
    info = store.save(df, "ohlcv", "ex", SYMS[1], "15m")
    m = store.manifest()
    key = next(k for k in m if "ETHUSDT" in k and k.endswith("_15m.csv.gz"))
    m[key]["updated_at"] = str(df.index[-1] + pd.Timedelta("5min"))
    store.manifest_path.write_text(__import__("json").dumps(m))
    res = audit_all(store, "ex", SYMS, ["15m"], now=now)
    b = next(x for x in res["series"] if x.symbol == SYMS[1])
    assert b.grade == "FAIL" and any("laufende" in r for r in b.reasons)
    assert info.rows == len(df)


def test_engine_does_not_fill_on_zero_volume_bar():
    from quantbot.backtesting.costs import CostModel
    from quantbot.backtesting.engine import BacktestEngine
    from quantbot.core.types import Intent
    from quantbot.data import MarketSeries

    idx = pd.date_range("2024-01-01", periods=6, freq="1h", tz="UTC")
    px = np.array([100, 101, 101, 103, 104, 105], float)
    df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px, "volume": [1, 1, 0, 1, 1, 1.0]}, index=idx)
    m = MarketSeries("X", "1h", df, pd.DataFrame({"rate": [0.0]}, index=idx[:1]), "h")

    class Once:
        def decide(self, view):
            return [Intent("X", 1.0)] if view.i == 1 else []

    eng = BacktestEngine({"X": m}, CostModel(0, 0, 0, 0, 0, 0), 1000.0, {"X": 0.005})
    res = eng.run(Once())
    assert res.trades.iloc[0].entry_time == idx[3]  # Kerze 2 ohne Handel -> nächste Kerze
