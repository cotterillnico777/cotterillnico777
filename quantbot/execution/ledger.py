"""Trade-Ledger für PAPER/LIVE: bildet aus der Fill-Folge vollständige Trades (wie im Backtest).

Jeder Fill wird genau einmal und in Reihenfolge verarbeitet (Fortschritt im Journal gespeichert).
Teil-Schließungen, Aufstocken und Richtungswechsel werden wie im Backtest-Konto behandelt.
"""

from __future__ import annotations

from ..monitoring.journal import Journal


class TradeLedger:
    def __init__(self, journal: Journal) -> None:
        self.j = journal

    def _state(self, s: str) -> dict:
        return self.j.get(f"ledger:{s}") or {"qty": 0.0, "avg": 0.0, "trade": None}

    def set_meta(self, symbol: str, meta: dict) -> None:
        """Metadaten der letzten Entscheidung (für neu eröffnete Trades)."""
        self.j.set(f"last_meta:{symbol}", meta)

    def process(self, now: str, equity: float, gross: float, funding: dict[str, float]) -> list[dict]:
        last = int(self.j.get("ledger_last_fill", 0))
        rows = self.j.query("SELECT * FROM fills WHERE id > ? ORDER BY id", (last,))
        closed = []
        for f in rows:
            closed += self._apply(f, now, equity, gross, funding)
            last = f["id"]
        self.j.set("ledger_last_fill", last)
        return closed

    def _apply(self, f, now, equity, gross, funding) -> list[dict]:
        s = f["symbol"]
        st = self._state(s)
        q = f["qty"] if f["side"] == "buy" else -f["qty"]
        price, fee = f["price"], f["fee"]
        order = self.j.get_order_row(f["client_id"])
        reason = order["reason"] if order is not None else "unknown"
        out = []
        cur = st["qty"]
        if cur == 0 or (cur > 0) == (q > 0):
            new = cur + q
            st["avg"] = (st["avg"] * abs(cur) + price * abs(q)) / abs(new)
            st["qty"] = new
            if st["trade"] is None:
                meta = self.j.get(f"last_meta:{s}") or {}
                st["trade"] = {
                    "symbol": s, "direction": "long" if q > 0 else "short", "entry_time": f["ts"],
                    "entry_price": price, "qty": abs(q), "leverage": gross / equity if equity else None,
                    "stop": meta.get("stop"), "take_profit": meta.get("take_profit"),
                    "regime": meta.get("regime"), "strategy": meta.get("strategy"),
                    "strategy_version": meta.get("strategy_version"),
                    "signal_strength": meta.get("signal_strength"), "entry_reason": meta.get("entry_reason"),
                    "features": meta.get("features"), "gross_pnl": 0.0, "fees": fee,
                    "exit_notional": 0.0, "exit_qty": 0.0, "mfe": 0.0, "mae": 0.0,
                    "funding_start": funding.get(s, 0.0),
                }
            else:
                t = st["trade"]
                t["fees"] += fee
                t["entry_price"] = st["avg"]
                t["qty"] = max(t["qty"], abs(st["qty"]))
        else:
            closing = min(abs(q), abs(cur))
            t = st["trade"]
            realized = closing * (price - st["avg"]) * (1 if cur > 0 else -1)
            share = closing / abs(q)
            if t is not None:
                t["gross_pnl"] += realized
                t["fees"] += fee * share
                t["exit_notional"] += closing * price
                t["exit_qty"] += closing
            rest = cur + q
            if abs(rest) < 1e-12 or (rest > 0) != (cur > 0):
                if t is not None:
                    fund = funding.get(s, 0.0) - t.pop("funding_start", 0.0)
                    trade = {**t, "exit_time": f["ts"], "exit_price": t["exit_notional"] / t["exit_qty"],
                             "exit_reason": reason, "funding": fund,
                             "net_pnl": t["gross_pnl"] - t["fees"] - fund,
                             "mfe_pct": t["mfe"] * 100, "mae_pct": t["mae"] * 100}
                    for k in ("exit_notional", "exit_qty", "mfe", "mae"):
                        trade.pop(k, None)
                    self.j.trade(trade)
                    out.append(trade)
                st["trade"] = None
                st["qty"], st["avg"] = 0.0, 0.0
                if abs(rest) > 1e-12:  # Richtungswechsel: Rest eröffnet neuen Trade
                    self.j.set(f"ledger:{s}", st)
                    rest_fill = {**dict(f), "qty": abs(rest), "fee": fee * (1 - share)}
                    out += self._apply(rest_fill, now, equity, gross, funding)
                    return out
            else:
                st["qty"] = rest
        self.j.set(f"ledger:{s}", st)
        return out

    def update_excursions(self, symbol: str, high: float, low: float) -> None:
        st = self._state(symbol)
        t = st.get("trade")
        if not t:
            return
        e = t["entry_price"]
        if t["direction"] == "long":
            fav, adv = high / e - 1, low / e - 1
        else:
            fav, adv = 1 - low / e, 1 - high / e
        t["mfe"], t["mae"] = max(t["mfe"], fav), min(t["mae"], adv)
        self.j.set(f"ledger:{symbol}", st)
