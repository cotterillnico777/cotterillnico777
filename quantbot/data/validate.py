"""Datenqualität prüfen. Probleme werden gemeldet, nie stillschweigend "repariert"."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..core.timeframes import tf_delta

OHLCV = ["open", "high", "low", "close", "volume"]


@dataclass
class ValidationReport:
    rows: int
    start: str | None
    end: str | None
    duplicates: int = 0
    unsorted: bool = False
    missing_bars: int = 0
    gaps: list[tuple[str, str, int]] = field(default_factory=list)  # (von, bis, fehlende Kerzen)
    ohlc_violations: int = 0
    non_positive: int = 0
    nan_rows: int = 0
    outliers: list[tuple[str, float]] = field(default_factory=list)  # Beispiele (Zeit, Rendite), max. 50
    outlier_count: int = 0  # tatsächliche Anzahl (die Liste oben ist gekürzt)
    outlier_threshold: float = float("nan")  # |Log-Rendite| ab der eine Kerze als extrem gilt
    zero_volume: int = 0
    zero_volume_moving: int = 0  # Volumen 0, aber Preis bewegt sich -> inkonsistent
    negative_volume: int = 0
    open_candle: str | None = None  # Zeitstempel einer noch nicht abgeschlossenen Kerze

    @property
    def coverage(self) -> float:
        total = self.rows + self.missing_bars
        return self.rows / total if total else 0.0

    @property
    def errors(self) -> list[str]:
        """Harte Fehler: Daten sind so nicht verwendbar."""
        e = []
        if self.duplicates:
            e.append(f"{self.duplicates} doppelte Zeitstempel")
        if self.unsorted:
            e.append("Zeitstempel nicht aufsteigend")
        if self.ohlc_violations:
            e.append(f"{self.ohlc_violations} Kerzen mit inkonsistentem OHLC")
        if self.non_positive:
            e.append(f"{self.non_positive} Kerzen mit Preis <= 0")
        if self.nan_rows:
            e.append(f"{self.nan_rows} Zeilen mit fehlenden Werten")
        if self.negative_volume:
            e.append(f"{self.negative_volume} Kerzen mit negativem Volumen")
        if self.zero_volume_moving:
            e.append(f"{self.zero_volume_moving} Kerzen ohne Volumen, aber mit Preisbewegung")
        if self.open_candle:
            e.append(f"laufende (nicht abgeschlossene) Kerze {self.open_candle}")
        return e

    @property
    def warnings(self) -> list[str]:
        w = []
        if self.missing_bars:
            w.append(f"{self.missing_bars} fehlende Kerzen in {len(self.gaps)} Lücken (Abdeckung {self.coverage:.2%})")
        if self.outlier_count:
            w.append(f"{self.outlier_count} extreme Kursbewegungen (|Log-Rendite| > {self.outlier_threshold:.4f}; "
                     "Details: python -m quantbot data audit)")
        if self.zero_volume:
            w.append(f"{self.zero_volume} Kerzen ohne Volumen (ohne Preisbewegung, kein Handel)")
        return w

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = [f"{self.rows} Kerzen, {self.start} bis {self.end}, Abdeckung {self.coverage:.2%}"]
        lines += [f"FEHLER: {e}" for e in self.errors]
        lines += [f"Warnung: {w}" for w in self.warnings]
        return "\n".join(lines)


def outlier_mask(close: pd.Series, outlier_sigma: float = 12.0) -> tuple[pd.Series, pd.Series, float]:
    """(Maske, Log-Rendite, Schwelle). Extrem = |r - Median| > outlier_sigma × robuste Streuung (MAD × 1,4826).

    Die Schwelle ist relativ zur typischen Bewegung des Zeitrahmens. Krypto-Renditen haben
    breite Ränder; bei 15m ist die typische Bewegung klein, daher gibt es dort mehr Treffer.
    """
    r = np.log(close).diff().dropna()
    if len(r) <= 50:
        return pd.Series(False, index=r.index), r, float("nan")
    med = r.median()
    mad = (r - med).abs().median() * 1.4826
    if not mad > 0:
        return pd.Series(False, index=r.index), r, float("nan")
    return (r - med).abs() > outlier_sigma * mad, r, float(outlier_sigma * mad + abs(med))


def validate_ohlcv(df: pd.DataFrame, timeframe: str, outlier_sigma: float = 12.0,
                   now: pd.Timestamp | None = None) -> ValidationReport:
    """``now``: Zeitpunkt, zu dem die Daten vorlagen; Kerzen mit Ende > now sind nicht abgeschlossen."""
    idx = df.index
    rep = ValidationReport(
        rows=len(df),
        start=str(idx[0]) if len(df) else None,
        end=str(idx[-1]) if len(df) else None,
    )
    if not len(df):
        return rep
    rep.duplicates = int(idx.duplicated().sum())
    rep.unsorted = not idx.is_monotonic_increasing
    rep.nan_rows = int(df[OHLCV].isna().any(axis=1).sum())
    rep.non_positive = int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    hi_bad = df["high"] < df[["open", "close"]].max(axis=1) - 1e-12
    lo_bad = df["low"] > df[["open", "close"]].min(axis=1) + 1e-12
    rep.ohlc_violations = int((hi_bad | lo_bad | (df["high"] < df["low"])).sum())
    zero = df["volume"] == 0
    flat = (df["high"] - df["low"]).abs() <= 1e-12
    rep.zero_volume = int((zero & flat).sum())
    rep.zero_volume_moving = int((zero & ~flat).sum())
    rep.negative_volume = int((df["volume"] < 0).sum())

    step = tf_delta(timeframe)
    if now is not None and idx.max() + step > now:
        rep.open_candle = str(idx.max())
    clean = idx[~idx.duplicated()].sort_values()
    diffs = clean[1:] - clean[:-1]
    for pos in np.nonzero(diffs > step)[0]:
        missing = int(diffs[pos] / step) - 1
        rep.missing_bars += missing
        rep.gaps.append((str(clean[pos]), str(clean[pos + 1]), missing))

    # Ausreißer: Log-Rendite gegenüber robuster Streuung (Median-Abweichung)
    mask, r, thr = outlier_mask(df["close"], outlier_sigma)
    rep.outlier_threshold = thr
    rep.outlier_count = int(mask.sum())
    rep.outliers = [(str(t), float(r[t])) for t in mask[mask].index[:50]]
    return rep
