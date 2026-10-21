"""Rendite-Backtest mit echten historischen Quoten.

Quelle: xgabora/Club-Football-Match-Data-2000-2025 (Matches.csv; Spalten aus
football-data.co.uk): bet365-Quoten (OddHome/OddDraw/OddAway, Over25/Under25)
und Höchstquote aus ~17 europäischen Büchern (MaxHome…, MaxOver25…).

Ablauf je Woche: Modell nur mit Spielen *vor* dieser Woche trainieren, dann für
jedes Spiel exakt die Wettlogik des Bots anwenden (Markt = bet365 margenbereinigt,
Wettquote = Höchstquote, gleiche Filter, Kelly-Limits) und mit dem Ergebnis abrechnen.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ledger import outcome
from .markets import devig, market_probs, sharpen
from .model import DixonColes
from .names import Resolver, key
from .value import Settings, kelly

DIVISIONS = {"E0": "ENG1", "E1": "ENG2", "D1": "GER1", "D2": "GER2", "SP1": "ESP1",
             "SP2": "ESP2", "I1": "ITA1", "I2": "ITA2", "F1": "FRA1", "F2": "FRA2",
             "N1": "NED1", "P1": "POR1", "B1": "BEL1", "T1": "TUR1", "G1": "GRE1",
             "SC0": "SCO1"}

# Kürzel aus football-data.co.uk -> Schlüssel im Modell
FD_ALIASES = {
    "nott'm forest": "nottingham forest", "nottm forest": "nottingham forest",
    "man united": "manchester united", "man city": "manchester city",
    "wolves": "wolverhampton wanderers", "qpr": "queens park rangers",
    "ath madrid": "atletico madrid", "ath bilbao": "athletic", "sociedad": "real sociedad",
    "espanol": "rcd espanyol barcelona", "vallecano": "rayo vallecano madrid", "celta": "celta vigo",
    "alaves": "deportivo alaves", "mallorca": "rcd mallorca", "betis": "real betis",
    "m'gladbach": "borussia monchengladbach", "mgladbach": "borussia monchengladbach",
    "ein frankfurt": "eintracht frankfurt", "fc koln": "1 koln", "heidenheim": "1 heidenheim 1846",
    "st pauli": "st pauli 1910", "wolfsburg": "vfl wolfsburg",
    "paris sg": "paris saint germain", "st etienne": "saint etienne", "brest": "stade brestois",
    "rennes": "stade rennais", "nancy": "nancy lorraine", "laval": "stade lavallois",
    "sp lisbon": "sporting portugal", "sp braga": "braga", "az alkmaar": "az",
    "for sittard": "fortuna sittard", "nijmegen": "nec", "st truiden": "sint truidense vv",
    "st. gilloise": "union saint gilloise", "verona": "hellas verona", "mantova": "mantova 1911 ssd",
    "aris": "aris saloniki", "ofi crete": "ofi heraklion", "buyuksehyr": "istanbul basaksehir",
    "lyon": "lyonnais", "troyes": "es troyes", "west brom": "west bromwich albion",
    "sheffield weds": "sheffield wednesday", "bochum": "vfl bochum", "sp gijon": "sporting gijon",
    "santander": "real racing santander", "larisa": "ae larissa", "kifisia": "ae kifisias",
    "athens kallithea": "gs kallithea", "preußen münster": "preussen munster",
}


def load_matches(path: str, start: str) -> pd.DataFrame:
    d = pd.read_csv(path, low_memory=False)
    d = d[d["Division"].isin(DIVISIONS) & (d["MatchDate"] >= start)].copy()
    d["date"] = pd.to_datetime(d["MatchDate"])
    d["grp"] = d["Division"].map(DIVISIONS)
    return d.dropna(subset=["FTHome", "FTAway", "OddHome", "OddDraw", "OddAway",
                            "MaxHome", "MaxDraw", "MaxAway"])


def map_teams(matches: pd.DataFrame, model_df: pd.DataFrame) -> dict[tuple[str, str], str]:
    """(Liga, Name in Quotendaten) -> Teamschlüssel im Modell.

    Streng, weil eine falsche Zuordnung Schein-Value erzeugt: exakter Schlüssel,
    Alias, Wort-Teilmenge, erst dann Fuzzy (≥ 0,85) – nur Teams desselben Landes,
    und pro Liga wird kein Modellteam zweimal vergeben."""
    dom = model_df[~model_df["home_grp"].str.startswith("X-")]
    by_country: dict[str, set[str]] = {}
    for k, g in zip(pd.concat([dom.home_key, dom.away_key]), pd.concat([dom.home_grp, dom.away_grp])):
        by_country.setdefault(g[:3], set()).add(k)
    out = {}
    for grp, g in matches.groupby("grp"):
        keys = by_country.get(grp[:3], set())
        res = Resolver(sorted(keys))
        used: dict[str, str] = {}
        for n in sorted(set(g["HomeTeam"]) | set(g["AwayTeam"])):
            alias = FD_ALIASES.get(n.lower())
            if alias in keys:  # Alias ist eindeutig – auch für Zweitschreibweisen
                out[(grp, n)] = used.setdefault(alias, alias)
                continue
            k = key(n)
            hit = k if k in keys else None
            if hit is None:
                cands = [c for c in keys if set(k.split()) <= set(c.split())]
                hit = cands[0] if len(cands) == 1 else None
            if hit is None:
                r = res.resolve(n, cutoff=0.85)
                hit = key(r) if r else None
            if hit is None or hit in used:
                continue
            used[hit] = n
            out[(grp, n)] = hit
    return out


def run(model_df: pd.DataFrame, matches: pd.DataFrame, cfg: Settings,
        refit: str = "W", **model_kw) -> tuple[pd.DataFrame, list]:
    teams = map_teams(matches, model_df)
    unmatched = sorted({(g, n) for g, n in zip(pd.concat([matches.grp, matches.grp]),
                                               pd.concat([matches.HomeTeam, matches.AwayTeam]))
                        if (g, n) not in teams})
    matches = matches.assign(hk=[teams.get((g, n)) for g, n in zip(matches.grp, matches.HomeTeam)],
                             ak=[teams.get((g, n)) for g, n in zip(matches.grp, matches.AwayTeam)])
    matches = matches.dropna(subset=["hk", "ak"])
    bets = []
    for _, chunk in matches.groupby(matches["date"].dt.to_period(refit)):
        model = DixonColes(**model_kw).fit(model_df, as_of=chunk["date"].min())
        grp = model.params["grp"]
        day_bets = []
        for r in chunk.itertuples():
            if r.hk not in grp or r.ak not in grp:
                continue
            mp = market_probs(model.score_matrix(r.hk, r.ak, euro=False))
            mp["1X2"] = sharpen(mp["1X2"], cfg.sharpen)
            books = {"1X2": (("H", "D", "A"), (r.OddHome, r.OddDraw, r.OddAway),
                             (r.MaxHome, r.MaxDraw, r.MaxAway))}
            if not np.isnan(r.Over25) and not np.isnan(r.MaxOver25):
                books["OU2.5"] = (("O", "U"), (r.Over25, r.Under25), (r.MaxOver25, r.MaxUnder25))
            for market, (sels, ref, best) in books.items():
                fair = devig(ref)
                if np.sum(1 / np.asarray(ref)) - 1 > cfg.max_overround:
                    continue
                w = cfg.model_weight if market == "1X2" else cfg.model_weight_goals
                pm = np.array([mp[market][s] for s in sels])
                if np.max(np.abs(pm - fair)) > cfg.max_disagreement:
                    continue
                p = w * pm + (1 - w) * fair
                ev = p * np.asarray(best) - 1
                i = int(np.argmax(ev))
                o = best[i]
                if ev[i] < cfg.min_edge or pm[i] * o - 1 <= 0 or not cfg.min_odds <= o <= cfg.max_odds:
                    continue
                frac = min(kelly(p[i], o) * cfg.kelly_fraction, cfg.max_stake_pct)
                won = outcome(market, sels[i], int(r.FTHome), int(r.FTAway))
                day_bets.append(dict(date=r.date, liga=r.grp, heim=r.HomeTeam, gast=r.AwayTeam,
                                     markt=market, tipp=sels[i], quote=o, ref_quote=ref[i],
                                     p=p[i], p_modell=pm[i], p_markt=fair[i], ev=ev[i],
                                     anteil=frac, gewonnen=won))
        bets += day_bets
    return pd.DataFrame(bets), unmatched


def simulate(bets: pd.DataFrame, bankroll: float = 1000.0, cfg: Settings | None = None) -> pd.DataFrame:
    """Bankroll-Verlauf: Einsätze als Anteil der *aktuellen* Bankroll, Tageslimit wie im Bot."""
    cfg = cfg or Settings()
    b = bets.sort_values("date").copy()
    bank, rows = bankroll, []
    for d, g in b.groupby("date"):
        frac = g["anteil"].to_numpy()
        if frac.sum() > cfg.max_day_pct:
            frac = frac * cfg.max_day_pct / frac.sum()
        stake = frac * bank
        pnl = np.where(g["gewonnen"], stake * (g["quote"] - 1), -stake)
        bank += pnl.sum()
        rows.append(dict(date=d, wetten=len(g), einsatz=stake.sum(), gewinn=pnl.sum(), bankroll=bank))
    return pd.DataFrame(rows)


def summary(bets: pd.DataFrame) -> dict:
    """Kennzahlen bei flachem Einsatz (1 Einheit) – unabhängig von Kelly-Pfadabhängigkeit."""
    if bets.empty:
        return {"wetten": 0}
    pnl = np.where(bets["gewonnen"], bets["quote"] - 1, -1.0)
    # Bootstrap: wie sicher ist ROI > 0?
    rng = np.random.default_rng(0)
    boots = rng.choice(pnl, (2000, len(pnl))).mean(axis=1)
    return {
        "wetten": int(len(bets)),
        "trefferquote": round(float(bets["gewonnen"].mean()), 3),
        "mittl_quote": round(float(bets["quote"].mean()), 2),
        "roi_flat": round(float(pnl.mean()), 4),
        "roi_95%_intervall": [round(float(np.percentile(boots, 2.5)), 4),
                              round(float(np.percentile(boots, 97.5)), 4)],
        "p_roi_positiv": round(float((boots > 0).mean()), 3),
        "erwarteter_roi": round(float(bets["ev"].mean()), 4),
    }
