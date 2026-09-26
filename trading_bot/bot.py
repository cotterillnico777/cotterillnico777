"""Die Bot-Schleife für Paper- und Live-Betrieb."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .broker import Broker, Fill
from .config import Config
from .data import candles_to_frame
from .indicators import atr
from .risk import RiskManager, entry_order_value, stop_price, trail_stop
from .strategies import Strategy

log = logging.getLogger(__name__)


@dataclass
class Position:
    amount: float
    entry_price: float
    cost: float  # insgesamt ausgegebene Quote-Währung inkl. Gebühr
    entry_time: str
    stop: float | None = None
    # Höchster Kurs seit Einstieg (für den Trailing-Stop)
    highest: float = 0.0


@dataclass
class BotState:
    position: Position | None = None
    wait_for_reset: bool = False
    last_candle: str | None = None
    day: str = ""
    realized_pnl_today: float = 0.0
    realized_pnl_total: float = 0.0
    paper: dict = field(default_factory=dict)
    trades: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "BotState":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        pos = data.pop("position", None)
        state = cls(**data)
        state.position = Position(**pos) if pos else None
        return state

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(path)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TradingBot:
    def __init__(
        self,
        cfg: Config,
        strategy: Strategy,
        exchange,
        broker: Broker,
        state_path: str | Path | None = None,
        clock=utc_now,
    ) -> None:
        self.cfg = cfg
        self.strategy = strategy
        self.ex = exchange
        self.broker = broker
        self.risk = RiskManager(cfg.risk, cfg.runtime.kill_switch_file)
        self.state_path = Path(state_path or cfg.runtime.state_file)
        self.state = BotState.load(self.state_path)
        self.clock = clock
        self.tf_ms = exchange.parse_timeframe(cfg.timeframe) * 1000

    # ------------------------------------------------------------------ data
    def closed_candles(self) -> pd.DataFrame:
        limit = max(self.strategy.warmup * 3, 200)
        rows = self.ex.fetch_ohlcv(self.cfg.symbol, self.cfg.timeframe, limit=limit)
        now_ms = self.clock().timestamp() * 1000
        # Die aktuell noch laufende Kerze verwerfen
        rows = [r for r in rows if r[0] + self.tf_ms <= now_ms]
        return candles_to_frame(rows)

    def last_price(self) -> float:
        ticker = self.ex.fetch_ticker(self.cfg.symbol)
        price = ticker.get("last") or ticker.get("close")
        if not price:
            raise RuntimeError("Kein aktueller Preis verfügbar")
        return float(price)

    # --------------------------------------------------------------- actions
    def _roll_day(self) -> None:
        today = self.clock().strftime("%Y-%m-%d")
        if self.state.day != today:
            self.state.day = today
            self.state.realized_pnl_today = 0.0

    def _record(self, fill: Fill, reason: str, pnl: float | None = None) -> None:
        entry = {
            "time": self.clock().isoformat(),
            "reason": reason,
            **fill.to_dict(),
        }
        if pnl is not None:
            entry["pnl"] = pnl
        self.state.trades.append(entry)
        self.state.trades = self.state.trades[-500:]

    def _buy(self, price: float, atr_value: float | None = None) -> None:
        _, quote_free = self.broker.balances()
        value = entry_order_value(quote_free, self.cfg.risk, price, atr_value)
        decision = self.risk.check_entry(value, self.state.realized_pnl_today)
        if not decision.allowed:
            log.warning("Kauf blockiert: %s", decision.reason)
            return
        fill = self.broker.market_buy(value, price)
        self.state.position = Position(
            amount=fill.amount,
            entry_price=fill.price,
            cost=-fill.quote_delta,
            entry_time=self.clock().isoformat(),
            stop=stop_price(fill.price, self.cfg.risk, atr_value),
            highest=fill.price,
        )
        self._record(fill, "entry")
        log.info(
            "KAUF %.8f %s @ %.4f für %.2f (Stop %s)",
            fill.amount,
            self.cfg.symbol,
            fill.price,
            -fill.quote_delta,
            f"{self.state.position.stop:.4f}" if self.state.position.stop else "aus",
        )

    def _sell(self, price: float, reason: str) -> None:
        pos = self.state.position
        assert pos is not None
        fill = self.broker.market_sell(pos.amount, price)
        pnl = fill.quote_delta - pos.cost * (fill.amount / pos.amount)
        remaining = pos.amount - fill.amount
        self.state.realized_pnl_today += pnl
        self.state.realized_pnl_total += pnl
        self._record(fill, reason, pnl)
        # Reste unter der Börsen-Mindestmenge gelten als geschlossen
        if remaining * price < max(self.cfg.risk.min_order_value, 1e-9):
            self.state.position = None
        else:
            pos.cost *= remaining / pos.amount
            pos.amount = remaining
        log.info(
            "VERKAUF (%s) %.8f @ %.4f, PnL %+.2f (heute %+.2f)",
            reason,
            fill.amount,
            fill.price,
            pnl,
            self.state.realized_pnl_today,
        )

    def reconcile(self) -> None:
        """Gespeicherte Position mit dem echten Kontostand abgleichen.

        Der Bot verkauft nur, was er selbst gekauft hat. Bestände, die schon
        vorher auf dem Konto lagen, werden nie angefasst.
        """
        pos = self.state.position
        if pos is None:
            return
        base_free, _ = self.broker.balances()
        if base_free < pos.amount * 0.999:
            log.warning(
                "Gespeicherte Position %.8f, aber nur %.8f frei. Position wird angepasst.",
                pos.amount,
                base_free,
            )
            if base_free <= 0:
                self.state.position = None
            else:
                pos.cost *= base_free / pos.amount
                pos.amount = base_free

    def _trail(self, candles: pd.DataFrame, atr_value: float | None) -> None:
        """Trailing-Stop mit dem Hoch der gerade abgeschlossenen Kerze nachziehen.

        Wie im Backtest einmal pro Kerze, damit sich Live und Backtest gleich verhalten.
        """
        pos = self.state.position
        if pos is None or not self.cfg.risk.trailing_stop or pos.stop is None:
            return
        pos.highest = max(pos.highest or pos.entry_price, float(candles["high"].iloc[-1]))
        new_stop = trail_stop(pos.stop, pos.highest, self.cfg.risk, atr_value)
        if new_stop is not None and new_stop > pos.stop:
            log.info("Trailing-Stop %.4f -> %.4f (Hoch %.4f)", pos.stop, new_stop, pos.highest)
            pos.stop = new_stop

    # ------------------------------------------------------------------ loop
    def tick(self) -> None:
        """Ein Durchlauf: Stop-Loss prüfen, bei neuer Kerze Signal auswerten."""
        self._roll_day()
        price = self.last_price()
        pos = self.state.position

        if pos is not None and pos.stop is not None and price <= pos.stop:
            log.warning("Stop-Loss ausgelöst: Preis %.4f <= Stop %.4f", price, pos.stop)
            self._sell(price, "stop_loss")
            self.state.wait_for_reset = True

        candles = self.closed_candles()
        if len(candles) < self.strategy.warmup:
            log.warning("Zu wenige Kerzen (%d) für Warmup %d", len(candles), self.strategy.warmup)
            return
        last_ts = str(candles.index[-1])
        if last_ts == self.state.last_candle:
            return
        self.state.last_candle = last_ts

        atr_value = (
            float(atr(candles, self.cfg.risk.atr_period).iloc[-1])
            if self.cfg.risk.needs_atr
            else None
        )
        self._trail(candles, atr_value)

        signal = int(self.strategy.generate_signals(candles).iloc[-1])
        log.info("Neue Kerze %s, Schluss %.4f, Signal %d", last_ts, candles["close"].iloc[-1], signal)

        if signal == 0:
            self.state.wait_for_reset = False
            if self.state.position is not None:
                self._sell(price, "signal")
        elif self.state.position is None:
            if self.state.wait_for_reset:
                log.info("Warte nach Stop-Loss auf neues Einstiegssignal")
            else:
                self._buy(price, atr_value)

    def save(self) -> None:
        self.state.paper = self.broker.state()
        self.state.save(self.state_path)

    def run(self, max_ticks: int | None = None) -> None:
        log.info(
            "Starte Bot: %s %s %s, Strategie %s, Modus %s",
            self.cfg.exchange.id,
            self.cfg.symbol,
            self.cfg.timeframe,
            self.strategy,
            self.cfg.runtime.mode.upper(),
        )
        ticks = 0
        errors = 0
        while max_ticks is None or ticks < max_ticks:
            try:
                self.tick()
                errors = 0
            except KeyboardInterrupt:
                raise
            except Exception:  # noqa: BLE001
                errors += 1
                log.exception("Fehler im Durchlauf (%d in Folge)", errors)
                if errors >= 10:
                    log.error("Zu viele Fehler in Folge, Bot wird beendet")
                    self.save()
                    raise
            finally:
                self.save()
            ticks += 1
            if max_ticks is None or ticks < max_ticks:
                time.sleep(self.cfg.runtime.poll_seconds * min(2**errors, 16))
