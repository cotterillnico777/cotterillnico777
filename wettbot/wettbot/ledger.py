"""Wett-Journal: platzierte Wetten speichern, abrechnen, auswerten.

Die wichtigste Kennzahl neben dem Gewinn ist der Closing Line Value (CLV):
Schlägt die genommene Quote regelmäßig die Schlussquote, ist der Vorteil echt –
auch wenn kurzfristig Pech den Kontostand drückt.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .data import DATA
from .names import key

LEDGER = DATA / "ledger.csv"
COLS = ["id", "datum", "anstoss", "heim", "gast", "markt", "tipp", "quote", "buchmacher",
        "p_modell", "p_markt", "p", "ev", "einsatz", "status", "tore_heim", "tore_gast",
        "gewinn", "schlussquote"]


def load(path: Path = LEDGER) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=COLS)
    return pd.read_csv(path, dtype={"anstoss": str})


def add(bets: pd.DataFrame, path: Path = LEDGER) -> pd.DataFrame:
    led = load(path)
    have = set(zip(led["datum"], led["heim"], led["gast"], led["markt"], led["tipp"]))
    new = bets[[(d, h, a, m, t) not in have for d, h, a, m, t in
                zip(bets["datum"], bets["heim"], bets["gast"], bets["markt"], bets["tipp"])]].copy()
    if new.empty:
        return new
    start = int(led["id"].max()) + 1 if len(led) else 1
    new["id"] = range(start, start + len(new))
    new["status"] = "offen"
    for c in COLS:
        if c not in new:
            new[c] = np.nan
    out = pd.concat([led, new[COLS]], ignore_index=True) if len(led) else new[COLS]
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return new[COLS]


def outcome(market: str, sel: str, hg: int, ag: int) -> bool:
    if market == "1X2":
        return sel == ("H" if hg > ag else "D" if hg == ag else "A")
    if market.startswith("OU"):
        over = hg + ag > float(market[2:])
        return over if sel == "O" else not over
    if market == "BTTS":
        both = hg > 0 and ag > 0
        return both if sel == "Y" else not both
    raise ValueError(market)


def settle(results: pd.DataFrame, path: Path = LEDGER) -> pd.DataFrame:
    """Offene Wetten mit Ergebnissen abrechnen (results: Spalten date, home_key, away_key, hg, ag)."""
    led = load(path)
    if led.empty:
        return led
    res = {(str(r.date.date()), r.home_key, r.away_key): (int(r.hg), int(r.ag))
           for r in results.itertuples()}
    for i, b in led[led["status"] == "offen"].iterrows():
        hit = res.get((b["datum"], key(b["heim"]), key(b["gast"])))
        if not hit:
            continue
        won = outcome(b["markt"], b["tipp"], *hit)
        led.loc[i, ["tore_heim", "tore_gast"]] = hit
        led.loc[i, "status"] = "gewonnen" if won else "verloren"
        led.loc[i, "gewinn"] = round(b["einsatz"] * (b["quote"] - 1) if won else -b["einsatz"], 2)
    led.to_csv(path, index=False)
    return led


def report(led: pd.DataFrame) -> dict:
    done = led[led["status"].isin(["gewonnen", "verloren"])]
    out = {"wetten": len(led), "abgerechnet": len(done), "offen": int((led["status"] == "offen").sum())}
    if len(done):
        out.update(einsatz=round(done["einsatz"].sum(), 2), gewinn=round(done["gewinn"].sum(), 2),
                   roi=round(done["gewinn"].sum() / done["einsatz"].sum(), 4),
                   trefferquote=round((done["status"] == "gewonnen").mean(), 3),
                   erwarteter_gewinn=round((done["einsatz"] * done["ev"]).sum(), 2))
    clv = led.dropna(subset=["schlussquote"])
    if len(clv):
        out["clv"] = round(float((clv["quote"] / clv["schlussquote"] - 1).mean()), 4)
    return out
