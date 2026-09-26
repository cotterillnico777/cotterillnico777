"""Strategie-Portfolio: kombiniert Strategiesignale (regimeabhängig) und übergibt an die Risk Engine.

Dies ist das Entscheidungsmodell für Backtest, Paper und Live. Es ist die einzige Stelle,
an der Strategie-, Regime- und Risikoschicht zusammenkommen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config.schema import RegimeConfig, StrategySlot
from ..core.types import Intent
from ..data import MarketSeries
from ..regimes import detect_regimes, regime_allows
from ..risk.engine import RiskEngine, Signal
from ..strategies import StrategyContext, create


@dataclass
class SlotFrames:
    slot: StrategySlot
    strategy_id: str
    frames: dict[str, pd.DataFrame]  # Symbol -> Ausgabe der Strategie (Index = Zeitstempel)


def compute_slot(slot: StrategySlot, markets: dict[str, MarketSeries]) -> SlotFrames:
    strat = create(slot.name, slot.params)
    symbols = slot.symbols or list(markets)
    closes = {s: m.ohlcv["close"] for s, m in markets.items()}
    frames = {}
    for s in symbols:
        m = markets[s]
        funding = m.funding["rate"] if m.funding is not None and len(m.funding) else None
        ctx = StrategyContext(symbol=s, timeframe=m.timeframe, universe_closes=closes, funding=funding)
        frames[s] = strat.compute(m.ohlcv, ctx)
    return SlotFrames(slot, strat.id, frames)


class StrategyPortfolio:
    def __init__(
        self,
        markets: dict[str, MarketSeries],
        slots: list[StrategySlot],
        risk: RiskEngine,
        regime_cfg: RegimeConfig,
        computed: list[SlotFrames] | None = None,
        regimes: dict[str, pd.DataFrame] | None = None,
    ) -> None:
        self.markets = markets
        self.slots = slots
        self.risk = risk
        self.computed = computed if computed is not None else [compute_slot(s, markets) for s in slots]
        self.regimes = regimes or {s: detect_regimes(m.ohlcv, m.timeframe, regime_cfg) for s, m in markets.items()}
        self._bound_index = None

    def bind(self, index: pd.DatetimeIndex) -> None:
        """Vorberechnete Tabellen auf den Kerzenindex der Engine ausrichten (Arrays für Tempo)."""
        self._bound_index = index
        self.arr: list[dict[str, dict[str, np.ndarray]]] = []
        for sf in self.computed:
            per = {}
            for s, f in sf.frames.items():
                g = f.reindex(index)
                per[s] = {c: g[c].values for c in g.columns}
            self.arr.append(per)
        self.reg = {}
        for s, r in self.regimes.items():
            g = r.reindex(index)
            self.reg[s] = (g["trend"].fillna("unknown").values, g["vol"].fillna("unknown").values)

    # ------------------------------------------------------------------ Engine
    def decide(self, view) -> list[Intent]:
        if self._bound_index is None or self._bound_index is not view._e.index:
            self.bind(view._e.index)
        i = view.i
        signals: dict[str, Signal] = {}
        for s in self.markets:
            trend, vol = self.reg[s][0][i], self.reg[s][1][i]
            num = den = 0.0
            stop_num = stop_den = 0.0
            tp = None
            contributors = []
            features = {}
            for k, sf in enumerate(self.computed):
                a = self.arr[k].get(s)
                if a is None:
                    continue
                w = sf.slot.weight
                den += w
                sig = a["signal"][i]
                if not np.isfinite(sig) or sig == 0 or not regime_allows(sf.slot.regimes, trend, vol):
                    continue
                num += w * sig
                sd = a["stop_distance"][i]
                if np.isfinite(sd) and sd > 0:
                    stop_num += abs(w * sig) * sd
                    stop_den += abs(w * sig)
                t = a["take_profit_distance"][i]
                if np.isfinite(t) and t > 0:
                    tp = t
                contributors.append(sf.strategy_id)
                for col, arr in a.items():
                    if col.startswith("f_"):
                        v = arr[i]
                        if np.isfinite(v):
                            features[f"{sf.slot.name}.{col[2:]}"] = float(v)
            value = num / den if den > 0 else 0.0
            if stop_den <= 0:
                value = 0.0
            stop = stop_num / stop_den if stop_den > 0 else float("nan")
            meta = {
                "strategy": "+".join(contributors) if contributors else "none",
                "signal_strength": float(value),
                "regime": f"{trend}|{vol}",
                "entry_reason": ",".join(contributors),
                "features": json.dumps(features, sort_keys=True),
            }
            signals[s] = Signal(s, value, stop, tp if len(contributors) == 1 else None, meta)
        return self.risk.targets(i, view.timestamp, view.account, view.prices, signals)

    def on_trade_closed(self, trade, i: int) -> None:
        self.risk.on_trade_closed(trade.net_pnl, trade.entry_equity, i)
