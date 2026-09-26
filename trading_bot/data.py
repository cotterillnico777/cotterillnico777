"""Historische Kerzen (OHLCV) von der Börse laden, mit CSV-Cache."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def candles_to_frame(rows: list[list[float]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    return df.astype(float)


def fetch_history(exchange, symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """Lädt ``days`` Tage Historie seitenweise über ccxt."""
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    since = exchange.milliseconds() - days * 86_400_000
    rows: list[list[float]] = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        next_since = batch[-1][0] + tf_ms
        if next_since <= since or next_since > exchange.milliseconds():
            break
        since = next_since
        time.sleep(exchange.rateLimit / 1000)
    if not rows:
        raise RuntimeError(f"Keine Kerzen für {symbol} {timeframe} erhalten")
    return candles_to_frame(rows)


def load_history(
    exchange, symbol: str, timeframe: str, days: int, cache_dir: str | Path = "data"
) -> pd.DataFrame:
    cache = Path(cache_dir) / f"{exchange.id}_{symbol.replace('/', '-')}_{timeframe}_{days}d.csv"
    if cache.exists() and time.time() - cache.stat().st_mtime < 6 * 3600:
        log.info("Lade Kerzen aus Cache %s", cache)
        return pd.read_csv(cache, index_col="timestamp", parse_dates=["timestamp"])
    df = fetch_history(exchange, symbol, timeframe, days)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache)
    return df


def load_csv(path: str | Path) -> pd.DataFrame:
    """CSV mit Spalten timestamp,open,high,low,close,volume laden."""
    df = pd.read_csv(path)
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"CSV fehlen Spalten: {sorted(missing)}")
    ts = df["timestamp"]
    df["timestamp"] = (
        pd.to_datetime(ts, unit="ms", utc=True)
        if pd.api.types.is_numeric_dtype(ts)
        else pd.to_datetime(ts, utc=True)
    )
    return df[COLUMNS].set_index("timestamp").sort_index().astype(float)
