"""Value-Erkennung und Einsatzberechnung.

Prinzip: Gewettet wird nur, wenn unsere Wahrscheinlichkeit p mal der *besten*
verfügbaren Quote deutlich über 1 liegt (positiver Erwartungswert).

p ist eine Mischung aus Modell und margenbereinigtem Markt:
    p = w · p_modell + (1 − w) · p_markt
Der Markt ist im Schnitt besser informiert als jedes einzelne Modell
(Verletzungen, Aufstellungen). Das Modell liefert die unabhängige Zweitmeinung,
Value entsteht vor allem bei Abweichung + Quotenvergleich (Line-Shopping).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .markets import MARKETS, devig, market_probs, overround
from .model import DixonColes
from .names import Resolver, key


@dataclass
class Settings:
    bankroll: float = 1000.0
    model_weight: float = 0.35     # Anteil Modell an p (1X2)
    model_weight_goals: float = 0.20  # Tormärkte: Modell im Backtest kaum besser als Basisrate
    min_edge: float = 0.03         # mind. +3 % Erwartungswert
    min_odds: float = 1.30
    max_odds: float = 8.0
    kelly_fraction: float = 0.25   # Viertel-Kelly: robuster gegen Schätzfehler
    max_stake_pct: float = 0.02    # max. 2 % der Bankroll pro Wette
    max_match_pct: float = 0.03    # max. 3 % pro Spiel (alle Märkte)
    max_day_pct: float = 0.10      # max. 10 % pro Spieltag
    max_overround: float = 0.12    # Märkte mit > 12 % Marge ignorieren
    # Weicht das Modell stark vom Markt ab, fehlt ihm meist Information (Verletzungen,
    # Rotation) – das ist kein Value, sondern ein Warnsignal.
    max_disagreement: float = 0.12
    allow_mixed: float = 0.0       # 1 = auch ohne vollständigen Quotensatz eines Buchmachers


def market_fair(odds: pd.DataFrame, market: str) -> tuple[dict | None, str]:
    """Faire Marktwahrscheinlichkeiten: Mittel über alle Buchmacher mit vollständigem
    Quotensatz. Fallback: beste Quote je Selektion (gemischt aus mehreren Büchern)."""
    sels = MARKETS[market]
    sub = odds[odds["market"] == market]
    sets = []
    for _, g in sub.groupby("bookmaker"):
        q = g.groupby("selection")["odds"].max()
        if all(s in q for s in sels):
            sets.append([q[s] for s in sels])
    src = f"{len(sets)} Buchm."
    if not sets:
        best = sub.groupby("selection")["odds"].max()
        if not all(s in best for s in sels):
            return None, "unvollständig"
        sets, src = [[best[s] for s in sels]], "gemischt"
    probs = np.mean([devig(s) for s in sets], axis=0)
    margin = float(np.mean([overround(s) for s in sets]))
    return {s: float(p) for s, p in zip(sels, probs)} | {"_margin": margin}, src


def kelly(p: float, o: float) -> float:
    return max(0.0, (p * o - 1.0) / (o - 1.0))


def find_value(model: DixonColes, odds: pd.DataFrame, known_names, cfg: Settings) -> pd.DataFrame:
    res = Resolver(known_names)
    rows = []
    for (d, ko, home, away), g in odds.groupby(["date", "kickoff", "home", "away"], sort=False):
        h, a = res.resolve(home), res.resolve(away)
        if not h or not a:
            rows.append(dict(spiel=f"{home} – {away}", hinweis="Team unbekannt"))
            continue
        hk, ak = key(h), key(a)
        mp = market_probs(model.score_matrix(hk, ak))
        lh, la = model.expected_goals(hk, ak)
        for market in g["market"].unique():
            fair, src = market_fair(g, market)
            for sel in MARKETS[market]:
                cand = g[(g["market"] == market) & (g["selection"] == sel)]
                if cand.empty:
                    continue
                best = cand.loc[cand["odds"].idxmax()]
                pm = mp[market][sel]
                row = dict(datum=d, anstoss=ko, spiel=f"{home} – {away}", heim=home, gast=away,
                           xg=f"{lh:.2f}:{la:.2f}", markt=market, tipp=sel, quote=best["odds"],
                           buchmacher=best["bookmaker"], p_modell=pm, quelle=src)
                if fair is None:
                    row.update(p_markt=np.nan, p=np.nan, ev=np.nan, ev_modell=np.nan,
                               hinweis="Marktquote unvollständig")
                elif fair["_margin"] > cfg.max_overround:
                    row.update(p_markt=fair[sel], p=np.nan, ev=np.nan, ev_modell=np.nan,
                               hinweis="Marge zu hoch")
                else:
                    w = cfg.model_weight if market == "1X2" else cfg.model_weight_goals
                    p = w * pm + (1 - w) * fair[sel]
                    row.update(p_markt=fair[sel], p=p, ev=p * best["odds"] - 1,
                               ev_modell=pm * best["odds"] - 1, hinweis="")
                rows.append(row)
    return pd.DataFrame(rows)


def select_bets(cands: pd.DataFrame, cfg: Settings) -> pd.DataFrame:
    if cands.empty or "ev_modell" not in cands:
        return cands.iloc[0:0]
    diff = (cands["p_modell"] - cands["p_markt"]).abs()
    market_diff = diff.groupby([cands["spiel"], cands["markt"]]).transform("max")
    ok = ((cands["ev"] >= cfg.min_edge) & (cands["ev_modell"] > 0)
          & cands["quote"].between(cfg.min_odds, cfg.max_odds)
          & (market_diff <= cfg.max_disagreement))
    if not cfg.allow_mixed:
        ok &= cands["quelle"] != "gemischt"
    c = cands[ok].copy()
    if c.empty:
        return c
    # Pro Spiel und Markt nur die beste Selektion (die anderen schließen sich aus)
    c = c.sort_values("ev", ascending=False).drop_duplicates(["spiel", "markt"])
    c["kelly"] = [kelly(p, o) for p, o in zip(c["p"], c["quote"])]
    c["anteil"] = np.minimum(c["kelly"] * cfg.kelly_fraction, cfg.max_stake_pct)
    # Spiel-Limit
    per_match = c.groupby("spiel")["anteil"].transform("sum")
    c["anteil"] *= np.minimum(1.0, cfg.max_match_pct / per_match)
    # Tages-Limit
    tot = c["anteil"].sum()
    if tot > cfg.max_day_pct:
        c["anteil"] *= cfg.max_day_pct / tot
    c["einsatz"] = (c["anteil"] * cfg.bankroll).round(2)
    c["erw_gewinn"] = (c["einsatz"] * c["ev"]).round(2)
    return c[c["einsatz"] >= 1.0].sort_values(["anstoss", "spiel"]).reset_index(drop=True)
