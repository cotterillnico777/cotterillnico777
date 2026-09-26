"""Research- und Backtest-Befehle."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("quantbot")


def load_markets(cfg, timeframe: str, symbols=None, synthetic: bool = False, synthetic_days: int = 1500):
    from .data import DataStore, MarketData, MarketSeries
    from .data.synthetic import synthetic_funding, synthetic_ohlcv
    from .core.timeframes import tf_seconds

    symbols = symbols or [i.symbol for i in cfg.instruments]
    if synthetic:
        n = int(synthetic_days * 86400 / tf_seconds(timeframe))
        out = {}
        for k, s in enumerate(symbols):
            df = synthetic_ohlcv(n, timeframe, seed=cfg.research.seed + k, regime_switch=True, start="2020-01-01")
            out[s] = MarketSeries(s, timeframe, df, synthetic_funding(df.index, seed=k), f"synthetic{k}", True)
        return out
    md = MarketData(DataStore(cfg.data.directory), cfg.data.exchange)
    return {s: md.load(s, timeframe) for s in symbols}


def cmd_research(args, cfg) -> int:
    from .research.pipeline import Researcher
    from .research.report import write_report
    from .strategies import STRATEGIES

    names = args.strategies or sorted(STRATEGIES)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    for tf in args.timeframes:
        markets = load_markets(cfg, tf, args.symbols, args.synthetic)
        researcher = Researcher(cfg, markets)
        log.info("Zeiträume %s: %s", tf, researcher.splits)
        result = researcher.run_all(names, jobs=args.jobs)
        meta = {s: {"rows": len(m.ohlcv), "hash": m.data_hash, "synthetic": m.synthetic,
                    "funding_history": m.funding is not None} for s, m in markets.items()}
        path = write_report(result, meta, Path(args.out) / f"{stamp}_{tf}")
        print(f"Bericht {tf}: {path}")
    return 0


def cmd_backtest(args, cfg) -> int:
    from .backtesting.metrics import format_metrics
    from .config.schema import StrategySlot
    from .research.runner import Prepared, run

    slots = list(cfg.strategies)
    if args.strategy:
        slots = [StrategySlot(args.strategy, {}, timeframe=args.timeframe)]
    if not slots:
        print("Keine Strategie: --strategy NAME oder strategies: in der Konfiguration")
        return 2
    tf = slots[0].timeframe if not args.strategy else args.timeframe
    markets = load_markets(cfg, tf, args.symbols, args.synthetic)
    import pandas as pd

    res = run(Prepared(cfg, markets, slots),
              start=pd.Timestamp(args.start, tz="UTC") if args.start else None,
              end=pd.Timestamp(args.end, tz="UTC") if args.end else None)
    print(format_metrics(res.metrics))
    b = res.metrics["benchmark"]
    print(f"Buy & Hold (gleichgewichtet): Rendite {b['total_return']:+.1%}, Sharpe {b['sharpe']:.2f}, "
          f"Max-DD {b['max_drawdown']:.1%}")
    if res.metrics.get("risk_blocks"):
        print(f"Eingriffe der Risk Engine: {res.metrics['risk_blocks']}")
    return 0


def register(sub) -> None:
    r = sub.add_parser("research", help="Forschungspipeline (Train/Val/WF/Stress/MC/OOS)")
    r.add_argument("--timeframes", nargs="+", default=["4h", "1d"])
    r.add_argument("--strategies", nargs="+", help="Standard: alle")
    r.add_argument("--symbols", nargs="+")
    r.add_argument("--out", default="research_output")
    r.add_argument("--synthetic", action="store_true", help="Funktionstest mit synthetischen Daten")
    import os

    r.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                   help="parallele Prozesse (Standard: alle Kerne bis auf einen)")
    r.set_defaults(func=cmd_research)

    b = sub.add_parser("backtest", help="Einzelner Backtest (Strategie oder Konfiguration)")
    b.add_argument("-s", "--strategy")
    b.add_argument("-t", "--timeframe", default="4h")
    b.add_argument("--symbols", nargs="+")
    b.add_argument("--start")
    b.add_argument("--end")
    b.add_argument("--synthetic", action="store_true")
    b.set_defaults(func=cmd_backtest)
