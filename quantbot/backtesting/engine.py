"""Ereignisgesteuerter Portfolio-Backtest für lineare Perpetuals.

Ablauf je Kerze i (Zeitstempel = Kerzenbeginn):
  1. Funding zum Kerzenbeginn (Positionen, die in die Kerze hinein gehalten werden)
  2. Ausführung der Ziele aus Kerze i-1-delay zum Eröffnungskurs (+ Slippage, Taker-Gebühr)
  3. Funding-Zeitpunkte innerhalb der Kerze (Mittelkurs)
  4. Stop / Take-Profit innerhalb der Kerze (Stop hat Vorrang, Gaps zum Eröffnungskurs)
  5. Liquidationsprüfung mit den ungünstigsten Kursen aller Positionen gleichzeitig
  6. Bewertung zum Schlusskurs, MFE/MAE offener Trades
  7. Entscheidung mit Informationen bis einschließlich Kerze i -> Ausführung frühestens i+1
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

from ..config.schema import HARD_MAX_LEVERAGE
from ..core.timeframes import tf_delta
from ..core.types import Intent
from ..data import MarketSeries
from ..portfolio.account import Account
from .costs import CostModel
from .metrics import compute_metrics


class MarketView:
    """Was ein Entscheidungsmodell zum Zeitpunkt i sehen darf (nichts aus der Zukunft)."""

    def __init__(self, engine: "BacktestEngine", i: int) -> None:
        self._e = engine
        self.i = i
        self.timestamp: pd.Timestamp = engine.index[i]
        self.account: Account = engine.account

    @property
    def prices(self) -> dict[str, float]:
        return self._e.last_close

    @property
    def equity(self) -> float:
        return self.account.equity(self._e.last_close)

    def position_qty(self, symbol: str) -> float:
        p = self.account.positions.get(symbol)
        return p.qty if p else 0.0


class DecisionModel(Protocol):
    def decide(self, view: MarketView) -> list[Intent]: ...


@dataclass
class TradeRecord:
    symbol: str
    direction: str  # long | short
    entry_time: pd.Timestamp
    entry_price: float
    qty: float  # maximale Menge während des Trades (vorzeichenlos)
    entry_equity: float
    leverage: float  # Kontohebel (Brutto-Exposure / Equity) direkt nach Einstieg
    stop: float | None
    take_profit: float | None
    meta: dict
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    exit_reason: str = ""
    gross_pnl: float = 0.0
    fees: float = 0.0
    funding: float = 0.0
    slippage_cost: float = 0.0
    mfe: float = 0.0  # größter Buchgewinn in % des Einstiegs
    mae: float = 0.0  # größter Buchverlust in % des Einstiegs (negativ)
    bars: int = 0
    _exit_notional: float = 0.0
    _exit_qty: float = 0.0

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.fees - self.funding

    @property
    def initial_risk(self) -> float | None:
        if self.stop is None:
            return None
        return abs(self.entry_price - self.stop) * self.qty

    def as_dict(self) -> dict:
        d = {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "qty": self.qty,
            "notional": self.qty * self.entry_price,
            "leverage": self.leverage,
            "stop": self.stop,
            "take_profit": self.take_profit,
            "gross_pnl": self.gross_pnl,
            "fees": self.fees,
            "funding": self.funding,
            "slippage_cost": self.slippage_cost,
            "net_pnl": self.net_pnl,
            "return_pct": self.net_pnl / self.entry_equity * 100 if self.entry_equity else 0.0,
            "r_multiple": self.net_pnl / self.initial_risk if self.initial_risk else np.nan,
            "mfe_pct": self.mfe * 100,
            "mae_pct": self.mae * 100,
            "bars": self.bars,
            "exit_reason": self.exit_reason,
        }
        for k, v in self.meta.items():
            if k not in d and not isinstance(v, (dict, list)):
                d[k] = v
        return d


@dataclass
class BacktestResult:
    equity: pd.Series
    exposure: pd.DataFrame  # je Kerze: gross, net (in Vielfachen der Equity)
    trades: pd.DataFrame
    fills: pd.DataFrame
    events: list[dict]
    metrics: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class BacktestEngine:
    def __init__(
        self,
        markets: dict[str, MarketSeries],
        costs: CostModel,
        initial_equity: float,
        mmr: dict[str, float],
        delay_bars: int = 0,
        min_notional: float = 5.0,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> None:
        if not markets:
            raise ValueError("Keine Märkte")
        tfs = {m.timeframe for m in markets.values()}
        if len(tfs) != 1:
            raise ValueError(f"Alle Märkte brauchen denselben Timeframe, gefunden: {tfs}")
        self.timeframe = tfs.pop()
        self.step = tf_delta(self.timeframe)
        self.markets = markets
        self.symbols = list(markets)
        idx = None
        for m in markets.values():
            idx = m.ohlcv.index if idx is None else idx.union(m.ohlcv.index)
        if start is not None:
            idx = idx[idx >= start]
        if end is not None:
            idx = idx[idx < end]
        if len(idx) < 2:
            raise ValueError("Zu wenige Kerzen im Zeitraum")
        self.index: pd.DatetimeIndex = idx
        self.costs = costs
        self.initial_equity = initial_equity
        self.delay = int(delay_bars)
        self.min_notional = min_notional
        self.mmr = mmr

        # Numpy-Arrays je Symbol, auf den gemeinsamen Index ausgerichtet (NaN = keine Kerze)
        self.o, self.h, self.l, self.c, self.no_trade = {}, {}, {}, {}, {}
        self.funding_events: dict[str, dict[int, list[tuple[float, bool]]]] = {}
        self.funding_fallback: dict[str, bool] = {}
        for s, m in markets.items():
            df = m.ohlcv.reindex(idx)
            self.o[s], self.h[s] = df["open"].values, df["high"].values
            self.l[s], self.c[s] = df["low"].values, df["close"].values
            # Volumen 0 = in dieser Kerze fand kein Handel statt (z. B. Börsenwartung): keine Fills
            no_trade = (df["volume"] == 0).values
            # Börsenereignis (data audit): widersprüchliche Kerzen -> dort weder Fills noch Stops
            for w_start, w_end in getattr(m, "no_trade_windows", []) or []:
                no_trade = no_trade | ((idx < w_end) & (idx + self.step > w_start))
            self.no_trade[s] = no_trade
            self.funding_events[s], self.funding_fallback[s] = self._funding_schedule(m)

    # ------------------------------------------------------------------ Funding
    def _funding_schedule(self, m: MarketSeries) -> tuple[dict[int, list[tuple[float, bool]]], bool]:
        """Je Kerzenindex: Liste (Rate, am_Kerzenbeginn)."""
        start, end = self.index[0], self.index[-1] + self.step
        fallback = m.funding is None or m.funding.empty
        if fallback:
            times = pd.date_range(start.ceil("8h"), end, freq="8h", inclusive="left")
            rates = pd.Series(self.costs.funding_fallback_rate, index=times)
        else:
            f = m.funding["rate"]
            rates = f[(f.index >= start) & (f.index < end)]
            # Lücken in der Funding-Historie mit der Fallback-Rate schließen (konservativ)
            expected = pd.date_range(start.ceil("8h"), end, freq="8h", inclusive="left")
            have = rates.index.floor("h")
            missing = expected.difference(have)
            if len(missing):
                rates = pd.concat([rates, pd.Series(self.costs.funding_fallback_rate, index=missing)]).sort_index()
        pos = self.index.searchsorted(rates.index, side="right") - 1
        sched: dict[int, list[tuple[float, bool]]] = {}
        for p, (ts, r) in zip(pos, rates.items()):
            if p < 0:
                continue
            at_open = ts == self.index[p]
            sched.setdefault(int(p), []).append((float(r), bool(at_open)))
        return sched, fallback

    # --------------------------------------------------------------------- Lauf
    def run(self, model: DecisionModel, metadata: dict | None = None) -> BacktestResult:
        self.model = model
        self.account = Account(cash=self.initial_equity, mmr=dict(self.mmr))
        self.last_close: dict[str, float] = {}
        self.open_trades: dict[str, TradeRecord] = {}
        self.trades: list[TradeRecord] = []
        self.fills: list[dict] = []
        self.events: list[dict] = []
        pending: dict[int, list[Intent]] = {}
        n = len(self.index)
        equity = np.empty(n)
        gross = np.zeros(n)
        net = np.zeros(n)
        stopped_at = None

        for i in range(n):
            # 1. Funding am Kerzenbeginn (vor der Ausführung)
            self._funding(i, at_open=True)
            # 2. Ausführung fälliger Ziele
            carry = []
            for intent in pending.pop(i, []):
                if math.isnan(self.o[intent.symbol][i]) or self.no_trade[intent.symbol][i]:
                    carry.append(intent)  # keine Kerze / kein Handel: nächste Kerze
                    continue
                self._execute(i, intent)
            if carry:
                pending.setdefault(i + 1, []).extend(carry)
            # 3. Funding innerhalb der Kerze
            self._funding(i, at_open=False)
            # 4. Stops / Take-Profit
            for s in self.symbols:
                self._check_exits(i, s)
            # Schlusskurse aktualisieren (fehlende Kerze: letzter bekannter Kurs)
            for s in self.symbols:
                if not math.isnan(self.c[s][i]):
                    self.last_close[s] = self.c[s][i]
            # 5. Liquidation
            if self._liquidation(i):
                equity[i:] = max(self.account.cash, 0.0)
                stopped_at = i
                break
            # 6. Bewertung
            px = self.last_close
            eq = self.account.equity(px)
            equity[i] = eq
            if eq > 0:
                gross[i] = self.account.gross_exposure(px) / eq
                net[i] = self.account.net_exposure(px) / eq
            self._update_excursions(i)
            # 7. Entscheidung (nur mit Daten bis einschließlich i)
            if i < n - 1 and len(self.last_close) == len(self.symbols):
                intents = model.decide(MarketView(self, i))
                if intents:
                    pending.setdefault(i + 1 + self.delay, []).extend(intents)

        if stopped_at is None:
            self._close_all(n - 1, "end_of_data")
            equity[-1] = self.account.equity(self.last_close)
        eq_s = pd.Series(equity, index=self.index, name="equity")
        exposure = pd.DataFrame({"gross": gross, "net": net}, index=self.index)
        trades = pd.DataFrame([t.as_dict() for t in self.trades])
        fills = pd.DataFrame(self.fills)
        result = BacktestResult(eq_s, exposure, trades, fills, self.events)
        result.metrics = compute_metrics(eq_s, trades, exposure, self.timeframe, self.initial_equity, fills)
        result.metrics["liquidations"] = sum(1 for e in self.events if e["type"] == "liquidation")
        result.metrics["funding_fallback_symbols"] = [s for s, f in self.funding_fallback.items() if f]
        result.metadata = dict(metadata or {})
        return result

    # ----------------------------------------------------------- Bausteine
    def _funding(self, i: int, at_open: bool) -> None:
        for s in self.symbols:
            for rate, is_open in self.funding_events[s].get(i, []):
                if is_open != at_open:
                    continue
                if at_open:
                    price = self.o[s][i]
                else:
                    price = (self.o[s][i] + self.c[s][i]) / 2
                if math.isnan(price):
                    price = self.last_close.get(s, float("nan"))
                if math.isnan(price):
                    continue
                paid = self.account.apply_funding(s, rate, price)
                if paid and s in self.open_trades:
                    self.open_trades[s].funding += paid

    def _fill(self, i: int, s: str, qty: float, price: float, reason: str, ref: float, maker: bool = False,
              meta: dict | None = None, stop=None, take_profit=None) -> None:
        """Ausführung buchen und Trade-Datensätze pflegen."""
        fee = self.costs.fee(qty * price, maker)
        res = self.account.apply_fill(s, qty, price, fee)
        slip_cost = abs(price - ref) * abs(qty)
        self.fills.append({
            "time": self.index[i], "symbol": s, "qty": qty, "price": price, "fee": fee,
            "reason": reason, "slippage_cost": slip_cost,
        })
        trade = self.open_trades.get(s)
        close_part = res.closed_qty
        if trade is not None and close_part:
            trade.gross_pnl += res.realized_pnl
            trade.fees += fee * (close_part / abs(qty))
            trade.slippage_cost += slip_cost * (close_part / abs(qty))
            trade._exit_notional += close_part * price
            trade._exit_qty += close_part
            if self.account.position(s).qty == 0 or res.flipped:
                trade.exit_time = self.index[i]
                trade.exit_price = trade._exit_notional / trade._exit_qty
                trade.exit_reason = reason
                self.trades.append(trade)
                del self.open_trades[s]
                hook = getattr(self.model, "on_trade_closed", None)
                if hook is not None:
                    hook(trade, i)
        opened = res.opened_qty
        if opened:
            open_fee = fee * (opened / abs(qty))
            open_slip = slip_cost * (opened / abs(qty))
            pos = self.account.position(s)
            if s not in self.open_trades:
                eq = self.account.equity({**self.last_close, s: price})
                gross = self.account.gross_exposure({**self.last_close, s: price})
                self.open_trades[s] = TradeRecord(
                    symbol=s,
                    direction="long" if pos.qty > 0 else "short",
                    entry_time=self.index[i],
                    entry_price=pos.avg_price,
                    qty=abs(pos.qty),
                    entry_equity=eq,
                    leverage=gross / eq if eq > 0 else float("inf"),
                    stop=stop,
                    take_profit=take_profit,
                    meta=dict(meta or {}),
                    fees=open_fee,
                    slippage_cost=open_slip,
                )
            else:
                t = self.open_trades[s]
                t.fees += open_fee
                t.slippage_cost += open_slip
                t.entry_price = pos.avg_price
                t.qty = max(t.qty, abs(pos.qty))

    def _execute(self, i: int, intent: Intent) -> None:
        s = intent.symbol
        pos = self.account.position(s)
        open_px = self.o[s][i]
        intent.target_qty = float(intent.target_qty)
        delta = intent.target_qty - pos.qty
        if abs(delta) * open_px < self.min_notional and intent.target_qty != 0:
            self._update_protection(pos, intent)
            return
        if delta == 0:
            self._update_protection(pos, intent)
            return
        # Harte technische Hebelgrenze (Schutz gegen Fehler in der Risk Engine)
        prices = {**self.last_close, s: open_px}
        eq = self.account.equity(prices)
        new_gross = self.account.gross_exposure(prices) - pos.notional(open_px) + abs(intent.target_qty) * open_px
        if eq <= 0:
            return
        if new_gross > HARD_MAX_LEVERAGE * eq and abs(intent.target_qty) > abs(pos.qty):
            allowed = max(HARD_MAX_LEVERAGE * eq - (new_gross - abs(intent.target_qty) * open_px), 0.0)
            capped = math.copysign(allowed / open_px, intent.target_qty)
            self.events.append({"type": "hard_leverage_cap", "time": self.index[i], "symbol": s,
                                "requested": intent.target_qty, "capped": capped})
            delta = capped - pos.qty
            if abs(delta) * open_px < self.min_notional:
                return
        side = 1 if delta > 0 else -1
        price = self.costs.fill_price(open_px, side, self.h[s][i], self.l[s][i])
        self._fill(i, s, delta, price, intent.reason, open_px, meta=intent.meta,
                   stop=intent.stop_price, take_profit=intent.take_profit)
        self._update_protection(self.account.position(s), intent)

    @staticmethod
    def _update_protection(pos, intent: Intent) -> None:
        if not pos.qty:
            return
        if intent.stop_price is not None:
            pos.stop_price = intent.stop_price
        if intent.take_profit is not None:
            pos.take_profit = intent.take_profit

    def _check_exits(self, i: int, s: str) -> None:
        pos = self.account.positions.get(s)
        if not pos or not pos.qty or math.isnan(self.o[s][i]) or self.no_trade[s][i]:
            return
        o, h, l = self.o[s][i], self.h[s][i], self.l[s][i]
        side = pos.side
        stop, tp = pos.stop_price, pos.take_profit
        if stop is not None and ((side > 0 and l <= stop) or (side < 0 and h >= stop)):
            ref = min(o, stop) if side > 0 else max(o, stop)  # Gap: Ausführung zum Eröffnungskurs
            price = self.costs.fill_price(ref, -side, h, l)
            self._fill(i, s, -pos.qty, price, "stop_loss", ref)
            return
        if tp is not None and ((side > 0 and h >= tp) or (side < 0 and l <= tp)):
            price = max(o, tp) if side > 0 else min(o, tp)  # Limit: kein Slippage, Maker-Gebühr
            self._fill(i, s, -pos.qty, price, "take_profit", price, maker=True)

    def _liquidation(self, i: int) -> bool:
        worst = dict(self.last_close)
        for s in self.account.open_symbols():
            if math.isnan(self.o[s][i]):
                continue
            worst[s] = self.l[s][i] if self.account.positions[s].qty > 0 else self.h[s][i]
        if not self.account.liquidation_check(worst):
            return False
        notional = self.account.gross_exposure(worst)
        for s in list(self.account.open_symbols()):
            qty = -self.account.positions[s].qty
            self._fill(i, s, qty, worst[s], "liquidation", worst[s])
        liq_fee = notional * self.costs.liquidation_fee
        self.account.cash -= liq_fee
        self.account.fees_paid += liq_fee
        self.account.liquidated = True
        self.events.append({"type": "liquidation", "time": self.index[i], "notional": notional,
                            "equity_after": self.account.cash})
        return True

    def _update_excursions(self, i: int) -> None:
        for s, t in self.open_trades.items():
            if math.isnan(self.h[s][i]):
                continue
            t.bars += 1
            if t.direction == "long":
                fav, adv = self.h[s][i] / t.entry_price - 1, self.l[s][i] / t.entry_price - 1
            else:
                fav, adv = 1 - self.l[s][i] / t.entry_price, 1 - self.h[s][i] / t.entry_price
            t.mfe = max(t.mfe, fav)
            t.mae = min(t.mae, adv)

    def _close_all(self, i: int, reason: str) -> None:
        for s in list(self.account.open_symbols()):
            pos = self.account.positions[s]
            px = self.last_close[s]
            side = -pos.side
            price = self.costs.fill_price(px, side, px, px)
            self._fill(i, s, -pos.qty, price, reason, px)
