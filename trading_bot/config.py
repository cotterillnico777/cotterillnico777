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
    # Stop-Abstand: "pct" = fester Prozentsatz, "atr" = Vielfaches der
    # Average True Range (passt sich der aktuellen Schwankungsbreite an)
    stop_mode: str = "pct"
    # Stop-Loss relativ zum Einstiegspreis (0.05 = 5 %), 0 = aus (nur stop_mode: pct)
    stop_loss_pct: float = 0.05
    atr_period: int = 14
    # Stop = Einstieg - atr_multiplier × ATR (nur stop_mode: atr)
    atr_multiplier: float = 2.5
    # Trailing-Stop: Stop zieht mit dem höchsten Kurs seit Einstieg nach oben
    trailing_stop: bool = False
    # Positionsgröße: "fixed" = position_fraction vom Guthaben,
    # "risk" = so groß, dass ein Stop-Treffer risk_per_trade vom Guthaben kostet
    sizing: str = "fixed"
    risk_per_trade: float = 0.01
    # Tagesverlust in Quote-Währung, ab dem keine neuen Käufe mehr erfolgen
    max_daily_loss: float = 50.0

    @property
    def stops_enabled(self) -> bool:
        return self.stop_mode == "atr" or self.stop_loss_pct > 0

    @property
    def needs_atr(self) -> bool:
        return self.stop_mode == "atr"


@dataclass
class TrendFilterConfig:
    # Nur kaufen, wenn der höhere Zeitrahmen im Aufwärtstrend ist
    enabled: bool = False
    timeframe: str = "1d"
    period: int = 200
    kind: str = "sma"  # sma | ema
    # "entry" = nur Einstiege filtern, "exit" = zusätzlich verkaufen, wenn der Trend kippt
    mode: str = "entry"


@dataclass
class BacktestConfig:
    initial_balance: float = 1000.0
    fee: float = 0.001  # 0,1 % pro Trade
    slippage: float = 0.0005  # 0,05 % ungünstigerer Ausführungspreis
    days: int = 365


@dataclass
class OptimizeConfig:
    # Rollierende Fenster: auf train_days optimieren, auf den folgenden
    # test_days (ungesehen) prüfen, dann um test_days weiterschieben
    train_days: int = 180
    test_days: int = 60
    # Zielgröße: sharpe | return | calmar (Rendite / max. Drawdown)
    metric: str = "sharpe"
    # Kombinationen mit weniger Trades im Trainingsfenster gelten als ungültig
    min_trades: int = 5
    # Zusätzliche Märkte für den Vergleich (leer = nur symbol)
    symbols: list[str] = field(default_factory=list)
    # Eigene Raster pro Strategie, z. B. {ma_crossover: {fast: [10, 20]}}
    grids: dict[str, dict[str, list[Any]]] = field(default_factory=dict)


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
    trend_filter: TrendFilterConfig = field(default_factory=TrendFilterConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    optimize: OptimizeConfig = field(default_factory=OptimizeConfig)
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
        if r.stop_mode not in ("pct", "atr"):
            raise ValueError("risk.stop_mode muss 'pct' oder 'atr' sein")
        if r.stop_mode == "atr" and (r.atr_period < 1 or r.atr_multiplier <= 0):
            raise ValueError("risk.atr_period >= 1 und atr_multiplier > 0 nötig")
        if r.sizing not in ("fixed", "risk"):
            raise ValueError("risk.sizing muss 'fixed' oder 'risk' sein")
        if r.sizing == "risk":
            if not 0 < r.risk_per_trade <= 0.1:
                raise ValueError("risk.risk_per_trade muss in (0, 0.1] liegen (max. 10 %)")
            if not r.stops_enabled:
                raise ValueError("risk.sizing: risk braucht einen Stop-Loss")
        if r.trailing_stop and not r.stops_enabled:
            raise ValueError("risk.trailing_stop braucht einen Stop-Loss")
        if r.max_daily_loss <= 0:
            raise ValueError("risk.max_daily_loss muss > 0 sein")
        if self.runtime.mode not in ("paper", "live"):
            raise ValueError("runtime.mode muss 'paper' oder 'live' sein")
        t = self.trend_filter
        if t.kind not in ("sma", "ema") or t.mode not in ("entry", "exit") or t.period < 2:
            raise ValueError("trend_filter: kind sma|ema, mode entry|exit, period >= 2")
        if t.enabled and t.timeframe[-1] not in "mhdw":
            raise ValueError("trend_filter.timeframe z. B. 4h, 1d oder 1w")
        o = self.optimize
        if o.train_days <= 0 or o.test_days <= 0:
            raise ValueError("optimize.train_days und test_days müssen > 0 sein")
        if o.metric not in ("sharpe", "return", "calmar"):
            raise ValueError("optimize.metric muss sharpe, return oder calmar sein")
        from .backtest import TIMEFRAME_SECONDS

        if self.timeframe[-1:] not in TIMEFRAME_SECONDS or not self.timeframe[:-1].isdigit():
            raise ValueError("timeframe z. B. 15m, 1h, 4h oder 1d")
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
