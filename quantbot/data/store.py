"""Lokaler Datenspeicher mit Manifest (Hash je Datei) für reproduzierbare Backtests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..core.timeframes import normalize_index, to_ms

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def frame_hash(df: pd.DataFrame) -> str:
    """Inhaltshash einer Tabelle (unabhängig vom Dateiformat)."""
    h = hashlib.sha256()
    h.update(to_ms(df.index).values.tobytes())
    h.update(pd.util.hash_pandas_object(df, index=False).values.tobytes())
    h.update(",".join(map(str, df.columns)).encode())
    return h.hexdigest()[:16]


@dataclass
class DatasetInfo:
    kind: str  # ohlcv | funding
    exchange: str
    symbol: str
    timeframe: str
    rows: int
    start: str
    end: str
    sha: str
    updated_at: str
    synthetic: bool = False


class DataStore:
    """Speichert je (Börse, Symbol, Art, Timeframe) eine CSV-Datei plus Manifest."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.manifest_path = self.root / "manifest.json"

    # ---------------------------------------------------------------- Pfade
    @staticmethod
    def _key(symbol: str) -> str:
        return symbol.replace("/", "").replace(":", "_")

    def path(self, kind: str, exchange: str, symbol: str, timeframe: str = "") -> Path:
        name = f"{self._key(symbol)}_{timeframe}.csv.gz" if timeframe else f"{self._key(symbol)}.csv.gz"
        return self.root / exchange / kind / name

    # ------------------------------------------------------------- Manifest
    def manifest(self) -> dict[str, dict]:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _update_manifest(self, key: str, info: DatasetInfo) -> None:
        m = self.manifest()
        m[key] = info.__dict__
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.manifest_path)

    # ---------------------------------------------------------- Lesen/Schreiben
    def save(
        self,
        df: pd.DataFrame,
        kind: str,
        exchange: str,
        symbol: str,
        timeframe: str = "",
        synthetic: bool = False,
    ) -> DatasetInfo:
        if not df.index.is_monotonic_increasing or df.index.duplicated().any():
            raise ValueError("Index muss eindeutig und aufsteigend sein")
        p = self.path(kind, exchange, symbol, timeframe)
        p.parent.mkdir(parents=True, exist_ok=True)
        out = df.copy()
        out.index = to_ms(out.index)  # ms seit Epoch
        out.index.name = "timestamp"
        out.to_csv(p, compression="gzip")
        # Hash über den Inhalt, wie er auf der Platte liegt (nach CSV-Rundung)
        on_disk = self._read(p)
        info = DatasetInfo(
            kind=kind,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            rows=len(df),
            start=str(df.index[0]) if len(df) else "",
            end=str(df.index[-1]) if len(df) else "",
            sha=frame_hash(on_disk),
            updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            synthetic=synthetic,
        )
        self._update_manifest(str(p.relative_to(self.root)), info)
        return info

    def load(self, kind: str, exchange: str, symbol: str, timeframe: str = "") -> pd.DataFrame:
        p = self.path(kind, exchange, symbol, timeframe)
        if not p.exists():
            raise FileNotFoundError(
                f"Keine Daten: {p}. Zuerst herunterladen: python -m quantbot data download"
            )
        df = self._read(p)
        expected = self.manifest().get(str(p.relative_to(self.root)), {}).get("sha")
        if expected and frame_hash(df) != expected:
            raise ValueError(f"Hash von {p} passt nicht zum Manifest: Datei wurde verändert")
        return df

    @staticmethod
    def _read(p: Path) -> pd.DataFrame:
        df = pd.read_csv(p, index_col="timestamp", compression="gzip")
        df.index = pd.to_datetime(df.index, unit="ms", utc=True)
        return normalize_index(df.astype(float))

    def info(self, kind: str, exchange: str, symbol: str, timeframe: str = "") -> dict:
        p = self.path(kind, exchange, symbol, timeframe)
        return self.manifest().get(str(p.relative_to(self.root)), {})
