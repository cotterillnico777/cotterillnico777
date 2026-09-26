"""Execution Engine: setzt Zielpositionen sicher und idempotent in Orders um."""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import dataclass

from ..core.types import Intent, Order, OrderStatus, OrderType, Side
from ..exchanges.base import ExchangeAdapter, ExchangeError, ExchangeUnavailable
from ..monitoring.journal import Journal, now

log = logging.getLogger(__name__)


class ExecutionHalted(RuntimeError):
    """Zu viele Fehlschläge: keine weiteren Orders (Kill Switch)."""


@dataclass
class ExecConfig:
    max_failures: int = 3  # aufeinanderfolgende fehlgeschlagene Orders -> Halt
    retries: int = 3  # Wiederholungen bei Timeout/Netzwerk
    retry_delay: float = 2.0
    min_notional: float = 10.0
    poll_attempts: int = 5  # Statusabfragen bis zum Endzustand


def client_id(run_tag: str, symbol: str, bar_key: str, purpose: str) -> str:
    """Deterministische ID (max. 36 Zeichen, Binance-kompatibel).

    Gleiche Entscheidung (Lauf, Symbol, Kerze, Zweck) -> gleiche ID -> die Börse lehnt Duplikate ab
    bzw. wir finden die bestehende Order wieder. Das verhindert Doppel-Orders nach Neustarts.
    """
    h = hashlib.sha1(f"{run_tag}|{symbol}|{bar_key}|{purpose}".encode()).hexdigest()[:24]
    return f"qb{purpose[:6]}{h}"[:36]


class ExecutionEngine:
    def __init__(self, adapter: ExchangeAdapter, journal: Journal, run_tag: str,
                 cfg: ExecConfig | None = None, sleep=time.sleep) -> None:
        self.ex = adapter
        self.journal = journal
        self.run_tag = run_tag
        self.cfg = cfg or ExecConfig()
        self.sleep = sleep
        self.consecutive_failures = 0

    # --------------------------------------------------------------- Senden
    def submit(self, order: Order) -> Order:
        """Order sicher senden. Nie doppelt: vor jedem (Neu-)Versuch den Status per client_id prüfen."""
        if self.consecutive_failures >= self.cfg.max_failures:
            raise ExecutionHalted(f"{self.consecutive_failures} fehlgeschlagene Orders in Folge")
        known = self._lookup(order)
        if known is not None:
            log.info("Order %s existiert bereits (%s), nicht erneut gesendet", order.client_id, known.status.value)
            return self._finish(known)
        order.created_at = order.created_at or now()
        order.status = OrderStatus.SUBMITTED
        self.journal.order(order)
        for attempt in range(self.cfg.retries + 1):
            try:
                result = self.ex.place_order(order)
                return self._finish(result)
            except ExchangeUnavailable as exc:
                order.status, order.error = OrderStatus.UNKNOWN, str(exc)
                self.journal.order(order)
                self.journal.event("WARNING", "order_timeout", f"{order.client_id}: {exc}")
                self.sleep(self.cfg.retry_delay * 2**attempt)
                known = self._lookup(order)
                if known is not None:  # kam trotz Timeout an
                    return self._finish(known)
            except ExchangeError as exc:
                order.status, order.error = OrderStatus.REJECTED, str(exc)
                self.journal.order(order)
                self.journal.event("ERROR", "order_rejected", f"{order.client_id}: {exc}")
                self.consecutive_failures += 1
                return order
        order.status = OrderStatus.REJECTED
        order.error = "keine Bestätigung nach Wiederholungen"
        self.journal.order(order)
        self.journal.event("ERROR", "order_failed", f"{order.client_id}: {order.error}")
        self.consecutive_failures += 1
        return order

    def _lookup(self, order: Order) -> Order | None:
        try:
            return self.ex.get_order(order.symbol, order.client_id)
        except ExchangeUnavailable:
            return None

    def _finish(self, o: Order) -> Order:
        for _ in range(self.cfg.poll_attempts):
            if o.status.is_final or o.type is not OrderType.MARKET:
                break
            self.sleep(self.cfg.retry_delay)
            again = self._lookup(o)
            if again is not None:
                o = again
        if o.status in (OrderStatus.FILLED, OrderStatus.OPEN) or o.filled_qty > 0:
            self.consecutive_failures = 0
        self._persist(o)
        return o

    def _persist(self, o: Order) -> None:
        """Order speichern und neu ausgeführte Menge als Fill verbuchen (einmalig)."""
        row = self.journal.get_order_row(o.client_id)
        before = float(row["filled_qty"] or 0.0) if row is not None else 0.0
        fee_before = float(row["fee"] or 0.0) if row is not None else 0.0
        new_qty = o.filled_qty - before
        if new_qty > 1e-12 and o.avg_price:
            # Preis des neuen Teils aus dem Durchschnitt zurückrechnen
            prev_avg = float(row["avg_price"] or 0.0) if row is not None else 0.0
            px = (o.avg_price * o.filled_qty - prev_avg * before) / new_qty if before else o.avg_price
            self.journal.fill(o.client_id, o.symbol, o.side.value, new_qty, px, max(o.fee - fee_before, 0.0))
        self.journal.order(o)

    # ------------------------------------------------------------ Umsetzung
    def rebalance(self, intents: list[Intent], bar_key: str, positions: dict[str, float],
                  prices: dict[str, float]) -> list[Order]:
        """Ziele umsetzen. Teilausführungen werden im nächsten Zyklus über den Abgleich nachgeholt."""
        done = []
        for it in intents:
            cur = positions.get(it.symbol, 0.0)
            px = prices[it.symbol]
            tgt = float(it.target_qty)
            old_stop, old_tp = self.protection_prices(it.symbol)
            if abs(tgt - cur) * px >= self.cfg.min_notional or (tgt == 0 and cur != 0):
                done += self._move(it.symbol, cur, tgt, bar_key, it.reason)
            new_qty = self._position(it.symbol, default=tgt)
            same_side = cur != 0 and new_qty != 0 and (cur > 0) == (new_qty > 0)
            stop = it.stop_price if it.stop_price is not None else (old_stop if same_side else None)
            tp = it.take_profit if it.take_profit is not None else (old_tp if same_side else None)
            changed = new_qty != cur or stop != old_stop or tp != old_tp
            if changed:
                done += self.protect(it.symbol, new_qty, stop, tp, bar_key)
        return done

    def sync_orders(self) -> list[Order]:
        """Status aller eigenen offenen Orders von der Börse holen (z. B. ausgelöste Stops)."""
        updated = []
        for row in self.journal.query("SELECT client_id, symbol FROM orders WHERE status IN (?,?,?,?)",
                                      (OrderStatus.OPEN.value, OrderStatus.SUBMITTED.value,
                                       OrderStatus.UNKNOWN.value, OrderStatus.PARTIALLY_FILLED.value)):
            o = self._lookup_by(row["symbol"], row["client_id"])
            if o is not None:
                self._persist(o)
                updated.append(o)
        return updated

    def _lookup_by(self, symbol: str, cid: str) -> Order | None:
        try:
            return self.ex.get_order(symbol, cid)
        except ExchangeUnavailable:
            return None

    def _move(self, symbol: str, cur: float, tgt: float, bar_key: str, reason: str) -> list[Order]:
        out = []
        if cur and (tgt == 0 or (cur > 0) != (tgt > 0)):
            # Erst schließen (reduce_only), dann ggf. Gegenrichtung eröffnen
            side = Side.SELL if cur > 0 else Side.BUY
            out.append(self.submit(Order(client_id(self.run_tag, symbol, bar_key, "close"), symbol, side,
                                         OrderType.MARKET, abs(cur), reduce_only=True, reason=reason or "exit")))
            cur = 0.0
        delta = tgt - cur
        if abs(delta) > 1e-12:
            reducing = cur != 0 and abs(tgt) < abs(cur)
            side = Side.BUY if delta > 0 else Side.SELL
            purpose = "reduce" if reducing else ("open" if cur == 0 else "add")
            out.append(self.submit(Order(client_id(self.run_tag, symbol, bar_key, purpose), symbol, side,
                                         OrderType.MARKET, abs(delta), reduce_only=reducing, reason=reason)))
        return out

    def _position(self, symbol: str, default: float) -> float:
        try:
            for p in self.ex.get_positions():
                if p.symbol == symbol:
                    return p.qty
            return 0.0
        except ExchangeUnavailable:
            return default

    def protect(self, symbol: str, qty: float, stop: float | None, tp: float | None, bar_key: str) -> list[Order]:
        """Schutz-Orders bei der Börse: alte eigene Stops/TPs löschen, neue reduce-only setzen."""
        key = f"protect:{symbol}"
        old = self.journal.get(key, {})
        for kind, cid in list(old.items()):
            try:
                self.ex.cancel_order(symbol, cid)
            except (ExchangeError, ExchangeUnavailable) as exc:
                log.warning("Schutz-Order %s nicht storniert: %s", cid, exc)
            old.pop(kind, None)
        out = []
        seq = int(self.journal.get(f"protect_seq:{symbol}", 0)) + 1
        self.journal.set(f"protect_seq:{symbol}", seq)
        pkey = f"{bar_key}#{seq}"
        if qty:
            exit_side = Side.SELL if qty > 0 else Side.BUY
            if stop is not None and math.isfinite(stop) and stop > 0:
                o = self.submit(Order(client_id(self.run_tag, symbol, pkey, "stop"), symbol, exit_side,
                                      OrderType.STOP_MARKET, abs(qty), stop_price=stop, reduce_only=True,
                                      reason="stop_loss"))
                if o.status is not OrderStatus.REJECTED:
                    old["stop"] = o.client_id
                out.append(o)
            if tp is not None and math.isfinite(tp) and tp > 0:
                o = self.submit(Order(client_id(self.run_tag, symbol, pkey, "tp"), symbol, exit_side,
                                      OrderType.TAKE_PROFIT_MARKET, abs(qty), stop_price=tp, reduce_only=True,
                                      reason="take_profit"))
                if o.status is not OrderStatus.REJECTED:
                    old["tp"] = o.client_id
                out.append(o)
        self.journal.set(key, old)
        return out

    def protection_prices(self, symbol: str) -> tuple[float | None, float | None]:
        ids = self.journal.get(f"protect:{symbol}", {})
        stop = tp = None
        for kind, cid in ids.items():
            row = self.journal.get_order_row(cid)
            if row is not None and row["status"] in (OrderStatus.OPEN.value, OrderStatus.SUBMITTED.value):
                if kind == "stop":
                    stop = row["stop_price"]
                else:
                    tp = row["stop_price"]
        return stop, tp
