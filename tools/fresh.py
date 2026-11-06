"""Frische Kurse für Scan-Treffer: hält der Ausbruch noch, und passt er zu den Regeln?

    python3 tools/fresh.py [MIN_BAR] [--short FILE]   # Long: trader/watchlist.json
Ausgabe je Zeile: Uhrzeit, Ticker, Kurs, Abstand zur Marke, Stop (Mitte der
Spanne), Risiko/Aktie, Stück (max. 10 $ Verlust, max. 900 $), Einsatz,
max. Verlust, Dollar-Volumen heute.
"""
import json
import sys
import time
import urllib.request

args = sys.argv[1:]
short = "--short" in args
if short:
    i = args.index("--short")
    path = args[i + 1]
    del args[i:i + 2]
else:
    path = "trader/watchlist.json"
minbar = int(args[0]) if args else 0
doc = json.load(open(path))
hits = doc["hits"]
out = []
for x in hits:
    if x["bar_index"] < minbar:
        continue
    s = x["symbol"]
    try:
        req = urllib.request.Request("https://query2.finance.yahoo.com/v8/finance/chart/%s?interval=5m&range=1d" % s,
                                     headers={"User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=20))["chart"]["result"][0]
    except Exception:
        continue
    q = d["indicators"]["quote"][0]
    p = d["meta"]["regularMarketPrice"]
    hi, lo = x["or_high"], x["or_low"]
    mid = (hi + lo) / 2
    if short:
        if p >= lo:
            continue
        r = mid - p
        over = 100 * (1 - p / lo)
    else:
        if p <= hi:
            continue
        r = p - mid
        over = 100 * (p / hi - 1)
    if r <= 0:
        continue
    n = int(min(10 / r, 900 / p))
    if n < 1:
        continue
    vol = sum(v for v in q["volume"] if v)
    out.append((x["at"], s, p, over, mid, r, n, n * p, n * r, vol * p / 1e6))
    time.sleep(0.2)
for o in sorted(out, key=lambda o: o[3]):
    print("%8s %-5s $%8.2f beyond %5.2f%% stop %8.2f risk %5.2f -> %3d sh $%5.0f maxloss $%5.2f  $vol %6.0fM" % o)
