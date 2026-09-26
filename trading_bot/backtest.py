"""Backtest einer Strategie auf historischen Kerzen.

Ablauf pro Kerze t:
  1. Offene Position: Stop-Loss prüfen (Tief der Kerze t).
  2. Signal aus Kerze t-1 wird zum Eröffnungskurs von Kerze t ausgeführt.
So fließen keine zukünftigen Daten in eine Entscheidung ein.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import BacktestConfig, RiskConfig
from .indicators import atr, realized_vol
from .risk import plan_rebalance, stop_price, trail_stop
from .strategies import Strategy

TIMEFRAME_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def periods_per_year(timeframe: str) -> float:
    unit = timeframe[-1]
    if unit not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unbekannter Timeframe: {timeframe}")
    return 365 * 86400 / (int(timeframe[:-1]) * TIMEFRAME_SECONDS[unit])


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    amount: float
    cost: float  # eingesetzte Quote-Währung inkl. Gebühr
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    proceeds: float | None = None  # erhaltene Quote-Währung nach Gebühr
    exit_reason: str = ""

    @property
    def pnl(self) -> float:
        return (self.proceeds or 0.0) - self.cost

    @property
    def return_pct(self) -> float:
        return self.pnl / self.cost * 100 if self.cost else 0.0


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: list[Trade]
    metrics: dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        m = self.metrics
        lines = [
            f"Zeitraum:             {m['start']} bis {m['end']}",
            f"Startkapital:         {m['initial']:.2f}",
            f"Endkapital:           {m['final']:.2f}",
            f"Gesamtrendite:        {m['total_return_pct']:+.2f} %",
            f"Buy & Hold (100 %):   {m['buy_hold_pct']:+.2f} %",
            f"Max. Drawdown:        {m['max_drawdown_pct']:.2f} %",
            f"Sharpe (annualisiert): {m['sharpe']:.2f}",
            f"Anzahl Trades:        {int(m['trades'])}",
            f"Trefferquote:         {m['win_rate_pct']:.1f} %",
            f"Ø Rendite pro Trade:  {m['avg_trade_pct']:+.2f} %",
            f"Stop ausgelöst:       {int(m['stops'])} (davon mit Gewinn: {int(m['stops_in_profit'])})",
            f"Zeit im Markt:        {m['exposure_pct']:.1f} % (Ø investiert {m['avg_exposure_pct']:.1f} %)",
            f"Orders:               {int(m['orders'])}",
        ]
        return "\n".join(lines)


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    risk: RiskConfig,
    bt: BacktestConfig,
    timeframe: str,
    signals: pd.Series | None = None,
    atr_series: pd.Series | None = None,
    vol_series: pd.Series | None = None,
) -> BacktestResult:
    """``signals`` kann vorberechnet übergeben werden (z. B. auf einer längeren
    Historie, damit Indikatoren am Fensteranfang schon eingeschwungen sind)."""
    if signals is None:
        if len(df) <= strategy.warmup + 1:
            raise ValueError(
                f"Zu wenige Kerzen ({len(df)}) für {strategy} (Warmup {strategy.warmup})"
            )
        signals = strategy.generate_signals(df)
    elif len(df) < 2:
        raise ValueError("Mindestens 2 Kerzen nötig")
    signals = signals.reindex(df.index).fillna(0).astype(float).clip(0, 1)

    if atr_series is None and risk.needs_atr:
        atr_series = atr(df, risk.atr_period)
    if vol_series is None and risk.needs_vol:
        vol_series = vol_for(df, risk, timeframe)
    nan = np.full(len(df), np.nan)
    atr_v = atr_series.reindex(df.index).values if atr_series is not None else nan
    vol_v = vol_series.reindex(df.index).values if vol_series is not None else nan

    cash = bt.initial_balance
    amount = 0.0
    open_trade: Trade | None = None
    stop: float | None = None
    highest = 0.0
    held_weight, unit_value = 0.0, 0.0
    # Nach einem Stop-Loss erst wieder einsteigen, wenn das Signal zwischendurch flat war
    wait_for_reset = False
    trades: list[Trade] = []
    equity = []
    exposure = []
    orders = 0

    opens, highs = df["open"].values, df["high"].values
    lows, closes = df["low"].values, df["close"].values
    sig = signals.values

    def buy(ts, value):
        nonlocal cash, amount, open_trade, orders
        price = opens_i * (1 + bt.slippage)
        got = value * (1 - bt.fee) / price
        cash -= value
        amount += got
        orders += 1
        if open_trade is None:
            open_trade = Trade(ts, price, got, value, proceeds=0.0)
        else:
            open_trade.cost += value
            open_trade.amount += got

    def sell(ts, price, qty, reason):
        nonlocal cash, amount, open_trade, stop, orders, held_weight
        proceeds = qty * price * (1 - bt.fee)
        cash += proceeds
        amount -= qty
        orders += 1
        open_trade.proceeds += proceeds
        open_trade.exit_time, open_trade.exit_price = ts, price
        if amount <= 1e-12:
            open_trade.exit_reason = reason
            trades.append(open_trade)
            open_trade, amount, stop, held_weight = None, 0.0, None, 0.0

    for i, ts in enumerate(df.index):
        opens_i = opens[i]
        # 1. Signal der vorherigen Kerze zum Eröffnungskurs ausführen
        if i > 0:
            target = sig[i - 1]
            if target <= 0:
                wait_for_reset = False
            if not (wait_for_reset and open_trade is None):
                # ATR und Volatilität der letzten abgeschlossenen Kerze
                prev_atr, prev_vol = atr_v[i - 1], vol_v[i - 1]
                order = plan_rebalance(
                    target, held_weight, unit_value, amount * opens_i,
                    cash + amount * opens_i, cash, risk, opens_i, prev_atr, prev_vol,
                )
                if order.action in ("open", "buy"):
                    was_flat = open_trade is None
                    buy(ts, order.value)
                    if was_flat:
                        stop = stop_price(open_trade.entry_price, risk, prev_atr)
                        highest = open_trade.entry_price
                elif order.action in ("sell", "close"):
                    qty = amount if order.action == "close" else amount * order.value
                    sell(ts, opens_i * (1 - bt.slippage), qty, "signal")
                if order.action is not None:
                    held_weight, unit_value = order.weight, order.unit_value

        # 2. Stop-Loss innerhalb der Kerze (Gap unter den Stop: Ausführung zum Open)
        if open_trade is not None and stop is not None and lows[i] <= stop:
            sell(ts, min(opens_i, stop) * (1 - bt.slippage), amount, "stop_loss")
            wait_for_reset = True

        # 3. Trailing-Stop mit dem Hoch dieser Kerze nachziehen (gilt ab nächster Kerze)
        if open_trade is not None and risk.trailing_stop:
            highest = max(highest, highs[i])
            stop = trail_stop(stop, highest, risk, atr_v[i])

        eq = cash + amount * closes[i]
        equity.append(eq)
        exposure.append(amount * closes[i] / eq if eq > 0 else 0.0)

    equity_s = pd.Series(equity, index=df.index, name="equity")
    metrics = _metrics(df, equity_s, trades, bt, timeframe, exposure, open_trade)
    metrics["orders"] = orders
    return BacktestResult(equity=equity_s, trades=trades, metrics=metrics)


def vol_for(df: pd.DataFrame, risk: RiskConfig, timeframe: str) -> pd.Series:
    """Annualisierte Volatilität über ``risk.vol_lookback_days`` für jede Kerze."""
    ppy = periods_per_year(timeframe)
    window = max(2, round(risk.vol_lookback_days * ppy / 365))
    return realized_vol(df["close"], window, ppy)


def _metrics(df, equity, trades, bt, timeframe, exposure, open_trade) -> dict:
    rets = equity.pct_change().dropna()
    std = rets.std()
    sharpe = (
        rets.mean() / std * math.sqrt(periods_per_year(timeframe))
        if std and not math.isnan(std)
        else 0.0
    )
    peak = equity.cummax()
    drawdown = ((equity - peak) / peak).min() * 100
    wins = [t for t in trades if t.pnl > 0]
    return {
        "start": str(df.index[0]),
        "end": str(df.index[-1]),
        "initial": bt.initial_balance,
        "final": float(equity.iloc[-1]),
        "total_return_pct": (equity.iloc[-1] / bt.initial_balance - 1) * 100,
        "buy_hold_pct": (df["close"].iloc[-1] / df["open"].iloc[0] - 1) * 100,
        "max_drawdown_pct": float(drawdown),
        "sharpe": float(sharpe),
        "trades": len(trades),
        "open_position": 1.0 if open_trade is not None else 0.0,
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "avg_trade_pct": sum(t.return_pct for t in trades) / len(trades) if trades else 0.0,
        "stops": sum(1 for t in trades if t.exit_reason == "stop_loss"),
        "stops_in_profit": sum(1 for t in trades if t.exit_reason == "stop_loss" and t.pnl > 0),
        "exposure_pct": sum(1 for e in exposure if e > 1e-9) / len(df) * 100,
        "avg_exposure_pct": float(np.mean(exposure)) * 100,
    }
