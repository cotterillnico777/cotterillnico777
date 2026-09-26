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


def cmd_run(args, cfg) -> int:
    from .backtesting.costs import CostModel
    from .config import resolve_mode
    from .core.types import Mode
    from .exchanges.ccxt_futures import CCXTFuturesAdapter
    from .exchanges.simulated import SimulatedExchange
    from .execution.trader import Trader
    from .monitoring.journal import Journal
    from .monitoring.logs import setup_logging

    mode = resolve_mode(cfg, args.mode)  # LIVE nur mit allen drei Freigaben
    setup_logging(cfg.runtime.log_file)
    db = args.journal or cfg.runtime.database.replace(".sqlite", f"_{mode.value}.sqlite")
    journal = Journal(db)
    mmr = {i.symbol: i.maintenance_margin_rate for i in cfg.instruments}
    if mode is Mode.PAPER:
        market = CCXTFuturesAdapter(cfg.data.exchange)
        exchange = SimulatedExchange(market, CostModel.from_config(cfg.costs), cfg.runtime.paper_balance, mmr)
    elif mode is Mode.LIVE:
        exchange = CCXTFuturesAdapter(cfg.data.exchange, with_keys=True)
        for inst in cfg.instruments:
            # Börsen-Hebel = nur Margin-Rahmen; die tatsächliche Größe bestimmt die Risk Engine
            exchange.set_leverage(inst.symbol, cfg.risk.max_leverage)
        print("*** LIVE: echte Orders mit echtem Geld ***")
    else:
        print("Für Backtests: python -m quantbot backtest / research")
        return 2
    trader = Trader(cfg, mode, exchange, journal)
    trader.run(max_cycles=1 if args.once else None)
    return 0


def cmd_status(args, cfg) -> int:
    from .monitoring.journal import Journal
    from .monitoring.status import format_status, status_report

    mode = args.mode or "paper"
    db = args.journal or cfg.runtime.database.replace(".sqlite", f"_{mode}.sqlite")
    if not Path(db).exists():
        print(f"Kein Journal unter {db}")
        return 1
    print(format_status(status_report(Journal(db), cfg.runtime.kill_switch_file)))
    return 0


def cmd_kill(args, cfg) -> int:
    Path(cfg.runtime.kill_switch_file).touch()
    print(f"Kill Switch gesetzt ({cfg.runtime.kill_switch_file}). Der Bot schließt alle Positionen "
          f"beim nächsten Zyklus und öffnet keine neuen. Aufheben: Datei löschen UND Journal-Risikostatus "
          f"bewusst zurücksetzen (neues Journal).")
    return 0


def cmd_analyze(args, cfg) -> int:
    from .analytics import full_report, journal_equity, journal_trades
    from .monitoring.journal import Journal

    if args.journal:
        j = Journal(args.journal)
        text = full_report(journal_trades(j), journal_equity(j))
    else:
        from .config.schema import StrategySlot
        from .research.runner import Prepared, run

        slots = list(cfg.strategies) or [StrategySlot(args.strategy, {}, timeframe=args.timeframe)]
        markets = load_markets(cfg, slots[0].timeframe, None, args.synthetic)
        res = run(Prepared(cfg, markets, slots))
        text = full_report(res.trades, res.equity)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text[:3000])
    print(f"\nVollständig: {out}")
    return 0


def cmd_compare(args, cfg) -> int:
    from .monitoring.journal import Journal
    from .research.forward import compare_forward, format_forward, to_json

    tf = cfg.strategies[0].timeframe
    markets = load_markets(cfg, tf)
    r = compare_forward(cfg, Journal(args.journal), markets)
    print(format_forward(r))
    Path(args.out).write_text(to_json(r), encoding="utf-8")
    return 0


def cmd_readiness(args, cfg) -> int:
    import json

    from .monitoring.journal import Journal
    from .monitoring.readiness import format_readiness, readiness

    j = Journal(args.journal) if args.journal and Path(args.journal).exists() else None
    fwd = json.loads(Path(args.forward).read_text()) if args.forward and Path(args.forward).exists() else None
    items = readiness(cfg, args.research, j, fwd)
    print(format_readiness(items))
    auto = [i for i in items if i.ok is not None]
    return 0 if all(i.ok for i in auto) else 1


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

    rn = sub.add_parser("run", help="Paper- oder Live-Handel (Standard: TRADING_MODE oder paper)")
    rn.add_argument("--mode", choices=["paper", "live"])
    rn.add_argument("--journal", help="SQLite-Datei (Standard aus runtime.database)")
    rn.add_argument("--once", action="store_true", help="nur ein Zyklus")
    rn.set_defaults(func=cmd_run)

    st = sub.add_parser("status", help="Bot-Status aus dem Journal")
    st.add_argument("--mode", choices=["paper", "live"])
    st.add_argument("--journal")
    st.set_defaults(func=cmd_status)

    k = sub.add_parser("kill", help="Kill Switch setzen (alles schließen, nichts Neues)")
    k.set_defaults(func=cmd_kill)

    an = sub.add_parser("analyze", help="Trade-Analyse (Journal oder Backtest)")
    an.add_argument("--journal")
    an.add_argument("-s", "--strategy", default="ema_trend")
    an.add_argument("-t", "--timeframe", default="4h")
    an.add_argument("--synthetic", action="store_true")
    an.add_argument("--out", default="research_output/analysis.md")
    an.set_defaults(func=cmd_analyze)

    cp = sub.add_parser("compare", help="Phase 7: Paper-Journal vs. Backtest im selben Zeitraum")
    cp.add_argument("--journal", required=True)
    cp.add_argument("--out", default="research_output/forward_compare.json")
    cp.set_defaults(func=cmd_compare)

    rd = sub.add_parser("readiness", help="Phase 8: Live-Readiness-Checkliste (aktiviert nichts)")
    rd.add_argument("--research", help="results.json aus 'quantbot research'")
    rd.add_argument("--journal", help="Paper-Journal")
    rd.add_argument("--forward", help="JSON aus 'quantbot compare'")
    rd.set_defaults(func=cmd_readiness)
