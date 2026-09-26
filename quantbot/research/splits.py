"""Zeitliche Aufteilung. Der Out-of-Sample-Teil wird nie für Entscheidungen benutzt."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Period:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp  # exklusiv

    def __str__(self) -> str:
        return f"{self.name} {self.start:%Y-%m-%d} bis {self.end:%Y-%m-%d}"


@dataclass(frozen=True)
class Splits:
    train: Period
    validation: Period
    oos: Period

    @property
    def research(self) -> Period:
        """Train + Validation: alles, was für Entscheidungen benutzt werden darf."""
        return Period("research", self.train.start, self.validation.end)


def make_splits(index: pd.DatetimeIndex, train_frac: float, val_frac: float,
                warmup_days: int = 0) -> Splits:
    """Aufteilung nach Zeit. ``warmup_days`` am Anfang bleiben ungenutzt (Indikator-Vorlauf)."""
    start = index[0] + pd.Timedelta(days=warmup_days)
    end = index[-1] + (index[-1] - index[-2])
    total = end - start
    t1 = (start + total * train_frac).floor("D")
    t2 = (start + total * (train_frac + val_frac)).floor("D")
    if not start < t1 < t2 < end:
        raise ValueError("Zu wenig Historie für Train/Validation/OOS")
    return Splits(Period("train", start, t1), Period("validation", t1, t2), Period("oos", t2, end))


def walk_forward_windows(period: Period, train_days: int, test_days: int) -> list[tuple[Period, Period]]:
    """Rollierende Fenster innerhalb von ``period`` (nie über dessen Ende hinaus)."""
    out = []
    tr, te = pd.Timedelta(days=train_days), pd.Timedelta(days=test_days)
    test_start = period.start + tr
    while test_start + te / 2 <= period.end:
        test_end = min(test_start + te, period.end)
        out.append((Period("wf_train", test_start - tr, test_start), Period("wf_test", test_start, test_end)))
        test_start += te
    return out
