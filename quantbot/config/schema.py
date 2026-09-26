"""Konfigurationsschema. Jeder Wert hat einen konservativen Standard.

Unbekannte Schlüssel sind ein Fehler (Tippfehler dürfen nie still ignoriert werden).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, get_args, get_origin, get_type_hints

from ..core.timeframes import tf_seconds

HARD_MAX_LEVERAGE = 5.0  # absolute technische Obergrenze, nicht per Konfiguration erhöhbar


@dataclass
class InstrumentConfig:
    symbol: str
    base: str
    maintenance_margin_rate: float = 0.005


@dataclass
class DataConfig:
    exchange: str = "binanceusdm"
    directory: str = "market_data"
    start: str = "2020-01-01"  # frühestes Datum für Downloads


@dataclass
class CostConfig:
    taker_fee: float = 0.0005  # 0,05 %
    maker_fee: float = 0.0002
    slippage_bps: float = 2.0  # feste Basis-Slippage
    slippage_range_frac: float = 0.02  # + 2 % der Kerzenspanne (Hoch - Tief)
    # Wird nur genutzt, wenn keine Funding-Historie vorliegt (im Bericht ausgewiesen)
    funding_fallback_rate: float = 0.0001  # pro 8 h = ca. 11 % p. a.
    liquidation_fee: float = 0.0125  # Anteil des Positionswerts


@dataclass
class ExecutionConfig:
    delay_bars: int = 0  # zusätzliche Verzögerung in Kerzen (Stresstest)


@dataclass
class RiskConfig:
    risk_per_trade: float = 0.005  # 0,5 % des Kontos pro Trade bis zum Stop
    sizing: str = "risk"  # risk | vol_target
    target_vol_per_position: float = 0.20  # für sizing: vol_target
    max_leverage: float = 2.0  # Standard-Obergrenze Kontohebel (Brutto-Exposure / Equity)
    max_symbol_exposure: float = 1.0  # max. Positionswert je Symbol / Equity
    max_gross_exposure: float = 2.0  # Summe |Positionswerte| / Equity
    max_net_exposure: float = 1.5  # |Summe Long - Summe Short| / Equity
    target_portfolio_vol: float = 0.30  # Portfolio-Vola (Kovarianz) wird darauf gedeckelt
    correlation_lookback_days: int = 60
    # Stop muss vor dem Liquidationspreis liegen: Liquidationsabstand >= Faktor × Stopabstand
    liquidation_buffer: float = 3.0
    daily_loss_limit: float = 0.03  # -3 % am Tag -> keine neuen Positionen bis Tageswechsel
    weekly_loss_limit: float = 0.06
    max_drawdown_limit: float = 0.20  # -20 % vom Höchststand -> Kill Switch (alles schließen)
    max_consecutive_losses: int = 5
    cooldown_bars: int = 12  # Pause nach Verlustserie / großem Verlust
    large_loss_threshold: float = 0.02  # Einzelverlust >= 2 % des Kontos -> Cooldown
    min_stop_distance_frac: float = 0.002  # Stops enger als 0,2 % werden abgelehnt
    min_trade_notional: float = 10.0


@dataclass
class RegimeConfig:
    trend_ma_days: int = 100  # Trend über Tagesdurchschnitt
    slope_days: int = 20
    sideways_band: float = 0.02  # |Steigung| unter 2 % über slope_days = seitwärts
    vol_lookback_days: int = 30
    vol_rank_days: int = 365  # Volatilitäts-Perzentil über 1 Jahr (nur Vergangenheit)
    high_vol_pct: float = 0.70
    low_vol_pct: float = 0.30


@dataclass
class StrategySlot:
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    symbols: list[str] = field(default_factory=list)  # leer = alle
    timeframe: str = "4h"
    weight: float = 1.0
    # Regime, in denen die Strategie handeln darf (leer = alle)
    regimes: list[str] = field(default_factory=list)


@dataclass
class ResearchConfig:
    train_frac: float = 0.6
    validation_frac: float = 0.2  # Rest = Out-of-Sample
    wf_train_days: int = 365
    wf_test_days: int = 90
    fee_stress: list[float] = field(default_factory=lambda: [2.0, 3.0])
    slippage_stress: list[float] = field(default_factory=lambda: [2.0, 3.0])
    delay_stress: list[int] = field(default_factory=lambda: [1, 2])
    monte_carlo_runs: int = 1000
    seed: int = 42
    min_trades: int = 30


@dataclass
class RuntimeConfig:
    poll_seconds: int = 30
    database: str = "state/quantbot.sqlite"
    log_file: str = "state/quantbot.log"
    kill_switch_file: str = "STOP"
    paper_balance: float = 10_000.0
    max_price_deviation: float = 0.15  # Kurs springt > 15 % gegenüber letzter Kerze -> Datenfehler
    max_order_failures: int = 3
    max_data_age_bars: float = 2.5


@dataclass
class LiveConfig:
    # Muss bewusst auf true gesetzt werden UND TRADING_MODE=live UND Bestätigung per Umgebung.
    enabled: bool = False


@dataclass
class Config:
    instruments: list[InstrumentConfig] = field(
        default_factory=lambda: [
            InstrumentConfig("BTC/USDT:USDT", "BTC", 0.004),
            InstrumentConfig("ETH/USDT:USDT", "ETH", 0.005),
            InstrumentConfig("SOL/USDT:USDT", "SOL", 0.01),
        ]
    )
    data: DataConfig = field(default_factory=DataConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    strategies: list[StrategySlot] = field(default_factory=list)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    live: LiveConfig = field(default_factory=LiveConfig)
    initial_equity: float = 10_000.0

    def instrument(self, symbol: str) -> InstrumentConfig:
        for inst in self.instruments:
            if inst.symbol == symbol or inst.base == symbol:
                return inst
        raise KeyError(f"Unbekanntes Instrument: {symbol}")

    def validate(self) -> None:
        r = self.risk
        _check(0 < r.risk_per_trade <= 0.02, "risk.risk_per_trade muss in (0, 0.02] liegen")
        _check(r.sizing in ("risk", "vol_target"), "risk.sizing: risk | vol_target")
        _check(
            1.0 <= r.max_leverage <= HARD_MAX_LEVERAGE,
            f"risk.max_leverage muss in [1, {HARD_MAX_LEVERAGE}] liegen (harte Obergrenze)",
        )
        _check(0 < r.max_symbol_exposure <= r.max_gross_exposure, "Exposure-Grenzen inkonsistent")
        _check(r.max_gross_exposure <= r.max_leverage, "max_gross_exposure darf max_leverage nicht übersteigen")
        _check(0 < r.max_net_exposure <= r.max_gross_exposure, "max_net_exposure ungültig")
        _check(r.liquidation_buffer >= 1.5, "risk.liquidation_buffer muss >= 1.5 sein")
        _check(0 < r.daily_loss_limit <= r.weekly_loss_limit < r.max_drawdown_limit < 1, "Verlustlimits inkonsistent")
        _check(r.max_consecutive_losses >= 1 and r.cooldown_bars >= 0, "Verlustserie/Cooldown ungültig")
        _check(0 < r.target_portfolio_vol <= 2, "risk.target_portfolio_vol ungültig")
        c = self.costs
        _check(c.taker_fee >= 0 and c.maker_fee >= 0 and c.slippage_bps >= 0, "Kosten dürfen nicht negativ sein")
        _check(self.execution.delay_bars >= 0, "execution.delay_bars >= 0")
        rs = self.research
        _check(0 < rs.train_frac < 1 and 0 < rs.validation_frac < 1 and rs.train_frac + rs.validation_frac < 1,
               "research: train_frac + validation_frac < 1")
        for s in self.strategies:
            tf_seconds(s.timeframe)
            _check(s.weight >= 0, f"Gewicht von {s.name} muss >= 0 sein")
        _check(len({i.symbol for i in self.instruments}) == len(self.instruments), "Doppelte Instrumente")
        for inst in self.instruments:
            _check(0 < inst.maintenance_margin_rate < 0.2, f"MMR von {inst.symbol} unplausibel")


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def build(cls: type, data: Any, path: str = "") -> Any:
    """Dataclass rekursiv aus einem Dict bauen, unbekannte Schlüssel ablehnen."""
    if not is_dataclass(cls):
        return data
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"'{path or 'root'}' muss ein Objekt sein")
    hints = get_type_hints(cls)
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Unbekannte Schlüssel in '{path or 'root'}': {sorted(unknown)}")
    kwargs = {}
    for name, value in data.items():
        tp = hints[name]
        sub = f"{path}.{name}" if path else name
        if is_dataclass(tp):
            kwargs[name] = build(tp, value, sub)
        elif get_origin(tp) is list and get_args(tp) and is_dataclass(get_args(tp)[0]):
            item = get_args(tp)[0]
            kwargs[name] = [build(item, v, f"{sub}[{i}]") for i, v in enumerate(value or [])]
        else:
            kwargs[name] = value
    return cls(**kwargs)
