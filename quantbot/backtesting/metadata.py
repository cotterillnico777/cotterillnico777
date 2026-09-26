"""Reproduzierbarkeit: alles festhalten, was ein Ergebnis bestimmt."""

from __future__ import annotations

import dataclasses
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__


def git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                               text=True, timeout=5).stdout.strip()
        return f"{sha}{'-dirty' if dirty else ''}" if sha else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def run_metadata(cfg, markets: dict, extra: dict | None = None) -> dict:
    """Git-Stand, Datenhashes, Konfiguration, Kosten, Seed, Zeitraum."""
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quantbot_version": __version__,
        "git_commit": git_commit(),
        "data": {
            s: {"hash": m.data_hash, "timeframe": m.timeframe, "rows": len(m.ohlcv),
                "start": str(m.ohlcv.index[0]), "end": str(m.ohlcv.index[-1]),
                "synthetic": m.synthetic, "funding_history": m.funding is not None}
            for s, m in markets.items()
        },
        "config": dataclasses.asdict(cfg),
        "seed": cfg.research.seed,
        **(extra or {}),
    }


def save_json(obj: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    return p
