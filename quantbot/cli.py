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


def cmd_data_audit(args, cfg) -> int:
    from .data import DataStore
    from .core.timeframes import tf_seconds as _tf_seconds
    from .data.audit import audit_all, write_audit

    symbols = args.symbols or [i.symbol for i in cfg.instruments]
    result = audit_all(DataStore(cfg.data.directory), cfg.data.exchange, symbols, args.timeframes)
    path = write_audit(result, args.out)
    from .data.audit import save_incidents

    inc = save_incidents(DataStore(cfg.data.directory), result["incidents"])
    grades = [a.grade for a in result["series"]] + [g for g, _, _ in result["funding"].values()]
    for a in result["series"]:
        print(f"{a.grade:4}  {a.symbol} {a.timeframe}: {'; '.join(a.reasons) or 'ohne Befund'}")
        for ts, r in a.crosstf.iterrows():
            print(f"        {ts}  {'Volumen' if r['nur_volumen'] else 'Preis  '}  Preis Δ {r['max_preisabweichung_pct']:.4f} %"
                  f"  Volumen Δ {r['volumenabweichung_pct']:+.2f} %  -> {r['ursache']}")
        if a.timeframe == min(args.timeframes, key=_tf_seconds) and len(a.zero_volume):
            print("        ohne Handel: " + ", ".join(str(t) for t in a.zero_volume.index))
    for s, (g, reasons, _) in result["funding"].items():
        print(f"{g:4}  {s} Funding: {'; '.join(reasons) or 'ohne Befund'}")
    if result["incidents"]:
        print(f"\n{len(result['incidents'])} Kerzen mit Börsenereignis -> ohne Handel im Backtest: {inc}")
    print(f"\nBericht: {path}")
    return 1 if "FAIL" in grades else 0


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
    au = data.add_parser("audit", help="Ausführliche Datenprüfung mit PASS/WARN/FAIL (ändert nichts)")
    au.add_argument("--timeframes", nargs="+", default=["15m", "1h", "4h", "1d"])
    au.add_argument("--symbols", nargs="+")
    au.add_argument("--out", default="research_output/data_audit")
    au.set_defaults(func=cmd_data_audit)

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
