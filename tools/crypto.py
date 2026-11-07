"""Krypto-Schatten-Depot: Opening-Range-Breakout ab 9:30 Uhr New York.

    python3 tools/crypto.py scan [--now "YYYY-MM-DD HH:MM"]   # Ausbrüche + Time Machine (1R/2R)
    python3 tools/crypto.py fill SYM buy|sell QTY PRICE [HH:MM]
        ohne offene Position eröffnet buy einen Long, sell einen Short;
        mit offener Position schließt die Gegenseite sie
    python3 tools/crypto.py status

Regeln wie bei den Aktien: Spanne 9:30 bis 9:45 Uhr New York (drei
5-Minuten-Kerzen), Long auf der ersten fertigen Kerze, die über dem Hoch
der Spanne schließt, Short auf der ersten, die unter dem Tief schließt.
Stop in der Mitte der Spanne (Long abgerundet, Short aufgerundet), Ziel 1R
oder 2R. Menge in Bruchteilen: min(10 $ / Risiko, 900 $ / Kurs, Bargeld
nach 10 % Reserve). Max. 3 Trades und 30 $ Verlust pro Tag, Einstiege 9:45
bis 15:30 Uhr, glatt um 15:55 Uhr. Long und Short, nur Spielgeld.
Stop mindestens 0,2 % vom Einstieg entfernt (sonst frisst ihn der Spread).
Ein Short bindet Bargeld wie ein Long (Sicherheit = Menge × Kurs).
Depot: trader/crypto-portfolio.json. Kein Broker, keine echten Orders.
"""
import datetime
import json
import math
import os
import subprocess
import sys
import urllib.request
import zoneinfo

NY = zoneinfo.ZoneInfo("America/New_York")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
TM = os.path.join(ROOT, ".claude", "skills", "trader-timemachine", "timemachine.py")
BOOK = os.path.join(ROOT, "trader", "crypto-portfolio.json")
COINS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "LINK-USD", "AVAX-USD", "LTC-USD", "BCH-USD"]
MAX_LOSS, MAX_POS, BUFFER = 10.0, 900.0, 0.10
MAX_TRADES, MAX_DAY_LOSS = 3, 30.0
MIN_RISK_PCT = 0.2  # Stop mindestens 0,2 % vom Einstieg entfernt


def load_book():
    if os.path.exists(BOOK):
        return json.load(open(BOOK))
    return {"start": 1000.0, "cash": 1000.0, "positions": [], "trades": []}


def save_book(b):
    with open(BOOK, "w") as f:
        json.dump(b, f, indent=2)
        f.write("\n")


def bars_today(sym, now):
    u = "https://query2.finance.yahoo.com/v8/finance/chart/%s?interval=5m&range=5d" % sym
    r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}),
                                         timeout=20))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    out = []
    for t, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]):
        st = datetime.datetime.fromtimestamp(t, NY)
        if None in (o, h, l, c) or t % 300 or st.date() != now.date():
            continue
        if st.time() < datetime.time(9, 30) or st + datetime.timedelta(minutes=5) > now:
            continue
        out.append({"st": st, "o": o, "h": h, "l": l, "c": c})
    return out, r["meta"]["regularMarketPrice"]


def tm(sym, day, entry, stop, target, at, now=None, side="buy"):
    cmd = [sys.executable, TM, "run", "--side", side, "--symbol", sym, "--date", day, "--entry", "%.2f" % entry,
           "--stop", "%.2f" % stop, "--target", "%.2f" % target, "--entry-time", at,
           "--until", "15:55", "--stop-rule", "or_mid", "--json"]
    if now:
        cmd += ["--now", now.strftime("%Y-%m-%d %H:%M")]
    p = subprocess.run(cmd, capture_output=True, text=True)
    try:
        d = json.loads(p.stdout)
    except ValueError:
        return None, None
    mc = d.get("simulation") or d.get("mc") or {}
    hist = d.get("history") or {}
    return mc.get("avg_R"), hist.get("avg_R")


def today_stats(b, day):
    ts = [t for t in b["trades"] if t["date"] == day]
    pnl = sum(t.get("pnl", 0) for t in ts)
    opens = sum(1 for t in ts if "pnl" not in t)
    return opens, pnl


def cmd_scan(fake=None):
    now = (datetime.datetime.strptime(fake, "%Y-%m-%d %H:%M").replace(tzinfo=NY)
           if fake else datetime.datetime.now(NY))
    day = now.date().isoformat()
    b = load_book()
    buys, pnl = today_stats(b, day)
    print("Krypto-Scan %s NY | heute %d Trades, %+.2f $ | Bargeld %.2f $ | offen: %s" % (
        now.strftime("%Y-%m-%d %H:%M"), buys, pnl, b["cash"],
        ", ".join("%s %s" % (p.get("side", "long"), p["symbol"]) for p in b["positions"]) or "nichts"))
    for sym in COINS:
        try:
            bars, last = bars_today(sym, now)
            if fake:
                last = bars[-1]["c"]
        except Exception as e:
            print("%-9s Fehler %s" % (sym, e))
            continue
        if len(bars) < 4:
            print("%-9s Spanne noch nicht fertig" % sym)
            continue
        oh = max(x["h"] for x in bars[:3])
        ol = min(x["l"] for x in bars[:3])
        for long in (True, False):
            evaluate(sym, bars, last, oh, ol, long, b, day, now, fake)


def evaluate(sym, bars, last, oh, ol, long, b, day, now, fake):
    tag = "LONG " if long else "SHORT"
    mark = oh if long else ol
    hit = next((x for x in bars[3:] if (x["c"] > oh if long else x["c"] < ol)), None)
    if not hit:
        print("%-9s %s kein Ausbruch (%s %.2f, zuletzt %.2f)" % (sym, tag, "Hoch" if long else "Tief", mark, last))
        return
    mid = (oh + ol) / 2
    mid = math.floor(mid * 100) / 100 if long else math.ceil(mid * 100) / 100
    entry = last
    at = (bars[-1]["st"] + datetime.timedelta(minutes=5)).strftime("%I:%M %p")
    r = entry - mid if long else mid - entry
    hold = last > oh if long else last < ol
    line = "%-9s %s Ausbruch %s Schluss %.2f %s %.2f | jetzt %.2f %s | Stop %.2f, R %.2f" % (
        sym, tag, (hit["st"] + datetime.timedelta(minutes=5)).strftime("%H:%M"), hit["c"],
        ">" if long else "<", mark, last, "hält" if hold else "ZURÜCK", mid, r)
    if not hold or r <= 0:
        print(line)
        return
    if r < MIN_RISK_PCT / 100 * entry:
        print(line + " | Stop zu eng (unter %.1f %% vom Kurs, frisst der Spread)" % MIN_RISK_PCT)
        return
    cash_ok = b["cash"] * (1 - BUFFER)
    qty = math.floor(min(MAX_LOSS / r, MAX_POS / entry, cash_ok / entry) * 1e6) / 1e6
    res = []
    for k in (1, 2):
        tgt = round(entry + k * r if long else entry - k * r, 2)
        sim, hist = tm(sym, day, entry, mid, tgt, at, now if fake else None, "buy" if long else "sell")
        res.append("%dR Ziel %.2f: Sim %s / Rückblick %s" % (
            k, tgt, "%+.3f" % sim if sim is not None else "?", "%+.3f" % hist if hist is not None else "?"))
    print(line + " | Menge %.6f (%.2f $, max. −%.2f $)\n          " % (qty, qty * entry, qty * r) + " | ".join(res))


def cmd_fill(sym, side, qty, price, at=None):
    now = datetime.datetime.now(NY)
    b = load_book()
    qty, price = float(qty), float(price)
    t = {"date": now.date().isoformat(), "time": at or now.strftime("%H:%M"), "symbol": sym,
         "side": side, "qty": qty, "price": price}
    pos = next((p for p in b["positions"] if p["symbol"] == sym), None)
    if pos is None:
        t["action"] = "open long" if side == "buy" else "open short"
        b["cash"] = round(b["cash"] - qty * price, 2)
        b["positions"].append({"symbol": sym, "side": "long" if side == "buy" else "short",
                               "qty": qty, "entry": price, "time": t["time"]})
    else:
        dirn = 1 if pos.get("side", "long") == "long" else -1
        if (side == "sell") != (dirn == 1):
            raise SystemExit("%s ist schon %s offen: zum Schließen die Gegenseite buchen" % (sym, pos.get("side")))
        b["positions"].remove(pos)
        t["action"] = "close " + pos.get("side", "long")
        t["pnl"] = round(qty * (price - pos["entry"]) * dirn, 2)
        b["cash"] = round(b["cash"] + qty * pos["entry"] + t["pnl"], 2)
    b["trades"].append(t)
    save_book(b)
    print("Gebucht: %s (%s) %.6f %s zu %.2f $ | Bargeld %.2f $%s" % (
        t["action"], side, qty, sym, price, b["cash"], " | Ergebnis %+.2f $" % t["pnl"] if "pnl" in t else ""))


def cmd_status():
    b = load_book()
    print(json.dumps(b, indent=2))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "scan":
        cmd_scan(a[2] if len(a) > 2 and a[1] == "--now" else None)
    elif a[0] == "fill":
        cmd_fill(*a[1:])
    elif a[0] == "status":
        cmd_status()
    else:
        print(__doc__)
