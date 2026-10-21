"""Ergebnisdaten laden.

Quellen (frei, ohne API-Key):
  * openfootball/football.json  – nationale Ligen (JSON)
  * openfootball/champions-league – CL/EL/Conference League inkl. Quali (Football.TXT)
  * data/results_manual.csv      – eigene Nachträge (z. B. aktuelle CL-Spieltage,
                                   die openfootball noch nicht hat)
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"

RAW_BASE = "https://raw.githubusercontent.com/openfootball"

# Liga-Datei -> Ligagruppe für das Modell (Stärke-Offset je Gruppe).
LEAGUES = {
    "en.1": "ENG1", "en.2": "ENG2", "es.1": "ESP1", "es.2": "ESP2",
    "de.1": "GER1", "de.2": "GER2", "it.1": "ITA1", "it.2": "ITA2",
    "fr.1": "FRA1", "fr.2": "FRA2", "pt.1": "POR1", "nl.1": "NED1",
    "be.1": "BEL1", "tr.1": "TUR1", "at.1": "AUT1", "sco.1": "SCO1",
    "gr.1": "GRE1",
}
SEASONS = ["2024-25", "2025-26", "2026-27"]
EURO_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]
EURO_FILES = ["cl.txt", "clq.txt", "el.txt", "elq.txt", "conf.txt", "confq.txt"]

COLUMNS = ["date", "home", "away", "hg", "ag", "comp", "neutral", "home_grp", "away_grp",
           "hht", "aht"]  # hht/aht = Halbzeitstand (fehlt teils)


def _get(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            dest.write_bytes(r.read())
        return True
    except Exception:  # 404 = Datei existiert für diese Saison nicht
        return False


def fetch(verbose: bool = True) -> None:
    """Lädt alle Rohdaten nach data/raw (überschreibt vorhandene)."""
    n = 0
    for season in SEASONS:
        for code in LEAGUES:
            url = f"{RAW_BASE}/football.json/master/{season}/{code}.json"
            n += _get(url, RAW / "leagues" / season / f"{code}.json")
    for season in EURO_SEASONS:
        for f in EURO_FILES:
            url = f"{RAW_BASE}/champions-league/master/{season}/{f}"
            n += _get(url, RAW / "europe" / season / f)
    if verbose:
        print(f"{n} Dateien geladen nach {RAW}")
    from .stats import fetch_xg
    fetch_xg(verbose)


# ---------------------------------------------------------------- Ligen (JSON)

def _ft(m):
    s = m.get("score")
    if isinstance(s, dict):
        return s.get("ft")
    return s if isinstance(s, list) else None


def load_leagues() -> pd.DataFrame:
    rows = []
    for path in sorted((RAW / "leagues").glob("*/*.json")):
        grp = LEAGUES.get(path.stem)
        if not grp:
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        matches = d.get("matches") or [m for r in d.get("rounds", []) for m in r["matches"]]
        for m in matches:
            ft = _ft(m)
            if not ft or ft[0] is None:
                continue
            ht = m["score"].get("ht") if isinstance(m.get("score"), dict) else None
            hht, aht = (ht[0], ht[1]) if ht and ht[0] is not None else (None, None)
            rows.append((m["date"], m["team1"], m["team2"], int(ft[0]), int(ft[1]),
                         grp, False, grp, grp, hht, aht))
    return pd.DataFrame(rows, columns=COLUMNS)


# ------------------------------------------------- Europapokal (Football.TXT)

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_DAY = re.compile(r"^\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) ([A-Z][a-z]{2}) (\d{1,2})(?: (\d{4}))?\s*$")
_MATCH = re.compile(
    r"^\s+(?:\d{1,2}:\d{2}\s+)?(?P<home>.+?\([A-Z]{2,4}\))\s+v\s+(?P<away>.+?\([A-Z]{2,4}\))\s+"
    r"(?P<score>\d+-\d+)(?P<rest>.*)$")
_COUNTRY = re.compile(r"\(([A-Z]{2,4})\)\s*$")


def _ninety_minutes(score: str, rest: str) -> tuple[int, int]:
    """Ergebnis nach 90 Minuten (Verlängerung/Elfmeter verfälschen das Modell)."""
    if "a.e.t." in rest or "pen." in rest:
        m = re.search(r"\((\d+)-(\d+),", rest)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"(\d+)-(\d+) a\.e\.t\.", rest)  # "4-3 pen. 1-1 a.e.t." ohne Klammer
        if m:
            return int(m.group(1)), int(m.group(2))
    h, a = score.split("-")
    return int(h), int(a)


def _half_time(rest: str) -> tuple[int | None, int | None]:
    """'(0-2)' -> 0-2; nach Verlängerung '(3-0, 1-0)' -> zweiter Wert."""
    m = re.search(r"\((\d+)-(\d+)(?:, (\d+)-(\d+))?\)", rest)
    if not m:
        return None, None
    if m.group(3) is not None:
        return int(m.group(3)), int(m.group(4))
    return int(m.group(1)), int(m.group(2))


def parse_football_txt(text: str, season: str, comp: str) -> list[tuple]:
    y1 = int(season[:4])
    rows, cur, neutral = [], None, False
    for line in text.splitlines():
        if line.startswith("▪"):
            neutral = line.strip().endswith("Final")
            continue
        d = _DAY.match(line)
        if d:
            mon, day, yr = _MONTHS[d.group(1)], int(d.group(2)), d.group(3)
            year = int(yr) if yr else (y1 if mon >= 7 else y1 + 1)
            cur = date(year, mon, day).isoformat()
            continue
        m = _MATCH.match(line)
        if m and cur:
            hg, ag = _ninety_minutes(m.group("score"), m.group("rest"))
            hht, aht = _half_time(m.group("rest"))
            home, away = m.group("home").strip(), m.group("away").strip()
            hc = _COUNTRY.search(home).group(1)
            ac = _COUNTRY.search(away).group(1)
            rows.append((cur, home, away, hg, ag, comp, neutral, f"X-{hc}", f"X-{ac}", hht, aht))
    return rows


def load_europe() -> pd.DataFrame:
    rows = []
    for path in sorted((RAW / "europe").glob("*/*.txt")):
        comp = {"cl": "UCL", "clq": "UCLQ", "el": "UEL", "elq": "UELQ",
                "conf": "UECL", "confq": "UECLQ"}[path.stem]
        rows += parse_football_txt(path.read_text(encoding="utf-8"), path.parent.name, comp)
    return pd.DataFrame(rows, columns=COLUMNS)


def load_manual() -> pd.DataFrame:
    p = DATA / "results_manual.csv"
    if not p.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(p, comment="#")
    df["neutral"] = df.get("neutral", False)
    df["neutral"] = df["neutral"].fillna(False).astype(bool)
    df["home_grp"] = "X-" + df["home_country"]
    df["away_grp"] = "X-" + df["away_country"]
    for c in ("hht", "aht"):
        if c not in df:
            df[c] = None
    return df[COLUMNS]


def _link_euro_keys(df: pd.DataFrame) -> dict[str, str]:
    """Europapokal-Schlüssel ohne Liga-Treffer auf Ligateams desselben Landes abbilden
    ("lazio roma" -> "lazio", "rayo vallecano" -> "rayo vallecano madrid")."""
    dom = df[~df["home_grp"].str.startswith("X-")]
    by_country: dict[str, set[str]] = {}
    for k, g in zip(pd.concat([dom.home_key, dom.away_key]), pd.concat([dom.home_grp, dom.away_grp])):
        by_country.setdefault(g[:3], set()).add(k)
    known = set().union(*by_country.values()) if by_country else set()
    euro = df[df["home_grp"].str.startswith("X-")]
    mapping = {}
    for k, g in zip(pd.concat([euro.home_key, euro.away_key]), pd.concat([euro.home_grp, euro.away_grp])):
        country = g[2:]
        if k in known or k in mapping or country not in by_country:
            continue
        toks = set(k.split())
        cands = [c for c in by_country[country] if toks <= set(c.split()) or set(c.split()) <= toks]
        if len(cands) == 1:
            mapping[k] = cands[0]
    return mapping


def load_all() -> pd.DataFrame:
    """Alle Spiele, Teamnamen auf eine Schreibweise vereinheitlicht."""
    from .names import key

    if not RAW.exists():
        fetch()
    df = pd.concat([load_leagues(), load_europe(), load_manual()], ignore_index=True)
    df["home_key"] = df["home"].map(key)
    df["away_key"] = df["away"].map(key)
    link = _link_euro_keys(df)
    df["home_key"] = df["home_key"].replace(link)
    df["away_key"] = df["away_key"].replace(link)
    # Ein Anzeigename pro Schlüssel; Ligazeilen stehen vorn, ihre Schreibweise gewinnt.
    display: dict[str, str] = {}
    for h, a, hk, ak in zip(df["home"], df["away"], df["home_key"], df["away_key"]):
        display.setdefault(hk, _COUNTRY.sub("", h).strip())
        display.setdefault(ak, _COUNTRY.sub("", a).strip())
    df["home"] = df["home_key"].map(display)
    df["away"] = df["away_key"].map(display)
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date", "home_key", "away_key"])
    return df.sort_values("date").reset_index(drop=True)
