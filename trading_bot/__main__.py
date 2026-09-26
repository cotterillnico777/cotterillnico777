"""Kommandozeile: python -m trading_bot <befehl> ..."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import Config, load_config
from .strategies import STRATEGIES, create_strategy

LIVE_CONFIRMATION = "ECHTGELD"


def load_dotenv(path: str = ".env") -> None:
    """Minimaler .env-Loader (KEY=VALUE pro Zeile), überschreibt nichts."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def setup_logging(log_file: str | None, verbose: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=handlers,
    )


def _strategy_from(cfg: Config, name: str | None):
    if name and name != cfg.strategy.name:
        # Andere Strategie per CLI: deren Standardparameter verwenden
        return create_strategy(name)
    return create_strategy(cfg.strategy.name, cfg.strategy.params)


def cmd_strategies(_args, _cfg: Config) -> int:
    for name, cls in sorted(STRATEGIES.items()):
        params = ", ".join(f"{k}={v}" for k, v in cls.default_params.items())
        doc = (cls.__doc__ or "").strip().splitlines()[0]
        print(f"{name:20s} {doc}\n{'':20s} Parameter: {params}")
    return 0


def cmd_backtest(args, cfg: Config) -> int:
    from .backtest import run_backtest
    from .data import load_csv, load_history

    if args.csv:
        df = load_csv(args.csv)
    else:
        from .broker import create_exchange

        ex = create_exchange(cfg.exchange.id)
        df = load_history(ex, cfg.symbol, cfg.timeframe, args.days or cfg.backtest.days)

    names = sorted(STRATEGIES) if args.all else [args.strategy or cfg.strategy.name]
    for name in names:
        strategy = _strategy_from(cfg, name)
        result = run_backtest(df, strategy, cfg.risk, cfg.backtest, cfg.timeframe)
        print(f"\n=== {strategy} | {cfg.symbol} {cfg.timeframe} ===")
        print(result.summary())
        if args.trades:
            for t in result.trades:
                print(
                    f"  {t.entry_time} -> {t.exit_time}  {t.entry_price:.4f} -> "
                    f"{t.exit_price:.4f}  {t.return_pct:+.2f} %  ({t.exit_reason})"
                )
    print(
        "\nHinweis: Vergangene Ergebnisse garantieren keine zukünftigen Gewinne. "
        "Positionsgröße laut risk.position_fraction / max_order_value."
    )
    return 0


def _load_datasets(args, cfg: Config) -> dict:
    from .data import load_csv, load_history

    if args.csv:
        return {Path(p).stem: load_csv(p) for p in args.csv}
    from .broker import create_exchange

    symbols = args.symbols.split(",") if args.symbols else [cfg.symbol, *cfg.optimize.symbols]
    ex = create_exchange(cfg.exchange.id)
    days = args.days or cfg.backtest.days
    return {
        s.strip(): load_history(ex, s.strip(), cfg.timeframe, days)
        for s in dict.fromkeys(symbols)
    }


def cmd_optimize(args, cfg: Config) -> int:
    import pandas as pd

    from .optimize import recommend, walk_forward

    if args.train_days:
        cfg.optimize.train_days = args.train_days
    if args.test_days:
        cfg.optimize.test_days = args.test_days
    if args.metric:
        cfg.optimize.metric = args.metric
    if args.full_stake:
        cfg.risk.position_fraction = 1.0
        cfg.risk.max_order_value = float("inf")
    datasets = _load_datasets(args, cfg)
    names = sorted(STRATEGIES) if args.all else [args.strategy or cfg.strategy.name]
    o = cfg.optimize
    print(
        f"Walk-Forward: {o.train_days} Tage optimieren -> {o.test_days} Tage ungesehen testen, "
        f"Ziel '{o.metric}', min. {o.min_trades} Trades pro Trainingsfenster\n"
        f"Märkte: {', '.join(datasets)} | Timeframe {cfg.timeframe}"
    )
    pd.set_option("display.width", 200)
    overview = []
    for name in names:
        for market, df in datasets.items():
            wf = walk_forward(df, name, cfg, market)
            s = wf.summary
            print(f"\n=== {name} | {market} ===")
            print(wf.fold_table().to_string(index=False))
            print(
                f"Out-of-Sample gesamt: {s['oos_return_pct']:+.2f} %  "
                f"(Standardparameter {s['default_return_pct']:+.2f} %, "
                f"Buy & Hold {s['buy_hold_pct']:+.2f} %)\n"
                f"Sharpe OOS {s['oos_sharpe']:.2f}, max. Drawdown {s['oos_max_dd_pct']:.2f} %, "
                f"profitable Fenster {s['profitable_folds_pct']:.0f} %, "
                f"Score Train Ø {s['avg_train_score']:.2f} -> Test Ø {s['avg_test_score']:.2f}"
            )
            overview.append(
                {
                    "Strategie": name,
                    "Markt": market,
                    "OOS %": round(s["oos_return_pct"], 2),
                    "Standard %": round(s["default_return_pct"], 2),
                    "Buy&Hold %": round(s["buy_hold_pct"], 1),
                    "Sharpe": round(s["oos_sharpe"], 2),
                    "MaxDD %": round(s["oos_max_dd_pct"], 2),
                    "Fenster +": f"{s['profitable_folds_pct']:.0f} %",
                    "Trades": s["trades"],
                }
            )
            if args.out:
                out = Path(args.out)
                out.mkdir(parents=True, exist_ok=True)
                tag = f"{name}_{market.replace('/', '-')}"
                wf.fold_table().to_csv(out / f"folds_{tag}.csv", index=False)
                wf.equity.to_csv(out / f"equity_{tag}.csv")

    print("\n=== Übersicht (nur ungesehene Testfenster) ===")
    print(pd.DataFrame(overview).to_string(index=False))
    stake = min(cfg.risk.position_fraction, cfg.risk.max_order_value / cfg.backtest.initial_balance)
    if stake < 1:
        print(
            f"Hinweis: Pro Trade werden höchstens ~{stake:.0%} des Kapitals eingesetzt "
            f"(risk.position_fraction / max_order_value), Buy & Hold rechnet mit 100 %. "
            f"Für einen fairen Vergleich mit Buy & Hold: --full-stake."
        )

    print("\n=== Empfehlung: robusteste Parameter über alle Märkte (ganzer Zeitraum) ===")
    for name in names:
        best, top = recommend(datasets, name, cfg)
        print(f"\n{name}:")
        print(top.to_string(index=False))
        if best:
            params = "\n".join(f"      {k}: {v}" for k, v in best.items())
            print(f"  -> für config.yaml:\n  strategy:\n    name: {name}\n    params:\n{params}")
    print(
        "\nSo liest du das: Zählt nur 'OOS %'. Liegt es nicht klar über 0 und über "
        "'Standard %', bringt die Optimierung nichts. Liegt es unter Buy & Hold, wäre "
        "einfaches Halten besser gewesen. 'Score Train' deutlich über 'Score Test' "
        "bedeutet Overfitting. Die Empfehlung ist in-sample und nur zusammen mit "
        "einem guten OOS-Ergebnis aussagekräftig."
    )
    return 0


def cmd_run(args, cfg: Config) -> int:
    from .bot import BotState, TradingBot
    from .broker import LiveBroker, PaperBroker, create_exchange

    live = cfg.runtime.mode == "live"
    if live != args.live:
        print(
            "Fehler: Für Echtgeld muss runtime.mode: live in der Konfiguration stehen "
            "UND --live angegeben werden. Für Paper-Trading beides weglassen.",
            file=sys.stderr,
        )
        return 2

    strategy = _strategy_from(cfg, args.strategy)
    state_file = cfg.runtime.state_file
    if live:
        exchange = create_exchange(cfg.exchange.id, cfg.exchange.sandbox, with_keys=True)
        broker = LiveBroker(exchange, cfg.symbol)
        base, quote = broker.balances()
        r = cfg.risk
        print(
            f"\n*** LIVE-TRADING MIT ECHTEM GELD ***\n"
            f"Börse: {cfg.exchange.id}{' (Sandbox)' if cfg.exchange.sandbox else ''}\n"
            f"Markt: {cfg.symbol} {cfg.timeframe}, Strategie: {strategy}\n"
            f"Guthaben: {base:.8f} {broker.base_ccy}, {quote:.2f} {broker.quote_ccy}\n"
            f"Max. pro Order: {r.max_order_value:.2f}, Stop-Loss: {r.stop_loss_pct:.1%}, "
            f"Tagesverlustlimit: {r.max_daily_loss:.2f}\n"
            f"Not-Aus: Datei '{cfg.runtime.kill_switch_file}' anlegen stoppt neue Käufe.\n"
        )
        if not args.yes:
            answer = input(f"Zum Starten '{LIVE_CONFIRMATION}' eingeben: ").strip()
            if answer != LIVE_CONFIRMATION:
                print("Abgebrochen.")
                return 1
    else:
        exchange = create_exchange(cfg.exchange.id, cfg.exchange.sandbox)
        state_file = str(Path(state_file).with_name(Path(state_file).stem + "_paper.json"))
        saved = BotState.load(Path(state_file)).paper
        broker = PaperBroker(
            quote=saved.get("quote", cfg.runtime.paper_balance),
            base=saved.get("base", 0.0),
            fee=cfg.backtest.fee,
            slippage=cfg.backtest.slippage,
        )

    bot = TradingBot(cfg, strategy, exchange, broker, state_path=state_file)
    bot.reconcile()
    try:
        bot.run(max_ticks=1 if args.once else None)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Beendet durch Benutzer")
        bot.save()
    return 0


def cmd_status(_args, cfg: Config) -> int:
    from .bot import BotState

    for label, path in (
        ("Live", Path(cfg.runtime.state_file)),
        ("Paper", Path(cfg.runtime.state_file).with_name(
            Path(cfg.runtime.state_file).stem + "_paper.json")),
    ):
        if not path.exists():
            continue
        s = BotState.load(path)
        print(f"== {label} ({path}) ==")
        print(f"Position: {s.position or 'keine'}")
        print(f"PnL heute: {s.realized_pnl_today:+.2f}, gesamt: {s.realized_pnl_total:+.2f}")
        if s.paper:
            print(f"Paper-Konto: {s.paper}")
        for t in s.trades[-5:]:
            print(f"  {t['time']} {t['side']:4s} {t['amount']:.8f} @ {t['price']:.4f} ({t['reason']})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trading_bot", description="Krypto-Trading-Bot")
    p.add_argument("-c", "--config", default="config.yaml", help="Pfad zur YAML-Konfiguration")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("strategies", help="Verfügbare Strategien anzeigen")

    bt = sub.add_parser("backtest", help="Strategie auf historischen Daten testen")
    bt.add_argument("-s", "--strategy", choices=sorted(STRATEGIES))
    bt.add_argument("--all", action="store_true", help="Alle Strategien vergleichen")
    bt.add_argument("--days", type=int, help="Anzahl Tage Historie")
    bt.add_argument("--csv", help="Kerzen aus CSV statt von der Börse")
    bt.add_argument("--trades", action="store_true", help="Einzelne Trades auflisten")

    op = sub.add_parser("optimize", help="Parameter-Scan mit Walk-Forward-Test")
    op.add_argument("-s", "--strategy", choices=sorted(STRATEGIES))
    op.add_argument("--all", action="store_true", help="Alle Strategien")
    op.add_argument("--days", type=int, help="Anzahl Tage Historie")
    op.add_argument("--symbols", help="Kommagetrennt, z. B. BTC/USDT,ETH/USDT,SOL/USDT")
    op.add_argument("--csv", action="append", help="Kerzen aus CSV (mehrfach möglich)")
    op.add_argument("--train-days", type=int)
    op.add_argument("--test-days", type=int)
    op.add_argument("--metric", choices=["sharpe", "return", "calmar"])
    op.add_argument("--out", help="Ordner für CSV-Ergebnisse")
    op.add_argument(
        "--full-stake",
        action="store_true",
        help="Jeden Trade mit 100 %% des Kapitals rechnen (vergleichbar mit Buy & Hold)",
    )

    run = sub.add_parser("run", help="Bot starten (Paper oder Live)")
    run.add_argument("-s", "--strategy", choices=sorted(STRATEGIES))
    run.add_argument("--live", action="store_true", help="Echtgeld (zusätzlich zu mode: live)")
    run.add_argument("--yes", action="store_true", help="Live-Bestätigung überspringen")
    run.add_argument("--once", action="store_true", help="Nur einen Durchlauf")

    sub.add_parser("status", help="Position, PnL und letzte Trades anzeigen")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()
    cfg_path = args.config if Path(args.config).exists() else None
    if cfg_path is None and args.config != "config.yaml":
        print(f"Konfiguration {args.config} nicht gefunden", file=sys.stderr)
        return 2
    cfg = load_config(cfg_path)
    setup_logging(cfg.runtime.log_file if args.command == "run" else None, args.verbose)
    handler = {
        "strategies": cmd_strategies,
        "backtest": cmd_backtest,
        "optimize": cmd_optimize,
        "run": cmd_run,
        "status": cmd_status,
    }[args.command]
    return handler(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
