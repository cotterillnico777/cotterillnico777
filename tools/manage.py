"""Überwacht einen offenen Papier-Trade bis Stop, Ziel oder Glattstellen.

    python3 tools/manage.py SYMBOL buy|sell STOP TARGET HH:MM [FLAT_HH:MM]
HH:MM = Schlusszeit der Einstiegskerze (New York). Prüft alle 30 s die
fertigen 5-Minuten-Kerzen danach. Vorsichtig: Stop und Ziel in derselben
Kerze zählen als Stop; Stop-Füllung zum Stop-Kurs oder schlechter (Eröffnung
jenseits des Stops), Ziel zum Zielkurs. Druckt eine Zeile und endet.
"""
import datetime
import json
import sys
import time
import urllib.request
import zoneinfo

NY = zoneinfo.ZoneInfo("America/New_York")
sym, side, stop, tgt, after = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
flat = sys.argv[6] if len(sys.argv) > 6 else "15:55"
long = side == "buy"
AFTER = datetime.time(*map(int, after.split(":")))
FLAT = datetime.time(*map(int, flat.split(":")))
last = None
while True:
    now = datetime.datetime.now(NY)
    try:
        req = urllib.request.Request("https://query2.finance.yahoo.com/v8/finance/chart/%s?interval=5m&range=1d" % sym,
                                     headers={"User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=20))["chart"]["result"][0]
        q = d["indicators"]["quote"][0]
        last = d["meta"]["regularMarketPrice"]
        for t, o, h, l, c in zip(d["timestamp"], q["open"], q["high"], q["low"], q["close"]):
            st = datetime.datetime.fromtimestamp(t, NY)
            if None in (o, h, l, c) or st.time() < AFTER or st + datetime.timedelta(minutes=5) > now:
                continue
            bar = "bar %s o%.2f h%.2f l%.2f c%.2f" % (st.strftime("%H:%M"), o, h, l, c)
            hit_stop = l <= stop if long else h >= stop
            hit_tgt = h >= tgt if long else l <= tgt
            if hit_stop:
                fill = min(stop, o) if long else max(stop, o)
                print("STOP %s fill %.2f" % (bar, fill), flush=True)
                raise SystemExit
            if hit_tgt:
                print("TARGET %s fill %.2f" % (bar, tgt), flush=True)
                raise SystemExit
    except SystemExit:
        break
    except Exception as e:
        print("fetch error", e, flush=True)
    if now.time() >= FLAT:
        print("FLAT %s last %s" % (now.strftime("%H:%M:%S"), last), flush=True)
        break
    time.sleep(30)
