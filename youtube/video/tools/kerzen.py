"""Lädt die 5-Minuten-Kerzen (9:30–16:00 New York) der Trade-Tage von Yahoo
und speichert sie als youtube/video/daten/kerzen.json für die Szenen.
Yahoo liefert 5-Minuten-Daten nur für die letzten 60 Tage."""
import datetime, json, os, urllib.request
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
TRADES = [("MRK", "2026-11-04"), ("KDP", "2026-11-05"), ("NKE", "2026-11-06"),
          ("MRNA", "2026-11-09"), ("FTNT", "2026-11-09"), ("NXPI", "2026-11-10"),
          ("PANW", "2026-11-10"), ("CBOE", "2026-11-11"), ("AAPL", "2026-11-11"),
          ("GIS", "2026-11-10")]

def load(sym, day):
    d = datetime.date.fromisoformat(day)
    p1 = int(datetime.datetime(d.year, d.month, d.day, 9, 0, tzinfo=NY).timestamp())
    p2 = int(datetime.datetime(d.year, d.month, d.day, 16, 30, tzinfo=NY).timestamp())
    url = (f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?interval=5m&period1={p1}&period2={p2}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    res = json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    bars = []
    for i, ts in enumerate(res["timestamp"]):
        t = datetime.datetime.fromtimestamp(ts, NY)
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c) or not (datetime.time(9, 30) <= t.time() < datetime.time(16, 0)):
            continue
        bars.append([t.strftime("%H:%M"), round(o, 4), round(h, 4), round(l, 4), round(c, 4)])
    return bars

out = {}
for sym, day in TRADES:
    out[f"{sym}_{day}"] = load(sym, day)
    print(sym, day, len(out[f"{sym}_{day}"]), "Kerzen")
os.makedirs(os.path.join(os.path.dirname(__file__), "..", "daten"), exist_ok=True)
with open(os.path.join(os.path.dirname(__file__), "..", "daten", "kerzen.json"), "w") as f:
    json.dump(out, f)
with open(os.path.join(os.path.dirname(__file__), "..", "daten", "kerzen.js"), "w") as f:
    f.write("window.KERZEN=" + json.dumps(out) + ";\n")
