"""Kerzen auf höhere Zeitrahmen verdichten. Nur vollständige Kerzen werden ausgegeben."""

from __future__ import annotations

import pandas as pd

from ..core.timeframes import pandas_rule, tf_seconds


def resample_ohlcv(df: pd.DataFrame, source_tf: str, target_tf: str) -> pd.DataFrame:
    src, dst = tf_seconds(source_tf), tf_seconds(target_tf)
    if dst < src or dst % src:
        raise ValueError(f"{target_tf} ist kein Vielfaches von {source_tf}")
    if dst == src:
        return df.copy()
    kw = {"label": "left", "closed": "left"}
    if target_tf[-1] in "mh":
        kw["origin"] = "epoch"  # Tagesgrenzen sind ohnehin 00:00 UTC
    agg = df.resample(pandas_rule(target_tf), **kw).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    counts = df["close"].resample(pandas_rule(target_tf), **kw).count()
    complete = counts == dst // src
    return agg[complete].dropna()
