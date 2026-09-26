"""Phase 7: Paper-/Forward-Ergebnisse gegen einen Backtest über denselben Zeitraum vergleichen.

Fragen:
  - Signal-Drift: liefert die Strategie live dieselben Signale wie im Backtest?
  - Execution-Gap: wie viel schlechter sind die Ausführungspreise (Slippage-Lücke)?
  - Trade-Abgleich: fehlen Trades auf einer Seite?
  - Performance-Drift: Rendite/Gebühren im Vergleich
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..analytics import journal_equity, journal_trades
from ..config.schema import Config
from ..data import MarketSeries
from .runner import Prepared, run


def compare_forward(cfg: Config, journal, markets: dict[str, MarketSeries]) -> dict:
    eq_live = journal_equity(journal)
    if eq_live.empty:
        raise ValueError("Journal enthält keine Equity-Daten (Paper noch nicht gelaufen?)")
    start, end = eq_live.index[0], eq_live.index[-1]
    tf = next(iter(markets.values())).timeframe
    step = pd.Timedelta(next(iter(markets.values())).ohlcv.index.to_series().diff().median())
    prep = Prepared(cfg, markets, cfg.strategies)
    bt = run(prep, start=start.floor(step), end=end.ceil(step) + step, label="forward_compare")

    # --- Signal-Drift: gleiche Kerzen, gleiche Symbole
    rows = journal.query("SELECT ts, symbol, value FROM signals")
    live_sig = pd.DataFrame([dict(r) for r in rows])
    from ..portfolio.allocator import StrategyPortfolio
    from ..risk.engine import RiskEngine

    port = StrategyPortfolio(markets, cfg.strategies, RiskEngine(cfg.risk, cfg.costs, {}), cfg.regime,
                             computed=prep.computed, regimes=prep.regimes)
    idx = bt.equity.index
    port.bind(idx)
    diffs, n = [], 0
    if not live_sig.empty:
        live_sig["ts"] = pd.to_datetime(live_sig["ts"], utc=True)
        for _, r in live_sig.iterrows():
            if r["ts"] not in idx:
                continue
            i = idx.get_loc(r["ts"])
            b = port.signals_at(i).get(r["symbol"])
            if b is not None:
                diffs.append(abs(b.value - r["value"]))
                n += 1
    signal = {"compared": n, "mean_abs_diff": float(np.mean(diffs)) if diffs else float("nan"),
              "share_identical": float(np.mean([d < 1e-6 for d in diffs])) if diffs else float("nan")}

    # --- Trade-Abgleich und Slippage-Lücke
    lt = journal_trades(journal)
    btt = bt.trades
    matched, gaps = 0, []
    if not lt.empty and not btt.empty:
        lt["entry_time"] = pd.to_datetime(lt["entry_time"], utc=True)
        for _, t in lt.iterrows():
            cand = btt[(btt.symbol == t["symbol"]) & (btt.direction == t["direction"])]
            if cand.empty:
                continue
            dt = (pd.to_datetime(cand["entry_time"], utc=True) - t["entry_time"]).abs()
            j = dt.idxmin()
            if dt[j] <= 2 * step:
                matched += 1
                sign = 1 if t["direction"] == "long" else -1
                gaps.append(sign * (t["entry_price"] / cand.loc[j, "entry_price"] - 1) * 10_000)
    live_ret = eq_live.iloc[-1] / eq_live.iloc[0] - 1
    out = {
        "period": [str(start), str(end)],
        "signal_drift": signal,
        "trades": {"paper": int(len(lt)), "backtest": int(len(btt)), "matched": matched},
        "entry_slippage_gap_bps": {"mean": float(np.mean(gaps)) if gaps else float("nan"),
                                   "p90": float(np.quantile(gaps, 0.9)) if gaps else float("nan")},
        "return": {"paper": float(live_ret), "backtest": float(bt.metrics["total_return"])},
        "fees": {"paper": float(lt["fees"].sum()) if not lt.empty else 0.0, "backtest": float(bt.metrics["fees"])},
    }
    out["return"]["gap"] = out["return"]["paper"] - out["return"]["backtest"]
    return out


def format_forward(r: dict) -> str:
    s, t, g, ret = r["signal_drift"], r["trades"], r["entry_slippage_gap_bps"], r["return"]
    return "\n".join([
        "# Backtest vs. Forward (Paper)",
        "",
        f"Zeitraum: {r['period'][0]} bis {r['period'][1]}",
        f"Signal-Drift: {s['compared']} Signale verglichen, identisch {s['share_identical']:.0%}, "
        f"mittlere Abweichung {s['mean_abs_diff']:.3f}",
        f"Trades: Paper {t['paper']}, Backtest {t['backtest']}, zugeordnet {t['matched']}",
        f"Einstiegs-Slippage-Lücke: Ø {g['mean']:.1f} bps, 90 % unter {g['p90']:.1f} bps "
        "(positiv = Paper schlechter)",
        f"Rendite: Paper {ret['paper']:+.2%}, Backtest {ret['backtest']:+.2%}, Differenz {ret['gap']:+.2%}",
        f"Gebühren: Paper {r['fees']['paper']:.2f}, Backtest {r['fees']['backtest']:.2f}",
    ])


def to_json(r: dict) -> str:
    return json.dumps(r, indent=2, default=str)
