"""Time Machine + Kosten für viele Kandidaten auf einmal.

    python3 tools/fresh.py [...] | python3 tools/batch_tm.py buy|sell [MIN_DOLLAR_VOL_M]
Liest die Zeilen von fresh.py (Kurs, Stop, Risiko), rechnet 1R und 2R mit der
Time Machine (Einstieg = letzte fertige Kerze) und zieht die Kosten aus
tools/costs.py ab. Sortiert nach Netto-EV der Simulation.
"""
import datetime
import json
import os
import subprocess
import sys
import zoneinfo
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import costs  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TM = os.path.join(HERE, "..", ".claude", "skills", "trader-timemachine", "timemachine.py")
side = sys.argv[1]
minvol = float(sys.argv[2]) if len(sys.argv) > 2 else 40
now = datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York"))
m = (now.hour * 60 + now.minute) // 5 * 5
at = datetime.time(m // 60, m % 60).strftime("%I:%M %p")
rows = []
for line in sys.stdin:
    p = line.split()
    try:
        sym = p[2]
        price = float(p[4])
        stop = float(p[p.index("stop") + 1])
        risk = float(p[p.index("risk") + 1])
        vol = float(p[-1].rstrip("M"))
    except (ValueError, IndexError):
        continue
    if vol >= minvol:
        rows.append((sym, price, stop, risk))


def run(row):
    sym, price, stop, risk = row
    out = []
    for k in (1, 2):
        tgt = round(price + k * risk if side == "buy" else price - k * risk, 2)
        cmd = [sys.executable, TM, "run", "--side", side, "--symbol", sym, "--entry", "%.2f" % price,
               "--stop", "%.2f" % stop, "--target", "%.2f" % tgt, "--entry-time", at, "--until", "15:55",
               "--stop-rule", "or_mid", "--json"]
        try:
            d = json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout)
            out.append((k, tgt, d["mc"]["avg_R"], d["history"]["avg_R"]))
        except Exception:
            out.append((k, tgt, None, None))
    return row, out


res = []
with ThreadPoolExecutor(6) as ex:
    for row, out in ex.map(run, rows):
        sym, price, stop, risk = row
        c = costs.cost_r(sym, price, risk)
        for k, tgt, sim, hist in out:
            if sim is None:
                continue
            res.append((sim - c, sym, k, price, stop, tgt, risk, sim, hist, c))
res.sort(reverse=True)
print("Einstieg %s | %s | sortiert nach netto Sim" % (at, side))
for n, sym, k, price, stop, tgt, risk, sim, hist, c in res:
    print("%-6s %dR %8.2f stop %8.2f ziel %8.2f | Sim %+.3f Rück %+.3f | Kosten %.3f R | netto %+.3f / %+.3f %s" % (
        sym, k, price, stop, tgt, sim, hist if hist is not None else 0, c, n,
        (hist - c) if hist is not None else 0, "JA" if n > 0 else ""))
