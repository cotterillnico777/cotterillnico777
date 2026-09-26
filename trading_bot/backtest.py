"""Backtest einer Strategie auf historischen Kerzen.

Ablauf pro Kerze t:
  1. Offene Position: Stop-Loss prüfen (Tief der Kerze t).
  2. Signal aus Kerze t-1 wird zum Eröffnungskurs von Kerze t ausgeführt.
So fließen keine zukünftigen Daten in eine Entscheidung ein.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from .config import BacktestConfig, RiskConfig
from .risk import entry_order_value, stop_price
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
            f"Stop-Loss ausgelöst:  {int(m['stops'])}",
            f"Zeit im Markt:        {m['exposure_pct']:.1f} %",
        ]
        return "\n".join(lines)


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    risk: RiskConfig,
    bt: BacktestConfig,
    timeframe: str,
    signals: pd.Series | None = None,
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
    signals = signals.reindex(df.index).fillna(0).astype(int)

    cash = bt.initial_balance
    amount = 0.0
    open_trade: Trade | None = None
    stop: float | None = None
    # Nach einem Stop-Loss erst wieder einsteigen, wenn das Signal zwischendurch flat war
    wait_for_reset = False
    trades: list[Trade] = []
    equity = []
    in_market = 0

    opens, lows, closes = df["open"].values, df["low"].values, df["close"].values
    sig = signals.values
    for i, ts in enumerate(df.index):
        # 1. Stop-Loss innerhalb der Kerze
        if open_trade is not None and stop is not None and lows[i] <= stop:
            price = min(opens[i], stop) * (1 - bt.slippage)
            proceeds = amount * price * (1 - bt.fee)
            cash += proceeds
            open_trade.exit_time, open_trade.exit_price = ts, price
            open_trade.proceeds, open_trade.exit_reason = proceeds, "stop_loss"
            trades.append(open_trade)
            open_trade, amount, stop, wait_for_reset = None, 0.0, None, True

        # 2. Signal der vorherigen Kerze zum Open ausführen
        if i > 0:
            target = sig[i - 1]
            if target == 0:
                wait_for_reset = False
            if target == 1 and open_trade is None and not wait_for_reset:
                value = entry_order_value(cash, risk)
                if value > 0:
                    price = opens[i] * (1 + bt.slippage)
                    amount = value * (1 - bt.fee) / price
                    cash -= value
                    open_trade = Trade(ts, price, amount, value)
                    stop = stop_price(price, risk)
            elif target == 0 and open_trade is not None:
                price = opens[i] * (1 - bt.slippage)
                proceeds = amount * price * (1 - bt.fee)
                cash += proceeds
                open_trade.exit_time, open_trade.exit_price = ts, price
                open_trade.proceeds, open_trade.exit_reason = proceeds, "signal"
                trades.append(open_trade)
                open_trade, amount, stop = None, 0.0, None

        if open_trade is not None:
            in_market += 1
        equity.append(cash + amount * closes[i])

    equity_s = pd.Series(equity, index=df.index, name="equity")
    return BacktestResult(
        equity=equity_s,
        trades=trades,
        metrics=_metrics(df, equity_s, trades, bt, timeframe, in_market, open_trade),
    )


def _metrics(df, equity, trades, bt, timeframe, in_market, open_trade) -> dict:
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
        "exposure_pct": in_market / len(df) * 100,
    }
