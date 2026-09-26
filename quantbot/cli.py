"""Kommandozeile: python -m quantbot <bereich> <befehl> ..."""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from .config import load_config, load_dotenv
from .monitoring.logs import setup_logging

log = logging.getLogger("quantbot")


def cmd_data_download(args, cfg) -> int:
    from .data import DataStore, MarketData
    from .exchanges.ccxt_futures import CCXTFuturesAdapter

    adapter = CCXTFuturesAdapter(cfg.data.exchange)
    md = MarketData(DataStore(cfg.data.directory), cfg.data.exchange)
    start = pd.Timestamp(args.start or cfg.data.start, tz="UTC")
    symbols = args.symbols or [i.symbol for i in cfg.instruments]
    failed = 0
    for symbol in symbols:
        for tf in args.timeframes:
            log.info("Lade %s %s ab %s", symbol, tf, start.date())
            try:
                rep = md.update(adapter, symbol, tf, start)
                print(f"{symbol} {tf}: {rep.summary()}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.error("%s %s fehlgeschlagen: %s", symbol, tf, exc)
    return 1 if failed else 0


def cmd_data_validate(args, cfg) -> int:
    from .data import DataStore, validate_ohlcv

    store = DataStore(cfg.data.directory)
    bad = 0
    for symbol in args.symbols or [i.symbol for i in cfg.instruments]:
        for tf in args.timeframes:
            try:
                df = store.load("ohlcv", cfg.data.exchange, symbol, tf)
            except FileNotFoundError as exc:
                print(f"{symbol} {tf}: {exc}")
                bad += 1
                continue
            rep = validate_ohlcv(df, tf)
            bad += 0 if rep.ok else 1
            print(f"{symbol} {tf}: {rep.summary()}")
            try:
                f = store.load("funding", cfg.data.exchange, symbol)
                print(f"  Funding: {len(f)} Einträge {f.index[0]} bis {f.index[-1]}")
            except FileNotFoundError:
                print("  Funding: keine Historie (Backtest nutzt konservative Fallback-Rate)")
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="quantbot", description="Quantitativer Krypto-Futures-Bot (v2)")
    p.add_argument("-c", "--config", help="YAML-Konfiguration (Standard: eingebaute Defaults)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="area", required=True)

    data = sub.add_parser("data", help="Marktdaten laden und prüfen").add_subparsers(dest="cmd", required=True)
    dl = data.add_parser("download", help="Kerzen + Funding laden/ergänzen")
    dl.add_argument("--timeframes", nargs="+", default=["15m", "1h", "4h", "1d"])
    dl.add_argument("--symbols", nargs="+")
    dl.add_argument("--start", help="z. B. 2020-01-01")
    dl.set_defaults(func=cmd_data_download)
    va = data.add_parser("validate", help="Datenqualität prüfen")
    va.add_argument("--timeframes", nargs="+", default=["15m", "1h", "4h", "1d"])
    va.add_argument("--symbols", nargs="+")
    va.set_defaults(func=cmd_data_validate)

    from . import cli_research  # noqa: F401  (registriert weitere Befehle)

    cli_research.register(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    setup_logging(cfg.runtime.log_file if getattr(args, "log_to_file", False) else None,
                  logging.DEBUG if args.verbose else logging.INFO)
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
