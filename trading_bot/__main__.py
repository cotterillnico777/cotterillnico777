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
        "run": cmd_run,
        "status": cmd_status,
    }[args.command]
    return handler(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
