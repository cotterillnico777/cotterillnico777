"""Teamprofile aus Spielstatistiken.

Quellen:
  * openfootball (data.load_all): Ergebnisse und Halbzeitstände aller Wettbewerbe
    -> Form, Tore, Torverteilung auf die Halbzeiten
  * xgabora/Club-Football-Match-Data (football-data.co.uk): Schüsse, Torschüsse,
    Ecken, Karten der nationalen Ligen; ClubElo-Ratings
"""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import RAW
from .names import Resolver, key

XG_BASE = "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data"
XG_DIR = RAW / "xg"


def fetch_xg(verbose: bool = True) -> None:
    XG_DIR.mkdir(parents=True, exist_ok=True)
    for f in ("Matches.csv", "EloRatings.csv"):
        with urllib.request.urlopen(f"{XG_BASE}/{f}", timeout=120) as r:
            (XG_DIR / f).write_bytes(r.read())
    if verbose:
        print(f"Statistikdaten geladen nach {XG_DIR}")


def load_xg_matches(start: str = "2023-07-01") -> pd.DataFrame:
    from .roi import DIVISIONS

    if not (XG_DIR / "Matches.csv").exists():
        fetch_xg()
    d = pd.read_csv(XG_DIR / "Matches.csv", low_memory=False)
    d = d[d["Division"].isin(DIVISIONS) & (d["MatchDate"] >= start)].copy()
    d["date"] = pd.to_datetime(d["MatchDate"])
    d["grp"] = d["Division"].map(DIVISIONS)
    return d.dropna(subset=["FTHome", "FTAway"]).reset_index(drop=True)


def load_elo() -> pd.DataFrame:
    if not (XG_DIR / "EloRatings.csv").exists():
        fetch_xg()
    e = pd.read_csv(XG_DIR / "EloRatings.csv")
    e["date"] = pd.to_datetime(e["date"])
    return e.sort_values("date")


def enrich(df: pd.DataFrame, xg: pd.DataFrame, xg_to_key: dict) -> pd.DataFrame:
    """Ligaergebnisse aus xgabora ergänzen, wo openfootball Lücken hat
    (z. B. Türkei/Belgien 2025/26 nur halb). Teams ohne Zuordnung behalten
    ihren eigenen Schlüssel (meist Aufsteiger)."""
    from .data import COLUMNS

    hk = [xg_to_key.get((g, n), key(n)) for g, n in zip(xg.grp, xg.HomeTeam)]
    ak = [xg_to_key.get((g, n), key(n)) for g, n in zip(xg.grp, xg.AwayTeam)]
    add = pd.DataFrame(dict(date=xg.date, home=xg.HomeTeam, away=xg.AwayTeam,
                            hg=xg.FTHome.astype(int), ag=xg.FTAway.astype(int), comp=xg.grp,
                            neutral=False, home_grp=xg.grp, away_grp=xg.grp,
                            hht=xg.HTHome, aht=xg.HTAway, home_key=hk, away_key=ak))
    # Anzeigenamen aus openfootball übernehmen, wo bekannt
    disp = dict(zip(df.home_key, df.home)) | dict(zip(df.away_key, df.away))
    add["home"] = [disp.get(k, n) for k, n in zip(add.home_key, add.home)]
    add["away"] = [disp.get(k, n) for k, n in zip(add.away_key, add.away)]
    out = pd.concat([df, add[COLUMNS + ["home_key", "away_key"]]], ignore_index=True)
    out = out.drop_duplicates(subset=["date", "home_key", "away_key"], keep="first")
    return out.sort_values("date").reset_index(drop=True)


# ------------------------------------------------------------- Teamprotokolle

def team_log_results(df: pd.DataFrame) -> pd.DataFrame:
    """Ein Eintrag pro Team und Spiel (alle Wettbewerbe, openfootball)."""
    hht = pd.to_numeric(df["hht"], errors="coerce")
    aht = pd.to_numeric(df["aht"], errors="coerce")
    home = pd.DataFrame(dict(date=df.date, team=df.home_key, opp=df.away_key, heim=True,
                             gf=df.hg, ga=df.ag, gf1=hht, ga1=aht, comp=df.comp))
    away = pd.DataFrame(dict(date=df.date, team=df.away_key, opp=df.home_key, heim=False,
                             gf=df.ag, ga=df.hg, gf1=aht, ga1=hht, comp=df.comp))
    log = pd.concat([home, away], ignore_index=True)
    log["pts"] = np.select([log.gf > log.ga, log.gf == log.ga], [3, 1], 0)
    return log.sort_values("date").reset_index(drop=True)


def team_log_stats(xg: pd.DataFrame, xg_to_key: dict) -> pd.DataFrame:
    """Ein Eintrag pro Team und Ligaspiel mit Schüssen, Ecken, Karten."""
    hk = [xg_to_key.get((g, n)) for g, n in zip(xg.grp, xg.HomeTeam)]
    ak = [xg_to_key.get((g, n)) for g, n in zip(xg.grp, xg.AwayTeam)]
    cols = dict(sh=("HomeShots", "AwayShots"), sot=("HomeTarget", "AwayTarget"),
                co=("HomeCorners", "AwayCorners"), ye=("HomeYellow", "AwayYellow"))
    parts = []
    for side, (me, op) in ((0, (hk, ak)), (1, (ak, hk))):
        p = pd.DataFrame(dict(date=xg.date, team=me, opp=op, grp=xg.grp, heim=side == 0))
        for c, (h, a) in cols.items():
            p[f"{c}_f"] = xg[h] if side == 0 else xg[a]
            p[f"{c}_a"] = xg[a] if side == 0 else xg[h]
        parts.append(p)
    log = pd.concat(parts, ignore_index=True).dropna(subset=["team"])
    return log.sort_values("date").reset_index(drop=True)


def _split(log: pd.DataFrame) -> dict:
    return {t: (g.date.to_numpy(), g.reset_index(drop=True)) for t, g in log.groupby("team")}


def _before(index: dict, team: str, as_of) -> pd.DataFrame | None:
    hit = index.get(team)
    if hit is None:
        return None
    dates, g = hit
    return g.iloc[: int(np.searchsorted(dates, np.datetime64(pd.Timestamp(as_of)), side="left"))]


@dataclass
class Profiles:
    """Schneller Zugriff auf 'Werte bis zum Datum X' je Team (nie Daten ab dem Spieltag)."""
    results: dict
    stats: dict
    elo: dict
    elo_key: dict

    @classmethod
    def build(cls, df: pd.DataFrame, xg: pd.DataFrame, elo: pd.DataFrame, xg_to_key: dict):
        # Elo-Namen -> Schlüssel: zuerst über die Quoten-Zuordnung, sonst Fuzzy im selben Land
        elo_key = {}
        for (g, n), k in xg_to_key.items():
            elo_key.setdefault(k, n)
        grp = {}
        for k, g in zip(pd.concat([df.home_key, df.away_key]), pd.concat([df.home_grp, df.away_grp])):
            grp.setdefault(k, g)
        last = elo.groupby("club").tail(1)
        by_country = {c: Resolver(list(g.club)) for c, g in last.groupby("country")}
        for k, g in grp.items():
            if k in elo_key:
                continue
            country = g[2:] if g.startswith("X-") else g[:3]
            r = by_country.get(country)
            hit = r.resolve(k, cutoff=0.75) if r else None
            if hit:
                elo_key[k] = hit
        elo_idx = {c: (g.date.to_numpy(), g.elo.to_numpy()) for c, g in elo.groupby("club")}
        return cls(_split(team_log_results(df)), _split(team_log_stats(xg, xg_to_key)), elo_idx, elo_key)

    def form(self, team: str, as_of, n: int = 5, max_age_days: int = 180) -> dict:
        g = _before(self.results, team, as_of)
        g = g.tail(n) if g is not None else pd.DataFrame()
        if len(g):
            g = g[g.date >= pd.Timestamp(as_of) - pd.Timedelta(days=max_age_days)]
        if g.empty:
            return dict(ppg=np.nan, gf=np.nan, ga=np.nan, serie="")
        serie = "".join("S" if p == 3 else "U" if p == 1 else "N" for p in g.pts)
        return dict(ppg=g.pts.mean(), gf=g.gf.mean(), ga=g.ga.mean(), serie=serie)

    def goals(self, team: str, as_of, n: int = 10) -> dict:
        all_ = _before(self.results, team, as_of)
        if all_ is None or all_.empty:
            return dict(gf=np.nan, ga=np.nan, anteil_2hz=np.nan, n_hz=0, btts=np.nan, over25=np.nan)
        g = all_.tail(n)
        h = all_.dropna(subset=["gf1"]).tail(2 * n)
        tot = (h.gf + h.ga).sum()
        second = (h.gf + h.ga - h.gf1 - h.ga1).sum()
        return dict(gf=g.gf.mean() if len(g) else np.nan, ga=g.ga.mean() if len(g) else np.nan,
                    anteil_2hz=second / tot if tot else np.nan, n_hz=len(h),
                    btts=((g.gf > 0) & (g.ga > 0)).mean() if len(g) else np.nan,
                    over25=((g.gf + g.ga) > 2.5).mean() if len(g) else np.nan)

    def shots_corners(self, team: str, as_of, n: int = 10) -> dict:
        g = _before(self.stats, team, as_of)
        g = g.dropna(subset=["co_f"]).tail(n) if g is not None else pd.DataFrame()
        if g.empty:
            return {c: np.nan for c in ("sh_f", "sh_a", "sot_f", "sot_a", "co_f", "co_a", "ye_f")} | {"n": 0}
        return {c: g[c].mean() for c in ("sh_f", "sh_a", "sot_f", "sot_a", "co_f", "co_a", "ye_f")} | {"n": len(g)}

    def elo_at(self, team: str, as_of) -> float:
        club = self.elo_key.get(team)
        if club not in self.elo:
            return np.nan
        dates, vals = self.elo[club]
        i = int(np.searchsorted(dates, np.datetime64(pd.Timestamp(as_of)), side="left"))
        return float(vals[i - 1]) if i else np.nan
