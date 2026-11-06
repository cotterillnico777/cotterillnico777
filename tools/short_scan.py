"""Schatten-Shorts: Opening-Range-Breakdown-Scan (Spiegelbild von scan.py orb).

Ein Treffer ist die erste fertige 5-Minuten-Kerze, die UNTER dem Tief der
Eröffnungsspanne schließt. Nutzt scan.py unverändert und tauscht nur die
beiden Regeln aus. Schreibt nichts nach trader/watchlist.json.

    python3 tools/short_scan.py            # JSON auf stdout
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".claude", "skills", "trader-scanner"))
import scan  # noqa: E402


def orb_candidate(bars, n_range):
    low = min(b["c"] for b in bars[:n_range])
    return any(b["c"] <= low for b in bars[n_range:])


def orb_hit(bars, n_range):
    rng = bars[:n_range]
    if any(b["h"] is None or b["l"] is None for b in rng):
        return None
    oh = max(b["h"] for b in rng)
    ol = min(b["l"] for b in rng)
    for k in range(n_range, len(bars)):
        b = bars[k]
        if b["c"] < ol:
            closes_at = b["start"] + datetime.timedelta(minutes=scan.BAR_MIN)
            return {"price": round(b["c"], 2), "at": scan.clock_label(closes_at),
                    "bar_start": b["start"].strftime("%H:%M"), "bar_index": k,
                    "or_high": round(oh, 2), "or_low": round(ol, 2),
                    "pct_under": round((1 - b["c"] / ol) * 100, 2), "_t": closes_at}
    return None


scan.orb_candidate = orb_candidate
scan.orb_hit = orb_hit

if __name__ == "__main__":
    sys.exit(scan.main(["orb", "--no-write", "--json"] + sys.argv[1:]))
