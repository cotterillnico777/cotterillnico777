"""Konfiguration aus YAML laden und prüfen."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ExchangeConfig:
    id: str = "binance"
    # Testnet der Börse verwenden (falls ccxt es für die Börse unterstützt)
    sandbox: bool = False


@dataclass
class StrategyConfig:
    name: str = "ma_crossover"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskConfig:
    # Anteil des verfügbaren Quote-Guthabens (z. B. USDT) pro Einstieg
    position_fraction: float = 0.25
    # Harte Obergrenze pro Order in Quote-Währung
    max_order_value: float = 100.0
    # Orders unter diesem Wert werden nicht gesendet (Börsen-Mindestgröße)
    min_order_value: float = 10.0
    # Stop-Loss relativ zum Einstiegspreis (0.05 = 5 %), 0 = aus
    stop_loss_pct: float = 0.05
    # Tagesverlust in Quote-Währung, ab dem keine neuen Käufe mehr erfolgen
    max_daily_loss: float = 50.0


@dataclass
class BacktestConfig:
    initial_balance: float = 1000.0
    fee: float = 0.001  # 0,1 % pro Trade
    slippage: float = 0.0005  # 0,05 % ungünstigerer Ausführungspreis
    days: int = 365


@dataclass
class RuntimeConfig:
    # "paper" (Spielgeld) oder "live" (echtes Geld)
    mode: str = "paper"
    paper_balance: float = 1000.0
    poll_seconds: int = 60
    state_file: str = "state/bot_state.json"
    # Existiert diese Datei, stoppt der Bot sofort alle neuen Käufe
    kill_switch_file: str = "STOP"
    log_file: str = "state/bot.log"


@dataclass
class Config:
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

    def validate(self) -> None:
        r = self.risk
        if not 0 < r.position_fraction <= 1:
            raise ValueError("risk.position_fraction muss in (0, 1] liegen")
        if r.max_order_value <= 0 or r.min_order_value < 0:
            raise ValueError("risk.max_order_value > 0 und min_order_value >= 0 nötig")
        if r.min_order_value > r.max_order_value:
            raise ValueError("risk.min_order_value darf nicht größer als max_order_value sein")
        if not 0 <= r.stop_loss_pct < 1:
            raise ValueError("risk.stop_loss_pct muss in [0, 1) liegen")
        if r.max_daily_loss <= 0:
            raise ValueError("risk.max_daily_loss muss > 0 sein")
        if self.runtime.mode not in ("paper", "live"):
            raise ValueError("runtime.mode muss 'paper' oder 'live' sein")
        if "/" not in self.symbol:
            raise ValueError("symbol im Format BASE/QUOTE angeben, z. B. BTC/USDT")


def _build(cls: type, data: dict[str, Any] | None, path: str) -> Any:
    data = data or {}
    known = {f.name: f for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(f"Unbekannte Konfigurationsschlüssel in '{path}': {sorted(unknown)}")
    kwargs = {}
    for name, value in data.items():
        default = known[name].default_factory  # type: ignore[misc]
        sub_cls = type(default()) if callable(default) else None
        if sub_cls is not None and is_dataclass(sub_cls):
            kwargs[name] = _build(sub_cls, value, f"{path}.{name}" if path else name)
        else:
            kwargs[name] = value
    return cls(**kwargs)


def load_config(path: str | Path | None) -> Config:
    data: dict[str, Any] = {}
    if path is not None:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    cfg = _build(Config, data, "")
    cfg.validate()
    return cfg
