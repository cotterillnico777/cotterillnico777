"""Zeitrahmen-Hilfen. Kerzenzeitstempel sind immer der Kerzenbeginn in UTC."""

from __future__ import annotations

import pandas as pd

UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
SUPPORTED = ("15m", "1h", "4h", "1d")


def tf_seconds(tf: str) -> int:
    unit = tf[-1:]
    if unit not in UNIT_SECONDS or not tf[:-1].isdigit() or int(tf[:-1]) <= 0:
        raise ValueError(f"Ungültiger Timeframe: {tf!r} (z. B. 15m, 1h, 4h, 1d)")
    return int(tf[:-1]) * UNIT_SECONDS[unit]


def tf_delta(tf: str) -> pd.Timedelta:
    return pd.Timedelta(seconds=tf_seconds(tf))


def periods_per_year(tf: str) -> float:
    """Krypto handelt 365 Tage im Jahr, rund um die Uhr."""
    return 365 * 86400 / tf_seconds(tf)


def pandas_rule(tf: str) -> str:
    n, unit = int(tf[:-1]), tf[-1]
    return {"m": f"{n}min", "h": f"{n}h", "d": f"{n}D", "w": f"{7 * n}D"}[unit]


def to_ms(index: pd.DatetimeIndex) -> "pd.Index":
    """Zeitstempel in Millisekunden seit Epoch, unabhängig von der internen Auflösung."""
    return pd.Index(index.as_unit("ms").asi8, name=index.name)


def normalize_index(df: "pd.DataFrame") -> "pd.DataFrame":
    """Einheitliche Zeitauflösung (ns, UTC) für alle Tabellen der Pipeline."""
    df.index = pd.DatetimeIndex(df.index).tz_convert("UTC").as_unit("ns")
    df.index.name = "timestamp"
    return df
