"""Kommandozeile:  python -m wettbot <befehl>

  fetch                         Ergebnisdaten (openfootball) neu laden
  picks  --odds DATEI | --api   Value-Wetten für die Quoten finden
  settle                        offene Wetten mit Ergebnissen abrechnen
  report                        Bilanz (Gewinn, ROI, CLV)
  backtest                      Walk-Forward-Test der Prognosegüte (CL)
  ranking                       Teamstärken
"""
from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

import pandas as pd

from . import backtest, data, ledger, odds as odds_mod
from .model import DixonColes
from .value import Settings, find_value, select_bets

REPORTS = data.ROOT / "reports"
SEL_DE = {"H": "Heimsieg", "D": "Remis", "A": "Auswärtssieg", "O": "Über", "U": "Unter",
          "Y": "Ja", "N": "Nein"}


def _fit(as_of=None):
    df = data.load_all()
    return df, DixonColes().fit(df, as_of=as_of)


def _label(market: str, sel: str) -> str:
    if market.startswith("OU"):
        return f"{SEL_DE[sel]} {market[2:]} Tore"
    if market == "BTTS":
        return f"Beide treffen: {SEL_DE[sel]}"
    return SEL_DE[sel]


def cmd_picks(a):
    cfg = Settings(**{f.name: getattr(a, f.name) for f in fields(Settings)
                      if getattr(a, f.name, None) is not None})
    if a.api:
        o = odds_mod.fetch_odds_api()
        if a.date:
            o = o[o["date"] == a.date]
        snap = data.DATA / "odds" / f"api-{odds_mod.now_berlin():%Y-%m-%d-%H%M}.csv"
        snap.parent.mkdir(parents=True, exist_ok=True)
        o.to_csv(snap, index=False)
        print(f"Quoten gespeichert: {snap}")
    else:
        o = odds_mod.load_csv(a.odds)
    as_of = pd.Timestamp(o["date"].min())
    df, model = _fit(as_of)
    names = set(df["home"]) | set(df["away"])
    cands = find_value(model, o, names, cfg)
    bets = select_bets(cands, cfg)

    # Übersicht aller Spiele
    print(f"\nModell trainiert bis {as_of.date()} mit {len(df[df.date < as_of])} Spielen\n")
    ov = cands[cands["markt"] == "1X2"].pivot_table(
        index=["anstoss", "spiel", "xg"], columns="tipp", values=["p_modell", "p_markt"], aggfunc="first")
    if not ov.empty:
        ov.columns = [f"{'Modell' if m == 'p_modell' else 'Markt'} {t}" for m, t in ov.columns]
        cols = [c for c in ["Modell H", "Markt H", "Modell D", "Markt D", "Modell A", "Markt A"] if c in ov]
        print((ov[cols] * 100).round(1).to_string())
    skipped = cands[cands["hinweis"].fillna("") != ""].drop_duplicates("spiel")
    for r in skipped.itertuples():
        print(f"  übersprungen: {r.spiel} ({r.hinweis})")

    print(f"\n{len(bets)} Value-Wette(n), Bankroll {cfg.bankroll:.0f} €:\n")
    for r in bets.itertuples():
        print(f"  {r.anstoss}  {r.spiel:<34} {_label(r.markt, r.tipp):<22} @ {r.quote:<5} "
              f"({r.buchmacher})  p={r.p:.1%}  EV={r.ev:+.1%}  Einsatz {r.einsatz:.2f} €")
    if len(bets):
        print(f"\n  Gesamteinsatz {bets.einsatz.sum():.2f} €, erwarteter Gewinn {bets.erw_gewinn.sum():+.2f} €")

    if a.save and len(bets):
        new = ledger.add(bets)
        print(f"\n{len(new)} Wette(n) ins Journal {ledger.LEDGER} übernommen")
    if a.report:
        write_report(cands, bets, cfg, as_of, Path(a.report))


def write_report(cands, bets, cfg, as_of, path: Path):
    lines = [f"# Wettbot – Champions League {as_of:%d.%m.%Y}", "",
             f"Bankroll {cfg.bankroll:.0f} € · Viertel-Kelly · min. EV {cfg.min_edge:.0%} · "
             f"Modellgewicht {cfg.model_weight:.0%} (1X2)", "",
             "## Value-Wetten", ""]
    if len(bets):
        lines += ["| Anstoß | Spiel | Tipp | Quote | Buchmacher | p | EV | Einsatz |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in bets.itertuples():
            lines.append(f"| {r.anstoss} | {r.spiel} | {_label(r.markt, r.tipp)} | {r.quote:.2f} | "
                         f"{r.buchmacher} | {r.p:.1%} | {r.ev:+.1%} | {r.einsatz:.2f} € |")
        lines += ["", f"Gesamteinsatz **{bets.einsatz.sum():.2f} €**, erwarteter Gewinn "
                      f"**{bets.erw_gewinn.sum():+.2f} €**."]
    else:
        lines.append("Keine Wette erfüllt die Kriterien – kein Einsatz ist dann die richtige Entscheidung.")
    lines += ["", "## Alle Spiele (1X2, Modell vs. margenbereinigter Markt)", "",
              "| Anstoß | Spiel | xG | Heim M/Mk | Remis M/Mk | Gast M/Mk |", "|---|---|---|---|---|---|"]
    def cell(g, sel):
        r = g[g.tipp == sel]
        if r.empty:
            return "–"
        r = r.iloc[0]
        return f"{r.p_modell:.0%} / " + ("–" if pd.isna(r.p_markt) else f"{r.p_markt:.0%}")

    one = cands[cands["markt"] == "1X2"]
    for (ko, sp, xg), g in one.groupby(["anstoss", "spiel", "xg"], sort=True):
        lines.append(f"| {ko} | {sp} | {xg} | {cell(g, 'H')} | {cell(g, 'D')} | {cell(g, 'A')} |")
    lines += ["", "_Quoten sind Momentaufnahmen. Vor dem Platzieren aktuelle Quote prüfen: "
                  "liegt sie unter der hier genannten, sinkt der Erwartungswert – ggf. auslassen._"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nBericht: {path}")


def cmd_settle(a):
    led = ledger.settle(data.load_all())
    print(json.dumps(ledger.report(led), indent=2, ensure_ascii=False))


def cmd_report(a):
    led = ledger.load()
    print(led.tail(30).to_string(index=False) if len(led) else "Journal leer")
    print(json.dumps(ledger.report(led), indent=2, ensure_ascii=False))


def cmd_backtest(a):
    pred = backtest.walk_forward(data.load_all(), start=a.start)
    print(json.dumps(backtest.scores(pred), indent=2, ensure_ascii=False))
    print(backtest.calibration(pred).round(3).to_string())


def cmd_ranking(a):
    df, model = _fit()
    r = model.ranking()
    print(r.head(a.top).round(3).to_string())


def main(argv=None):
    p = argparse.ArgumentParser(prog="wettbot", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(fn=lambda a: data.fetch())

    pk = sub.add_parser("picks")
    src = pk.add_mutually_exclusive_group(required=True)
    src.add_argument("--odds", help="Quoten-CSV")
    src.add_argument("--api", action="store_true", help="Live-Quoten über The Odds API (ODDS_API_KEY)")
    pk.add_argument("--date", help="nur dieses Datum (JJJJ-MM-TT), bei --api")
    pk.add_argument("--save", action="store_true", help="Wetten ins Journal schreiben")
    pk.add_argument("--report", help="Markdown-Bericht hierhin schreiben")
    for f in fields(Settings):
        pk.add_argument(f"--{f.name.replace('_', '-')}", dest=f.name, type=float, default=None)
    pk.set_defaults(fn=cmd_picks)

    sub.add_parser("settle").set_defaults(fn=cmd_settle)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    bt = sub.add_parser("backtest")
    bt.add_argument("--start", default="2024-09-01")
    bt.set_defaults(fn=cmd_backtest)
    rk = sub.add_parser("ranking")
    rk.add_argument("--top", type=int, default=40)
    rk.set_defaults(fn=cmd_ranking)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
