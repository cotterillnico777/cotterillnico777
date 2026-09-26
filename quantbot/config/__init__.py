"""Konfiguration laden und Betriebsmodus bestimmen."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from ..core.types import Mode
from .schema import HARD_MAX_LEVERAGE, Config, StrategySlot, build

LIVE_CONFIRM_ENV = "QUANTBOT_LIVE_CONFIRM"
LIVE_CONFIRM_VALUE = "I_ACCEPT_REAL_MONEY_RISK"


def load_config(path: str | Path | None = None) -> Config:
    data = {}
    if path is not None:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    cfg = build(Config, data)
    cfg.validate()
    return cfg


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimaler .env-Loader. Überschreibt keine bereits gesetzten Variablen."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class LiveTradingDisabled(RuntimeError):
    pass


def resolve_mode(cfg: Config, requested: str | None = None) -> Mode:
    """Betriebsmodus aus Argument oder TRADING_MODE (Standard: paper).

    LIVE ist nur möglich, wenn alle drei Bedingungen erfüllt sind:
      1. TRADING_MODE=live (bzw. --mode live)
      2. live.enabled: true in der Konfiguration
      3. QUANTBOT_LIVE_CONFIRM=I_ACCEPT_REAL_MONEY_RISK in der Umgebung
    Es gibt keinen Codepfad, der LIVE automatisch aktiviert.
    """
    raw = (requested or os.environ.get("TRADING_MODE") or "paper").strip().lower()
    try:
        mode = Mode(raw)
    except ValueError:
        raise ValueError(f"Unbekannter Modus {raw!r}: backtest | paper | live") from None
    if mode is Mode.LIVE:
        missing = []
        if not cfg.live.enabled:
            missing.append("live.enabled: true in der Konfiguration")
        if os.environ.get(LIVE_CONFIRM_ENV) != LIVE_CONFIRM_VALUE:
            missing.append(f"{LIVE_CONFIRM_ENV}={LIVE_CONFIRM_VALUE} in der Umgebung")
        if missing:
            raise LiveTradingDisabled("LIVE ist deaktiviert. Es fehlt: " + "; ".join(missing))
    return mode


__all__ = [
    "Config",
    "StrategySlot",
    "HARD_MAX_LEVERAGE",
    "load_config",
    "load_dotenv",
    "resolve_mode",
    "LiveTradingDisabled",
]
