"""Datenpipeline: Download -> Validierung -> Speicher (mit Hash) -> Laden."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from ..core.timeframes import tf_delta
from .download import download_funding, download_ohlcv
from .resample import resample_ohlcv
from .store import DataStore, frame_hash
from .validate import ValidationReport, validate_ohlcv

log = logging.getLogger(__name__)


@dataclass
class MarketSeries:
    """Alles, was der Backtest für ein Symbol braucht."""

    symbol: str
    timeframe: str
    ohlcv: pd.DataFrame
    funding: pd.DataFrame | None  # None = keine Historie -> Fallback-Rate im Backtest
    data_hash: str
    synthetic: bool = False


def closed_candles(df: pd.DataFrame, timeframe: str, symbol: str = "", now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Nur abgeschlossene Kerzen (Ende <= jetzt). Die Datei bleibt unverändert; ausgeschlossene
    Kerzen werden protokolliert. Normalerweise ist nichts auszuschließen, weil der Download nur
    abgeschlossene Kerzen speichert – dies ist die zweite Sicherung für Research und Backtest."""
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    keep = df.index + tf_delta(timeframe) <= now
    if not keep.all():
        log.warning("%s %s: %d nicht abgeschlossene Kerze(n) ab %s ausgeschlossen",
                    symbol, timeframe, int((~keep).sum()), df.index[~keep][0])
    return df[keep]


class MarketData:
    def __init__(self, store: DataStore, exchange: str) -> None:
        self.store = store
        self.exchange = exchange

    def update(self, adapter, symbol: str, timeframe: str, start: pd.Timestamp) -> ValidationReport:
        """Kerzen und Funding laden bzw. ergänzen, prüfen und speichern."""
        try:
            old = self.store.load("ohlcv", self.exchange, symbol, timeframe)
            since = old.index[-1] - pd.Timedelta(days=2)  # Überlappung schließt Randlücken
        except FileNotFoundError:
            old, since = None, start
        new = download_ohlcv(adapter, symbol, timeframe, since)
        df = new if old is None else pd.concat([old, new])
        df = df[~df.index.duplicated(keep="last")].sort_index()
        report = validate_ohlcv(df, timeframe, now=pd.Timestamp.now(tz="UTC"))
        if not report.ok:
            raise ValueError(f"Daten von {symbol} {timeframe} fehlerhaft:\n{report.summary()}")
        self.store.save(df, "ohlcv", self.exchange, symbol, timeframe)

        try:
            f_old = self.store.load("funding", self.exchange, symbol)
            f_since = f_old.index[-1] - pd.Timedelta(days=1)
        except FileNotFoundError:
            f_old, f_since = None, start
        f_new = download_funding(adapter, symbol, f_since)
        f = f_new if f_old is None else pd.concat([f_old, f_new])
        f = f[~f.index.duplicated(keep="last")].sort_index()
        if len(f):
            self.store.save(f, "funding", self.exchange, symbol)
        return report

    def load(self, symbol: str, timeframe: str, start=None, end=None) -> MarketSeries:
        df = self.store.load("ohlcv", self.exchange, symbol, timeframe)
        df = closed_candles(df, timeframe, symbol)
        if start is not None:
            df = df[df.index >= pd.Timestamp(start, tz="UTC")]
        if end is not None:
            df = df[df.index < pd.Timestamp(end, tz="UTC")]
        try:
            funding = self.store.load("funding", self.exchange, symbol)
        except FileNotFoundError:
            funding = None
        info = self.store.info("ohlcv", self.exchange, symbol, timeframe)
        return MarketSeries(
            symbol=symbol,
            timeframe=timeframe,
            ohlcv=df,
            funding=funding,
            data_hash=frame_hash(df),
            synthetic=bool(info.get("synthetic", False)),
        )


__all__ = [
    "DataStore",
    "MarketData",
    "MarketSeries",
    "ValidationReport",
    "validate_ohlcv",
    "resample_ohlcv",
    "frame_hash",
    "closed_candles",
]
