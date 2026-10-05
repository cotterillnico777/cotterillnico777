"""Historische Daten über einen ExchangeAdapter laden (seitenweise, mit Wiederholung)."""

from __future__ import annotations

import logging
import time

import pandas as pd

from ..core.timeframes import normalize_index, tf_seconds
from ..exchanges.base import ExchangeAdapter

log = logging.getLogger(__name__)

FINALIZE_GRACE_MS = 120_000  # Kerzen erst 2 min nach Schluss übernehmen


def _retry(fn, attempts: int = 5, base_delay: float = 2.0):
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - Netzwerkfehler aller Art
            if i == attempts - 1:
                raise
            wait = base_delay * 2**i
            log.warning("Abruf fehlgeschlagen (%s), neuer Versuch in %.0fs", exc, wait)
            time.sleep(wait)


def download_ohlcv(
    adapter: ExchangeAdapter,
    symbol: str,
    timeframe: str,
    since: pd.Timestamp,
    until: pd.Timestamp | None = None,
    page: int = 1000,
) -> pd.DataFrame:
    """Alle *abgeschlossenen* Kerzen von ``since`` bis ``until`` (Standard: jetzt)."""
    step_ms = tf_seconds(timeframe) * 1000
    now_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    end_ms = int(until.timestamp() * 1000) if until is not None else now_ms
    cursor = int(since.timestamp() * 1000)
    rows: dict[int, list[float]] = {}
    while cursor < end_ms:
        batch = _retry(lambda: adapter.get_ohlcv(symbol, timeframe, since=cursor, limit=page))
        if not batch:
            break
        for r in batch:
            # Nur abgeschlossene Kerzen im gewünschten Zeitraum
            # (+ Puffer: direkt nach Schluss kann die Börse die Kerze noch nachführen)
            if r[0] + step_ms <= min(end_ms, now_ms - FINALIZE_GRACE_MS) and r[0] >= cursor - step_ms:
                rows[int(r[0])] = r
        nxt = int(batch[-1][0]) + step_ms
        if nxt <= cursor:
            break
        cursor = nxt
    return _to_frame(list(rows.values()), ["open", "high", "low", "close", "volume"])


def download_funding(
    adapter: ExchangeAdapter,
    symbol: str,
    since: pd.Timestamp,
    until: pd.Timestamp | None = None,
    page: int = 1000,
) -> pd.DataFrame:
    """Funding-Historie: Spalte ``rate`` je Funding-Zeitpunkt."""
    end_ms = int((until or pd.Timestamp.now(tz="UTC")).timestamp() * 1000)
    cursor = int(since.timestamp() * 1000)
    rows: dict[int, list[float]] = {}
    while cursor < end_ms:
        batch = _retry(lambda: adapter.get_funding_history(symbol, since=cursor, limit=page))
        if not batch:
            break
        for ts, rate in batch:
            if ts <= end_ms:
                rows[int(ts)] = [int(ts), float(rate)]
        nxt = int(batch[-1][0]) + 1
        if nxt <= cursor:
            break
        cursor = nxt
    return _to_frame(list(rows.values()), ["rate"])


def _to_frame(rows: list[list[float]], columns: list[str]) -> pd.DataFrame:
    if not rows:
        return normalize_index(pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz="UTC")))
    df = pd.DataFrame(rows, columns=["timestamp", *columns])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return normalize_index(df.drop_duplicates("timestamp").set_index("timestamp").sort_index().astype(float))
