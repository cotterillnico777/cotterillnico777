"""Analyse-Lauf für einen Spielplan und Ausgabe als Markdown-Bericht."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import analyse, data, roi, stats
from .model import DixonColes
from .names import Resolver, key


def load_context():
    """Ergebnisse (openfootball + Ligadaten) und Teamprofile."""
    df = data.load_all()
    xg = stats.load_xg_matches()
    mp = roi.map_teams(xg, df)
    df = stats.enrich(df, xg, mp)
    P = stats.Profiles.build(df, xg, stats.load_elo(), mp)
    return df, xg, mp, P


def train(verbose=True):
    """Trainingstabelle bauen (dauert ~10 Min.), bewerten, final fitten, speichern."""
    df, xg, mp, P = load_context()
    t = analyse.build_training(df, xg, P, mp, verbose=verbose)
    analyse.TRAINING.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(analyse.TRAINING, index=False)
    return fit_saved(t)


def fit_saved(t: pd.DataFrame | None = None):
    if t is None:
        t = pd.read_csv(analyse.TRAINING, parse_dates=["date"])
    ev = analyse.evaluate(t)
    a = analyse.Analyzer.fit(t)
    a.report = ev
    a.save()
    return a, ev


def run(fixtures: pd.DataFrame, euro: bool = True):
    """euro=True: Spiele im Europapokal (CL); False: Ligaspiele."""
    df, xg, mp, P = load_context()
    if not analyse.PARAMS.exists():
        raise SystemExit("Analysemodell fehlt: zuerst `python -m wettbot analyse-train` ausführen")
    an = analyse.Analyzer.load()
    res = Resolver(set(df.home) | set(df.away))
    out = []
    for d, g in fixtures.groupby("date", sort=True):
        as_of = pd.Timestamp(d)
        model = DixonColes().fit(df, as_of=as_of)
        for r in g.itertuples():
            h, a = res.resolve(r.home), res.resolve(r.away)
            if not h or not a or key(h) not in model.params["grp"] or key(a) not in model.params["grp"]:
                out.append(dict(spiel=f"{r.home} – {r.away}", fehler="Team unbekannt"))
                continue
            hk, ak = key(h), key(a)
            lh, la = model.expected_goals(hk, ak, False, euro)
            row = pd.DataFrame([dict(lh=lh, la=la, rho=model.params["rho"],
                                     **analyse.features(P, hk, ak, as_of))])
            p = an.predict(row, euro)
            out.append(dict(datum=d, anstoss=r.kickoff, spiel=f"{r.home} – {r.away}",
                            heim=r.home, gast=r.away, prognose=p, merkmale=row.iloc[0].to_dict()))
    return out, an


def _pct(x):
    return f"{100 * x:.0f} %"


def _num(x, nd=1):
    return "–" if x is None or pd.isna(x) else f"{x:.{nd}f}"


def render(results, an, title: str, euro: bool = True) -> str:
    method = ("Für Europapokalspiele nutzt das Tool die Torprognose allein: Im Test auf ungesehenen "
              "CL-Spielen war sie genauer als jede Kombination mit Form, Elo, Schüssen oder Ecken. "
              "Die übrigen Kennzahlen stehen als Hintergrund in den Spielblättern."
              if euro else
              "Wahrscheinlichkeiten aus der Kombination von Torprognose-Modell, Elo, Form, "
              "Tordifferenz, Torschüssen und Ecken – Gewichte aus ~10 000 vergangenen Spielen gelernt.")
    L = [f"# {title}", "", method, "", "## Übersicht", "",
         "| Anstoß | Spiel | 1 | X | 2 | Tipp | Über 2,5 | Beide treffen | Ecken (erw.) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if "fehler" in r:
            L.append(f"| | {r['spiel']} | – | – | – | {r['fehler']} | | | |")
            continue
        p = r["prognose"]
        x = p["1X2"]
        tipp = max(x, key=x.get)
        tipp_txt = {"H": "1", "D": "X", "A": "2"}[tipp]
        L.append(f"| {r['datum'][5:]} {r['anstoss']} | {r['spiel']} | {_pct(x['H'])} | {_pct(x['D'])} | "
                 f"{_pct(x['A'])} | **{tipp_txt}** | {_pct(p['OU2.5'])} | {_pct(p['BTTS'])} | "
                 f"{_num(p['ecken']['gesamt'])} |")
    for r in results:
        if "fehler" in r:
            continue
        p, m = r["prognose"], r["merkmale"]
        x, hz, ec = p["1X2"], p["halbzeit"], p["ecken"]
        L += ["", f"## {r['spiel']}  ·  {r['datum']} {r['anstoss']}", "",
              "| Kennzahl | " + r["heim"] + " | " + r["gast"] + " |", "|---|---|---|",
              f"| Form (letzte 5) | {m['h_serie'] or '–'} ({_num(m['h_ppg5'], 1)} P./Spiel) | "
              f"{m['a_serie'] or '–'} ({_num(m['a_ppg5'], 1)} P./Spiel) |",
              f"| Tore / Gegentore (letzte 10) | {_num(m['h_gf10'])} / {_num(m['h_ga10'])} | "
              f"{_num(m['a_gf10'])} / {_num(m['a_ga10'])} |",
              f"| Torschüsse für / gegen (Liga) | {_num(m['h_sot_f'])} / {_num(m['h_sot_a'])} | "
              f"{_num(m['a_sot_f'])} / {_num(m['a_sot_a'])} |",
              f"| Ecken für / gegen (Liga) | {_num(m['h_co_f'])} / {_num(m['h_co_a'])} | "
              f"{_num(m['a_co_f'])} / {_num(m['a_co_a'])} |",
              f"| Tore nach der Pause | {_pct(m['h_anteil2hz']) if pd.notna(m['h_anteil2hz']) else '–'} | "
              f"{_pct(m['a_anteil2hz']) if pd.notna(m['a_anteil2hz']) else '–'} |",
              f"| Elo | {_num(m['h_elo'], 0)} | {_num(m['a_elo'], 0)} |",
              f"| Torerwartung | {p['xg'][0]:.2f} | {p['xg'][1]:.2f} |", "",
              f"**Ergebnis:** Heimsieg {_pct(x['H'])} · Remis {_pct(x['D'])} · Auswärtssieg {_pct(x['A'])}  ",
              f"**Doppelte Chance:** 1X {_pct(p['DC']['1X'])} · X2 {_pct(p['DC']['X2'])} · 12 {_pct(p['DC']['12'])}  ",
              "**Wahrscheinlichste Ergebnisse:** " + " · ".join(f"{i}:{j} ({_pct(q)})" for i, j, q in p["ergebnisse"]) + "  ",
              "**Tore:** " + " · ".join(f"über {l} {_pct(p['OU'][l])}" for l in (0.5, 1.5, 2.5, 3.5, 4.5))
              + f" · beide treffen {_pct(p['BTTS'])}  ",
              f"**Halbzeiten:** Tor in der 1. HZ {_pct(hz['p_tor_1hz'])} · in der 2. HZ {_pct(hz['p_tor_2hz'])} · "
              f"mehr Tore in der 2. HZ {_pct(hz['p_mehr_2hz'])} · Halbzeitstand 1/X/2 "
              f"{_pct(hz['hz1_1X2']['H'])} / {_pct(hz['hz1_1X2']['D'])} / {_pct(hz['hz1_1X2']['A'])}  ",
              f"**Ecken:** erwartet {ec['heim']:.1f} : {ec['gast']:.1f} (gesamt {ec['gesamt']:.1f}) · "
              + " · ".join(f"über {l} {_pct(v)}" for l, v in ec["ueber"].items())
              + ("" if ec["datenbasis"] else " · _ohne Eckendaten eines Teams – Ligamittel_")]
    rep = an.report or {}
    if rep:
        o = rep.get("1X2", {})
        cl = rep.get("CL", {})
        L += ["", "## Wie gut sind diese Wahrscheinlichkeiten?", "",
              "Getestet auf Spielen, die beim Lernen nicht verwendet wurden (Log-Loss, kleiner = besser; "
              "**fett** = im Tool verwendet):", "",
              f"| Markt | CL: Torprognose | CL: Kombi | CL: Basisrate | Liga: Kombi | Liga: Torprognose | Liga: Basisrate |",
              "|---|---|---|---|---|---|---|"]
        for mk, lab in (("1X2", "Sieg/Remis/Niederlage"), ("OU2.5", "Über/Unter 2,5"), ("BTTS", "Beide treffen")):
            v, c = rep.get(mk, {}), cl.get(mk, {})
            L.append(f"| {lab} | **{c.get('torprognose')}** | {c.get('kombi')} | {c.get('basisrate')} | "
                     f"**{v.get('kombi')}** | {v.get('nur_torprognose')} | {v.get('basisrate')} |")
        L += ["", f"CL-Test: {cl.get('spiele', '?')} Spiele · Liga-Test: {rep.get('spiele_test', '?')} Spiele."]
        e = rep.get("Ecken", {})
        L += ["", f"Ecken: mittlere Abweichung {e.get('mae_kombi')} statt {e.get('mae_mittelwert')} "
                  f"mit dem bloßen Ligamittel.",
              f"Halbzeiten: {100 * rep.get('Halbzeit', {}).get('anteil_tore_2hz', 0.55):.0f} % der Tore fallen "
              "nach der Pause; teamspezifische Werte verbesserten die Prognose nicht.",
              "", "Beitrag der Kennzahlen zur 1X2-Prognose in Ligaspielen (Verbesserung des Log-Loss im Test, "
                  "> 0 = hilft):", ""]
        L += [f"- {k}: {v:+.4f}" for k, v in o.get("beitrag", {}).items()]
    L += ["", "_Wahrscheinlichkeiten sind Schätzungen, keine Gewissheiten. Ein Tipp mit 60 % geht in "
              "4 von 10 Fällen schief. Verletzungen und Aufstellungen kennt das Tool nicht._"]
    return "\n".join(L) + "\n"


def write(results, an, title: str, path: Path, euro: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(results, an, title, euro), encoding="utf-8")
