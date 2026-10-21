"""Teamnamen vereinheitlichen.

openfootball, Buchmacher und Quoten-APIs schreiben Vereine unterschiedlich
("FC Bayern München", "Bayern Munich", "Bayern"). Alles wird auf einen
kanonischen Schlüssel reduziert; Sonderfälle stehen in ALIASES.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

# Füllwörter, die beim Vergleich ignoriert werden.
_STOP = {
    "fc", "cf", "sc", "sk", "ac", "afc", "kv", "ssc", "bc", "fk", "cd", "ud",
    "sv", "as", "ss", "us", "osc", "rc", "club", "clube", "de", "da", "do",
    "calcio", "balompie", "futbol", "1907", "1909", "1913", "1899", "1901",
    "04", "05", "07", "29", "royale", "royal", "the", "and", "pae", "sfp",
    "cp", "rotterdam", "milano", "linz", "olympique",
}

# Schlüssel -> kanonischer Schlüssel (nach Normalisierung beider Seiten).
ALIASES = {
    "inter": "internazionale",
    "inter milan": "internazionale",
    "internazionale": "internazionale",
    "bayern munich": "bayern munchen",
    "bayern": "bayern munchen",
    "man united": "manchester united",
    "man utd": "manchester united",
    "manchester utd": "manchester united",
    "man city": "manchester city",
    "atletico madrid": "atletico madrid",
    "club atletico madrid": "atletico madrid",
    "atletico": "atletico madrid",
    "atl madrid": "atletico madrid",
    "sporting": "sporting portugal",
    "sporting lisbon": "sporting portugal",
    "sporting portugal": "sporting portugal",
    "sporting braga": "braga",
    "betis": "real betis",
    "real betis": "real betis",
    "leipzig": "rb leipzig",
    "rb leipzig": "rb leipzig",
    "rasenballsport leipzig": "rb leipzig",
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "paris saint germain": "paris saint germain",
    "barca": "barcelona",
    "benfica": "sport lisboa e benfica",
    "sl benfica": "sport lisboa e benfica",
    "sport lisboa e benfica": "sport lisboa e benfica",
    "red bull salzburg": "rb salzburg",
    "salzburg": "rb salzburg",
    "olympiakos": "olympiakos piraeus",
    "olympiacos": "olympiakos piraeus",
    "olympiakos piraeus": "olympiakos piraeus",
    "gnk dinamo zagreb": "dinamo zagreb",
    "copenhagen": "kobenhavn",
    "qarabag": "qarabag agdam",
    "young boys": "bsc young boys",
    "red star belgrade": "crvena zvezda",
    "marseille": "marseille",
    "galatasaray": "galatasaray",
    "lask": "lask",
    "lask linz": "lask",
    "brugge": "brugge",
    "club brugge": "brugge",
    "lens": "lens",
    "racing lens": "lens",
    "lille": "lille",
    "como": "como",
    "shakhtar": "shakhtar donetsk",
    "shakhtar donetsk": "shakhtar donetsk",
    "viking": "viking",
    "viking fk": "viking",
    "bodo glimt": "bodo glimt",
    "bodo/glimt": "bodo glimt",
    "slavia prague": "slavia praha",
    "slavia praha": "slavia praha",
    "slovan bratislava": "slovan bratislava",
    "aek": "aek athens",
    "aek athens": "aek athens",
    "aek athen": "aek athens",
    "aek athens fc": "aek athens",
    "fenerbahce": "fenerbahce",
    "psv eindhoven": "psv",
    "psv": "psv",
    "feyenoord": "feyenoord",
    "union saint gilloise": "union saint gilloise",
    "union sg": "union saint gilloise",
    "dortmund": "borussia dortmund",
    "bvb": "borussia dortmund",
    "stuttgart": "vfb stuttgart",
    "vfb stuttgart": "vfb stuttgart",
    "leverkusen": "bayer leverkusen",
    "bayer leverkusen": "bayer leverkusen",
    "napoli": "napoli",
    "roma": "roma",
    "villa": "aston villa",
    "sabah": "sabah",
    "sabah fk": "sabah",
    "porto": "porto",
    "real madrid": "real madrid",
    "arsenal": "arsenal",
    "liverpool": "liverpool",
    "villarreal": "villarreal",
}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ø", "o").replace("Ø", "o").replace("ı", "i").replace("ß", "ss")
    return s.lower()


def key(name: str) -> str:
    """Kanonischer Vergleichsschlüssel für einen Vereinsnamen."""
    s = re.sub(r"\s*\([A-Z]{2,4}\)\s*$", "", name.strip())  # "(ENG)" am Ende
    s = _fold(s)
    s = re.sub(r"[^a-z0-9/ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s in ALIASES:
        return ALIASES[s]
    toks = [t for t in s.replace("/", " ").split() if t not in _STOP]
    s2 = " ".join(toks) or s
    return ALIASES.get(s2, s2)


class Resolver:
    """Ordnet beliebige Schreibweisen bekannten Teams zu."""

    def __init__(self, known_names):
        self.by_key: dict[str, str] = {}
        for n in known_names:
            self.by_key.setdefault(key(n), n)

    def resolve(self, name: str, cutoff: float = 0.82) -> str | None:
        k = key(name)
        if k in self.by_key:
            return self.by_key[k]
        m = difflib.get_close_matches(k, self.by_key.keys(), n=1, cutoff=cutoff)
        return self.by_key[m[0]] if m else None
