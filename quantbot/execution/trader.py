"""Handelsschleife für PAPER und LIVE. Gleiche Strategie-, Risk- und Execution-Engine für beide.

Je Zyklus:
  1. Kerzen + Funding laden (nur abgeschlossene Kerzen), Datenqualität prüfen
  2. PAPER: simulierte Börse verarbeitet Stops/Funding/Liquidation der neuen Kerzen
  3. Order-Status mit der Börse abgleichen (ausgelöste Stops)
  4. Bei neuer Kerze: Signale -> Risk Engine -> Execution Engine
  5. Journal: Signale, Equity, Positionen, Trades (MFE/MAE), Heartbeat
Kill Switch bei Datenfehlern, wiederholten Order-/API-Fehlern, inkonsistenten Positionen und
den Limits der Risk Engine. Nach dem Kill Switch werden nur noch Positionen geschlossen.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import __version__
from ..backtesting.metadata import git_commit
from ..config.schema import Config
from ..core.timeframes import tf_seconds
from ..core.types import Intent, Mode
from ..data import MarketSeries, frame_hash, validate_ohlcv
from ..data.download import download_funding, download_ohlcv
from ..exchanges.base import ExchangeAdapter, ExchangeUnavailable
from ..exchanges.simulated import SimulatedExchange
from ..monitoring.journal import Journal
from ..portfolio.account import Account, Position
from ..portfolio.allocator import StrategyPortfolio
from ..portfolio.correlation import RiskStats
from ..risk.engine import RiskEngine, RiskState
from ..strategies import create
from .engine import ExecConfig, ExecutionEngine, ExecutionHalted
from .ledger import TradeLedger

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Trader:
    def __init__(self, cfg: Config, mode: Mode, exchange: ExchangeAdapter, journal: Journal,
                 clock=utc_now, sleep=time.sleep) -> None:
        if mode is Mode.BACKTEST:
            raise ValueError("Trader ist für PAPER/LIVE; Backtests laufen über 'quantbot backtest'")
        if not cfg.strategies:
            raise ValueError("Keine Strategien konfiguriert (strategies: ...)")
        tfs = {s.timeframe for s in cfg.strategies}
        if len(tfs) != 1:
            raise ValueError(f"Alle Strategien brauchen denselben Timeframe, gefunden: {tfs}")
        self.cfg, self.mode, self.ex, self.journal = cfg, mode, exchange, journal
        self.clock, self.sleep = clock, sleep
        self.tf = tfs.pop()
        self.step = pd.Timedelta(seconds=tf_seconds(self.tf))
        syms = sorted({s for slot in cfg.strategies for s in slot.symbols}) or [i.symbol for i in cfg.instruments]
        self.symbols = syms
        self.mmr = {i.symbol: i.maintenance_margin_rate for i in cfg.instruments}
        self.risk = RiskEngine(cfg.risk, cfg.costs, self.mmr, None, cfg.runtime.kill_switch_file)
        saved = journal.get("risk_state")
        if saved:
            self.risk.state = RiskState(**saved)
        tag_src = json.dumps([mode.value, [dataclasses.asdict(s) for s in cfg.strategies]], sort_keys=True)
        self.run_tag = hashlib.sha1(tag_src.encode()).hexdigest()[:8]
        self.exec = ExecutionEngine(exchange, journal, self.run_tag,
                                    ExecConfig(max_failures=cfg.runtime.max_order_failures,
                                               min_notional=cfg.risk.min_trade_notional), sleep=sleep,
                                    clock=clock)
        warm = max(create(s.name, s.params).warmup for s in cfg.strategies) * 3
        bars_per_day = 86400 / tf_seconds(self.tf)
        regime_days = cfg.regime.trend_ma_days + cfg.regime.slope_days + cfg.regime.vol_rank_days // 4
        self.history_bars = int(min(max(warm, (regime_days + 5) * bars_per_day,
                                        cfg.risk.correlation_lookback_days * bars_per_day), 20_000))
        self.errors = 0
        self.data_errors = 0
        self.ledger = TradeLedger(journal)
        if isinstance(exchange, SimulatedExchange) and journal.get("paper_exchange"):
            exchange.load_state(journal.get("paper_exchange"))  # Paper-Konto nach Neustart fortsetzen
        journal.start_run(f"{mode.value}-{self.run_tag}-{int(time.time())}", mode.value, git_commit(),
                          __version__, dataclasses.asdict(cfg))
        journal.event("INFO", "start", f"{mode.value} gestartet", {"symbols": syms, "timeframe": self.tf})

    # ------------------------------------------------------------------ Daten
    def fetch(self) -> dict[str, MarketSeries]:
        since = pd.Timestamp(self.clock()) - self.step * (self.history_bars + 2)
        out = {}
        for s in self.symbols:
            df = download_ohlcv(self.ex, s, self.tf, since)
            try:
                f = download_funding(self.ex, s, since)
            except ExchangeUnavailable:
                f = None
            out[s] = MarketSeries(s, self.tf, df, f if f is not None and len(f) else None, frame_hash(df))
        return out

    def health(self, markets: dict[str, MarketSeries], prices: dict[str, float]) -> list[str]:
        problems = []
        now = pd.Timestamp(self.clock())
        for s, m in markets.items():
            df = m.ohlcv
            if df.empty:
                problems.append(f"{s}: keine Kerzen")
                continue
            age = now - (df.index[-1] + self.step)
            if age > self.step * self.cfg.runtime.max_data_age_bars:
                problems.append(f"{s}: letzte Kerze veraltet ({age})")
            rep = validate_ohlcv(df.iloc[-500:], self.tf)
            if not rep.ok:
                problems.append(f"{s}: {'; '.join(rep.errors)}")
            p = prices.get(s)
            if p is None or not math.isfinite(p) or p <= 0:
                problems.append(f"{s}: kein gültiger Preis")
            elif abs(p / df["close"].iloc[-1] - 1) > self.cfg.runtime.max_price_deviation:
                problems.append(f"{s}: Preis {p} weicht stark von Kerze {df['close'].iloc[-1]} ab")
        return problems

    # ---------------------------------------------------------------- Konto
    def account_snapshot(self, prices: dict[str, float]) -> Account:
        bal = self.ex.get_balance()
        positions = self.ex.get_positions()
        unreal = sum(p.qty * (prices.get(p.symbol, p.entry_price) - p.entry_price) for p in positions)
        acc = Account(cash=bal.equity - unreal, mmr=self.mmr)
        for p in positions:
            stop, tp = self.exec.protection_prices(p.symbol)
            acc.positions[p.symbol] = Position(p.symbol, p.qty, p.entry_price, stop, tp)
        return acc

    # ------------------------------------------------------------------ Paper
    def paper_step(self, markets: dict[str, MarketSeries]) -> None:
        """Simulierte Börse: Stops, Funding, Liquidation für neu abgeschlossene Kerzen."""
        if not isinstance(self.ex, SimulatedExchange):
            return
        worst = {}
        for s, m in markets.items():
            done = self.journal.get(f"paper_bar:{s}")
            new = m.ohlcv if done is None else m.ohlcv[m.ohlcv.index > pd.Timestamp(done)]
            if done is None:
                new = m.ohlcv.iloc[-1:]  # beim Start nur die letzte Kerze als Preisbasis
            for ts, row in new.iterrows():
                trig = self.ex.process_bar(s, row["high"], row["low"], row["close"])
                for o in trig:
                    self.journal.event("INFO", "stop_triggered", f"{s} {o.reason} @ {o.avg_price}")
                pos = self.ex.account.positions.get(s)
                if pos and pos.qty:
                    worst[s] = row["low"] if pos.qty > 0 else row["high"]
            if len(new):
                self.journal.set(f"paper_bar:{s}", str(new.index[-1]))
            if m.funding is not None:
                f_done = self.journal.get(f"paper_funding:{s}")
                fnew = m.funding if f_done is None else m.funding[m.funding.index > pd.Timestamp(f_done)]
                if f_done is None:
                    fnew = fnew.iloc[0:0]
                for ts, r in fnew.iterrows():
                    self.ex.apply_funding(s, float(r["rate"]), float(m.ohlcv["close"].asof(ts)))
                if len(m.funding):
                    self.journal.set(f"paper_funding:{s}", str(m.funding.index[-1]))
        if worst and self.ex.check_liquidation(worst):
            self.journal.event("CRITICAL", "liquidation", "Paper-Konto liquidiert")
            self.risk.kill("Liquidation")

    # ---------------------------------------------------------------- Trades
    def book_trades(self, markets: dict[str, MarketSeries], prices: dict[str, float]) -> list[dict]:
        acc = self.account_snapshot(prices)
        eq, gross = acc.equity(prices), acc.gross_exposure(prices)
        funding = dict(getattr(self.ex, "funding_by_symbol", {}))
        closed = self.ledger.process(str(pd.Timestamp(self.clock())), eq, gross, funding)
        for t in closed:
            self.risk.on_trade_closed(t["net_pnl"], eq, self._bar_no(pd.Timestamp(self.clock())))
            self.journal.event("INFO", "trade_closed", f"{t['symbol']} {t['direction']} {t['net_pnl']:+.2f}",
                               {"exit_reason": t["exit_reason"]})
        for s, m in markets.items():
            last = m.ohlcv.iloc[-1]
            self.ledger.update_excursions(s, float(last["high"]), float(last["low"]))
        return closed

    # ------------------------------------------------------------------ Zyklus
    def tick(self) -> str:
        try:
            markets = self.fetch()
            prices = {s: self.ex.get_ticker_price(s) for s in self.symbols}
        except ExchangeUnavailable as exc:
            return self._error("api", str(exc))
        problems = self.health(markets, prices)
        if problems:
            self.data_errors += 1
            self.journal.event("ERROR", "data", "; ".join(problems))
            if self.data_errors >= 3:
                self.risk.kill("wiederholte Datenfehler: " + problems[0])
                self._flatten(prices, "data_error")
            self.journal.heartbeat("data_error", problems[0])
            return "data_error"
        self.data_errors = 0

        self.paper_step(markets)
        self.exec.sync_orders()
        self.book_trades(markets, prices)  # z. B. ausgelöste Stops seit dem letzten Zyklus
        last_ts = min(m.ohlcv.index[-1] for m in markets.values())
        if self.journal.get("last_bar") == str(last_ts) and not self.risk.state.killed:
            self._persist_paper()
            self.journal.heartbeat("ok", f"warte auf Kerze nach {last_ts}")
            return "waiting"

        try:
            intents, equity, gross = self._decide(markets, prices, last_ts)
            if self.risk.state.killed:
                self._flatten(prices, self.risk.state.kill_reason)
            else:
                positions = {p.symbol: p.qty for p in self.ex.get_positions()}
                self.exec.rebalance(intents, str(last_ts), positions, prices)
            self.book_trades(markets, prices)
            self._snapshot(prices)
        except ExecutionHalted as exc:
            self.risk.kill(f"Execution angehalten: {exc}")
            self.journal.event("CRITICAL", "kill_switch", str(exc))
            self._flatten(prices, "execution_halted")
        except ExchangeUnavailable as exc:
            return self._error("api", str(exc))
        self.journal.set("last_bar", str(last_ts))
        self.journal.set("risk_state", dataclasses.asdict(self.risk.state))
        self._persist_paper()
        self.errors = 0
        status = "killed" if self.risk.state.killed else "ok"
        self.journal.heartbeat(status, self.risk.state.kill_reason or f"Kerze {last_ts} verarbeitet")
        return status

    def _decide(self, markets, prices, last_ts):
        idx = None
        for m in markets.values():
            idx = m.ohlcv.index if idx is None else idx.union(m.ohlcv.index)
        idx = idx[idx <= last_ts]
        self.risk.stats = RiskStats({s: m.ohlcv["close"].reindex(idx) for s, m in markets.items()}, self.tf,
                                    self.cfg.risk.correlation_lookback_days)
        portfolio = StrategyPortfolio(markets, self.cfg.strategies, self.risk, self.cfg.regime)
        portfolio.bind(idx)
        i = len(idx) - 1
        signals = portfolio.signals_at(i)
        for s, sig in signals.items():
            self.journal.signal(last_ts, s, sig.value, sig.stop_distance, sig.meta.get("regime"),
                                sig.meta.get("strategy"), sig.meta.get("features", "{}"))
        account = self.account_snapshot(prices)
        self._reconcile(account)
        intents = self.risk.targets(i, pd.Timestamp(last_ts), account, prices, signals,
                                    bar_no=self._bar_no(last_ts))
        for it in intents:
            self.ledger.set_meta(it.symbol, {**{k: v for k, v in it.meta.items()},
                                             "stop": it.stop_price, "take_profit": it.take_profit,
                                             "strategy_version": self.run_tag})
        return intents, account.equity(prices), account.gross_exposure(prices)

    def _persist_paper(self) -> None:
        if isinstance(self.ex, SimulatedExchange):
            self.journal.set("paper_exchange", self.ex.to_state())

    def _bar_no(self, ts) -> int:
        return int(pd.Timestamp(ts).value // self.step.value)

    def _reconcile(self, account: Account) -> None:
        """Positionen ohne eigenen Trade-Eintrag = fremd oder inkonsistent -> Kill Switch."""
        for s, p in account.positions.items():
            if p.qty and s not in self.symbols:
                self.risk.kill(f"Unerwartete Position in {s}")
                self.journal.event("CRITICAL", "inconsistent_position", f"{s} {p.qty}")

    def _flatten(self, prices, reason: str) -> None:
        intents = [Intent(p.symbol, 0.0, reason=reason) for p in self.ex.get_positions() if p.qty]
        if intents:
            positions = {p.symbol: p.qty for p in self.ex.get_positions()}
            key = f"flatten-{pd.Timestamp(self.clock()).floor('min')}"
            try:
                self.exec.consecutive_failures = 0
                self.exec.rebalance(intents, key, positions, prices)
            except ExecutionHalted as exc:
                self.journal.event("CRITICAL", "flatten_failed", str(exc))

    def _snapshot(self, prices) -> None:
        acc = self.account_snapshot(prices)
        eq = acc.equity(prices)
        peak = max(self.risk.state.peak_equity, eq)
        self.journal.equity(pd.Timestamp(self.clock()), eq, acc.gross_exposure(prices) / eq if eq else 0,
                            acc.net_exposure(prices) / eq if eq else 0, eq / peak - 1 if peak else 0)
        for s, p in acc.positions.items():
            if p.qty:
                self.journal.position(pd.Timestamp(self.clock()), s, p.qty, p.avg_price, p.stop_price,
                                      p.take_profit, p.unrealized(prices[s]))

    def _error(self, kind: str, msg: str) -> str:
        self.errors += 1
        self.journal.event("ERROR", kind, msg)
        self.journal.heartbeat("error", msg)
        if self.errors >= 10:
            self.risk.kill(f"{self.errors} Fehler in Folge ({kind})")
        return "error"

    def run(self, max_cycles: int | None = None) -> None:
        n = 0
        while max_cycles is None or n < max_cycles:
            status = self.tick()
            log.info("Zyklus %d: %s", n, status)
            n += 1
            if max_cycles is None or n < max_cycles:
                self.sleep(self.cfg.runtime.poll_seconds)
