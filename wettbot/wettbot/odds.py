"""Quoten laden: aus CSV (manuell gepflegt) oder live über The Odds API.

CSV-Format (eine Zeile pro Quote):
    date,kickoff,home,away,market,selection,odds,bookmaker
    2026-10-21,21:00,Bayern Munich,Arsenal,1X2,H,2.25,LetsBetMD

market/selection: 1X2 (H/D/A), OU1.5|OU2.5|OU3.5 (O/U), BTTS (Y/N).
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ODDS_COLUMNS = ["date", "kickoff", "home", "away", "market", "selection", "odds", "bookmaker"]
API = "https://api.the-odds-api.com/v4/sports/soccer_uefa_champs_league/odds"
TZ = ZoneInfo("Europe/Berlin")


def load_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, comment="#", dtype={"kickoff": str})
    missing = set(ODDS_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{path}: Spalten fehlen: {sorted(missing)}")
    df["odds"] = df["odds"].astype(float)
    if (df["odds"] <= 1.0).any():
        raise ValueError(f"{path}: Quoten müssen Dezimalquoten > 1 sein")
    return df[ODDS_COLUMNS]


def fetch_odds_api(api_key: str | None = None, regions: str = "eu,uk") -> pd.DataFrame:
    """Live-Quoten für die Champions League (kostenloser Key: the-odds-api.com)."""
    api_key = api_key or os.environ.get("ODDS_API_KEY")
    if not api_key:
        raise SystemExit("ODDS_API_KEY fehlt (kostenlos auf https://the-odds-api.com)")
    q = urllib.parse.urlencode(dict(apiKey=api_key, regions=regions, markets="h2h,totals",
                                    oddsFormat="decimal"))
    with urllib.request.urlopen(f"{API}?{q}", timeout=30) as r:
        events = json.load(r)
    rows = []
    for ev in events:
        ko = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(TZ)
        home, away = ev["home_team"], ev["away_team"]
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                for o in mk["outcomes"]:
                    if mk["key"] == "h2h":
                        sel = "H" if o["name"] == home else "A" if o["name"] == away else "D"
                        market = "1X2"
                    elif mk["key"] == "totals" and o.get("point") in (1.5, 2.5, 3.5):
                        sel = "O" if o["name"] == "Over" else "U"
                        market = f"OU{o['point']}"
                    else:
                        continue
                    rows.append((ko.date().isoformat(), ko.strftime("%H:%M"), home, away,
                                 market, sel, float(o["price"]), bk["title"]))
    return pd.DataFrame(rows, columns=ODDS_COLUMNS)


def now_berlin() -> datetime:
    return datetime.now(timezone.utc).astimezone(TZ)
