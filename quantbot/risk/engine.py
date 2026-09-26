"""Zentrale Risk Engine.

Strategien liefern nur Richtung, Stärke und Stop-Abstand. Die Risk Engine entscheidet
allein über Positionsgröße und damit über den Hebel:

  1. Sperren prüfen: Kill Switch, Max-Drawdown, Tages-/Wochenverlust, Cooldown
  2. Größe je Symbol: Risiko pro Trade / Stop-Abstand (oder Volatilitätsziel)
  3. Trade-Qualität: Kosten in R, Mindestsignal, Mindest-Stopabstand
  4. Grenzen: Symbol-Exposure, Brutto-/Netto-Exposure, Kontohebel
  5. Portfolio-Volatilität über Kovarianz (korrelierte Positionen zählen gemeinsam)
  6. Liquidationsabstand: Stop muss mit Sicherheitsfaktor vor der Liquidation liegen
  7. Hysterese gegen unnötiges Nachjustieren

Schließen oder Verkleinern ist immer erlaubt, auch wenn neue Risiken gesperrt sind.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..config.schema import HARD_MAX_LEVERAGE, CostConfig, RiskConfig
from ..core.types import Intent
from ..portfolio.account import Account
from ..portfolio.correlation import RiskStats

log = logging.getLogger(__name__)


@dataclass
class Signal:
    """Ausgabe der Strategie-Schicht für ein Symbol zu einem Zeitpunkt."""

    symbol: str
    value: float  # -1..+1 (Richtung × Stärke), 0 = kein Trade
    stop_distance: float  # Preisabstand zum Stop (> 0)
    take_profit_distance: float | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class RiskState:
    peak_equity: float = 0.0
    day: str = ""
    day_start_equity: float = 0.0
    week: str = ""
    week_start_equity: float = 0.0
    consecutive_losses: int = 0
    cooldown_until: int = -1  # Kerzenindex
    killed: bool = False
    kill_reason: str = ""
    blocks: dict = field(default_factory=dict)  # Zähler: Grund -> Anzahl


class RiskEngine:
    def __init__(
        self,
        cfg: RiskConfig,
        costs: CostConfig,
        mmr: dict[str, float],
        stats: RiskStats | None = None,
        kill_switch_file: str | None = None,
    ) -> None:
        self.cfg = cfg
        self.costs = costs
        self.mmr = mmr
        self.stats = stats
        self.kill_switch_file = Path(kill_switch_file) if kill_switch_file else None
        self.state = RiskState()
        self.decisions: list[dict] = []  # Protokoll der Eingriffe (für Analyse)

    # ------------------------------------------------------------ Ereignisse
    def on_trade_closed(self, net_pnl: float, equity_before: float, i: int) -> None:
        st = self.state
        if net_pnl < 0:
            st.consecutive_losses += 1
            big = equity_before > 0 and -net_pnl / equity_before >= self.cfg.large_loss_threshold
            if st.consecutive_losses >= self.cfg.max_consecutive_losses or big:
                st.cooldown_until = max(st.cooldown_until, i + self.cfg.cooldown_bars)
                why = "großer Einzelverlust" if big else f"{st.consecutive_losses} Verluste in Folge"
                log.warning("Cooldown bis Kerze %d (%s)", st.cooldown_until, why)
                if not big:
                    st.consecutive_losses = 0
        else:
            st.consecutive_losses = 0

    def kill(self, reason: str) -> None:
        if not self.state.killed:
            log.critical("KILL SWITCH: %s", reason)
        self.state.killed = True
        self.state.kill_reason = reason

    # ---------------------------------------------------------------- Sperren
    def _update_limits(self, ts: pd.Timestamp, equity: float) -> str | None:
        """Gibt den Sperrgrund für NEUE Risiken zurück (None = frei)."""
        st, c = self.state, self.cfg
        st.peak_equity = max(st.peak_equity, equity)
        day = ts.strftime("%Y-%m-%d")
        week = f"{ts.isocalendar().year}-{ts.isocalendar().week}"
        if st.day != day:
            st.day, st.day_start_equity = day, equity
        if st.week != week:
            st.week, st.week_start_equity = week, equity
        if self.kill_switch_file is not None and self.kill_switch_file.exists():
            self.kill(f"Kill-Switch-Datei {self.kill_switch_file}")
        if st.peak_equity > 0 and equity <= st.peak_equity * (1 - c.max_drawdown_limit):
            self.kill(f"Max-Drawdown {c.max_drawdown_limit:.0%} überschritten")
        if st.killed:
            return "kill_switch"
        if equity <= st.day_start_equity * (1 - c.daily_loss_limit):
            return "daily_loss_limit"
        if equity <= st.week_start_equity * (1 - c.weekly_loss_limit):
            return "weekly_loss_limit"
        return None

    # ------------------------------------------------------------ Kernlogik
    def targets(
        self,
        i: int,
        ts: pd.Timestamp,
        account: Account,
        prices: dict[str, float],
        signals: dict[str, Signal],
        bar_no: int | None = None,
    ) -> list[Intent]:
        """``i`` = Index in den Statistiken; ``bar_no`` = fortlaufende Kerzennummer für Cooldowns
        (Live: gleitendes Datenfenster, daher absolute Nummer). Standard: bar_no = i."""
        c = self.cfg
        clock_i = i if bar_no is None else bar_no
        equity = account.equity(prices)
        if equity <= 0:
            self.kill("Kontowert <= 0")
        block = self._update_limits(ts, equity)
        if block is None and clock_i < self.state.cooldown_until:
            block = "cooldown"
        if self.state.killed:
            # Alles schließen, keine neuen Positionen mehr
            return [Intent(s, 0.0, reason="kill_switch") for s in account.open_symbols()]

        # --- 2./3. Rohgröße je Symbol
        raw: dict[str, float] = {}
        stops: dict[str, float] = {}
        for s, sig in signals.items():
            price = prices[s]
            q = self._size(i, s, sig, equity, price)
            raw[s] = q
            stops[s] = sig.stop_distance

        # --- 4./5./6. Portfolio-Grenzen (proportional skalieren)
        raw = self._portfolio_limits(i, raw, prices, equity)
        raw = self._liquidation_safety(account, raw, prices, stops)

        # --- Sperren anwenden und Intents bauen
        intents: list[Intent] = []
        for s in set(signals) | set(account.open_symbols()):
            cur = account.positions[s].qty if s in account.positions else 0.0
            tgt = raw.get(s, 0.0)
            if block is not None and not _is_reduction(cur, tgt):
                self.state.blocks[block] = self.state.blocks.get(block, 0) + 1
                tgt = _limit_to_reduction(cur, tgt)
            # Hysterese: gleiche Richtung, kleine Änderung -> nicht handeln
            if cur and tgt and (cur > 0) == (tgt > 0) and abs(tgt - cur) <= c.rebalance_threshold * abs(cur):
                tgt = cur
            sig = signals.get(s)
            price = prices[s]
            stop = tp = None
            if tgt and sig is not None:
                d = 1 if tgt > 0 else -1
                new_entry = cur == 0 or (cur > 0) != (tgt > 0)
                pos = account.positions.get(s)
                if new_entry or pos is None or pos.stop_price is None:
                    stop = price - d * sig.stop_distance
                elif c.trailing_stop:
                    cand = price - d * sig.stop_distance
                    stop = max(pos.stop_price, cand) if d > 0 else min(pos.stop_price, cand)
                if sig.take_profit_distance and new_entry:
                    tp = price + d * sig.take_profit_distance
            if tgt == cur and stop is None and tp is None:
                continue
            meta = dict(sig.meta) if sig is not None else {}
            meta.setdefault("risk_block", block or "")
            intents.append(Intent(s, tgt, stop_price=stop, take_profit=tp,
                                  reason="signal" if tgt != 0 or cur == 0 else "exit_signal", meta=meta))
        return intents

    def _size(self, i: int, s: str, sig: Signal, equity: float, price: float) -> float:
        c = self.cfg
        v = max(min(sig.value, 1.0), -1.0)
        if abs(v) < c.min_signal or not math.isfinite(sig.stop_distance) or sig.stop_distance <= 0:
            return 0.0
        if sig.stop_distance < c.min_stop_distance_frac * price:
            self._note("stop_too_tight")
            return 0.0
        # Trade-Qualität: Hin- und Rückweg-Kosten im Verhältnis zum Risiko
        cost = price * (2 * self.costs.taker_fee + 2 * self.costs.slippage_bps / 10_000)
        if cost / sig.stop_distance > c.max_cost_in_r:
            self._note("cost_too_high")
            return 0.0
        if c.sizing == "vol_target":
            vol = self.stats.volatility(s, i) if self.stats else float("nan")
            if not math.isfinite(vol):
                return 0.0
            notional = equity * c.target_vol_per_position * abs(v) / vol
            qty = notional / price
        else:
            qty = equity * c.risk_per_trade * abs(v) / sig.stop_distance
        qty = min(qty, c.max_symbol_exposure * equity / price)
        return math.copysign(qty, v)

    def _portfolio_limits(self, i: int, q: dict[str, float], prices: dict[str, float], equity: float) -> dict:
        c = self.cfg
        if not q or equity <= 0:
            return q
        notion = {s: q[s] * prices[s] for s in q}
        gross = sum(abs(v) for v in notion.values())
        max_gross = min(c.max_gross_exposure, c.max_leverage, HARD_MAX_LEVERAGE) * equity
        if gross > max_gross:
            self._note("gross_exposure_cap")
            q = {s: v * max_gross / gross for s, v in q.items()}
            notion = {s: q[s] * prices[s] for s in q}
        net = sum(notion.values())
        max_net = c.max_net_exposure * equity
        if abs(net) > max_net:
            self._note("net_exposure_cap")
            side = 1 if net > 0 else -1
            same = sum(v for v in notion.values() if v * side > 0)
            other = net - same
            # Positionen der dominanten Seite so skalieren, dass |net| = max_net
            k = (side * max_net - other) / same if same else 1.0
            q = {s: (v * k if notion[s] * side > 0 else v) for s, v in q.items()}
        # Korrelationsbewusst: Portfolio-Vola aus Kovarianz begrenzen
        if self.stats is not None:
            syms = [s for s in q if q[s]]
            if syms:
                cov = self.stats.covariance(i, syms)
                if cov is not None:
                    w = np.array([q[s] * prices[s] / equity for s in syms])
                    pvol = float(np.sqrt(max(w @ cov @ w, 0.0)))
                    if pvol > c.target_portfolio_vol:
                        self._note("portfolio_vol_cap")
                        k = c.target_portfolio_vol / pvol
                        q = {s: v * k for s, v in q.items()}
        return q

    def _liquidation_safety(self, account: Account, q: dict, prices: dict, stop_dist: dict) -> dict:
        """Positionen verkleinern, bis jeder Stop deutlich vor der Liquidation liegt."""
        if not any(q.values()):
            return q
        buffer = self.cfg.liquidation_buffer
        scale = 1.0
        for _ in range(30):
            sim = Account(cash=account.equity(prices), mmr=self.mmr)
            for s, qty in q.items():
                if qty:
                    sim.apply_fill(s, qty * scale, prices[s], 0.0)
            ok = True
            for s, qty in q.items():
                if not qty:
                    continue
                liq = sim.liquidation_price(s, prices)
                if liq is None:
                    continue
                if abs(prices[s] - liq) < buffer * stop_dist.get(s, 0.0):
                    ok = False
                    break
            if ok:
                break
            scale *= 0.85
        if scale < 1.0:
            self._note("liquidation_buffer")
        return {s: v * scale for s, v in q.items()}

    def _note(self, what: str) -> None:
        self.state.blocks[what] = self.state.blocks.get(what, 0) + 1


def _is_reduction(cur: float, tgt: float) -> bool:
    return tgt == 0 or (cur != 0 and (cur > 0) == (tgt > 0) and abs(tgt) <= abs(cur))


def _limit_to_reduction(cur: float, tgt: float) -> float:
    """Bei Sperre: höchstens verkleinern, nie vergrößern oder neu eröffnen."""
    if cur == 0 or tgt == 0 or (cur > 0) != (tgt > 0):
        return 0.0 if (cur == 0 or (cur > 0) != (tgt > 0)) else tgt
    return tgt if abs(tgt) <= abs(cur) else cur
