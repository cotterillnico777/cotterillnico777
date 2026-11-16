"""Erzeugt die Trade-Szenen (HTML) aus einer Liste. Jede Szene nutzt trade.js.
Aufruf: python3 tools/szenen.py   → schreibt szenen/<name>.html"""
import json, os

HERE = os.path.join(os.path.dirname(__file__), "..", "szenen")

def pop(id_, text, left, top, style):
    return f'<div class="pop" id="{id_}" style="left:{left}px;top:{top}px;{style}">{text}</div>'

GRAU = "background:var(--bg2);color:var(--ink);border:3px solid var(--line)"
ROT = "background:var(--loss);color:#fff"
BLAU = "background:var(--accent);color:#0b1622"
FLACH = [[2.4, 0], [4.0, 6], [5.2, 6], [12.0, 77], [30, 77]]   # Einstieg 9:55, Glattstellen 15:55

SZENEN = [
 dict(name="nke", eyebrow="TAG 4 · FR, 06.11.", title="Nike", entrytag=("Kauf · 23 × 38,66 $", 330, 250),
      stamp=("GLATTGESTELLT −1,15 $", "var(--ink)", None), flash=None,
      cfg=dict(key="NKE_2026-11-06", entryBar="09:55", exitBar="15:50", entry=38.66, stop=38.28, target=39.42, qty=23,
               result=-1.15, yMin=37.8, yMax=39.6, yStep=.5, yDec=1, timeline=FLACH, exitSfx="flat",
               moments=[dict(id="m0", bar="10:25", price=39.175, color="var(--gain)", hold=2.2),
                        dict(id="m1", bar="12:35", price=38.41, color="var(--loss)", hold=2.2, rot=-2)],
               captions=[[.3, 2.4, "Tag vier. Nike."], ["entry", 0, 2.6, "Gekauft um zehn Uhr: 23 Aktien zu 38,66 Dollar."],
                         ["m0", 0, 2.2, "Kurz vor halb elf: nur 25 Cent bis zum Ziel."], ["m1", 0, 2.4, "Mittags nur noch 13 Cent über dem Stop."],
                         ["exit", 0, 4.5, "Weder Stop noch Ziel. Glattgestellt um fünf vor vier: <b>minus 1,15 Dollar</b>."]]),
      pops=[pop("m0", "Nur 25 Cent vom Ziel", 700, 210, BLAU), pop("m1", "13 Cent über dem Stop", 900, 640, ROT)], dur=18),

 dict(name="ftnt", eyebrow="TAG 5 · MO, 09.11.", title="Fortinet", entrytag=("Kauf · 4 × 122,93 $", 330, 230),
      stamp=("GLATTGESTELLT −1,88 $", "var(--ink)", None), flash=None,
      cfg=dict(key="FTNT_2026-11-09", entryBar="09:55", exitBar="15:50", entry=122.93, stop=120.78, target=127.23, qty=4,
               result=-1.88, yMin=119, yMax=128, yStep=2, timeline=FLACH, exitSfx="flat",
               moments=[dict(id="m0", bar="09:55", price=122.93, color="var(--cost)", hold=3, delay=1.2, rot=-2)],
               captions=[[.3, 2.4, "Am selben Tag: Fortinet."],
                         ["m0", 0, 3, "Ein Kandidat, der nur ganz knapp über der Kostengrenze lag."],
                         ["exit", 0, 4.5, "Ergebnis: <b>minus 2,19 Dollar</b> netto."]]),
      pops=[pop("m0", "Nur +0,012 R über den Kosten", 560, 660, "background:var(--cost);color:#1a1205")], dur=18),

 dict(name="nxpi", eyebrow="TAG 6 · DI, 10.11.", title="NXP Semiconductors", size=120,
      entrytag=("Kauf · 1 × 260,56 $", 330, 230), stamp=("GLATTGESTELLT +1,33 $", "var(--gain)", None), flash=None,
      cfg=dict(key="NXPI_2026-11-10", entryBar="09:55", exitBar="15:50", entry=260.56, stop=253.59, target=274.50, qty=1,
               result=1.33, yMin=249, yMax=277, yStep=5, timeline=FLACH, exitSfx="flat",
               moments=[dict(id="m0", bar="12:00", price=255.73, color="var(--loss)", hold=2.4, rot=-2)],
               captions=[[.3, 2.4, "Tag sechs. Zuerst NXP Semiconductors."],
                         ["entry", 0, 2.8, "Der stärkste Kandidat des Tages, auch nach Kosten."],
                         ["m0", 0, 2.6, "Mittags fast 5 Dollar im Minus …"],
                         ["exit", 0, 4.5, "Am Ende doch knapp im Plus: <b>plus 1,33 Dollar</b> vor Kosten."]]),
      pops=[pop("m0", "Mittags −4,83 $", 760, 650, ROT)], dur=18),

 dict(name="panw", eyebrow="TAG 6 · DI, 10.11.", title="Palo Alto Networks", size=120,
      entrytag=("Kauf · 1 × 328,92 $", 330, 210), stamp=("STOP −7,91 $", "var(--loss)", "var(--loss)"), flash="var(--loss)",
      cfg=dict(key="PANW_2026-11-10", entryBar="09:55", exitBar="12:20", entry=328.92, stop=321.01, target=344.74, qty=1,
               result=-7.91, yMin=314, yMax=347, yStep=5, dimAfter=True,
               timeline=[[2.4, 0], [4.0, 6], [5.2, 6], [10.2, 35], [13.0, 35], [16.0, 78], [30, 78]],
               moments=[dict(id="m0", bar="12:20", price=320.93, color="var(--loss)", hold=2.6, delay=-.2, shake=True, rot=-2),
                        dict(id="m1", bar="15:55", price=326.49, color="var(--muted)", hold=20, sfx="swish")],
               captions=[[.3, 2.4, "Dann Palo Alto Networks."],
                         ["entry", 0, 3, "Wieder ein knapper Kandidat."],
                         ["m0", -1.8, 1.7, "Um zwanzig nach zwölf schlägt der Markt kurz aus."],
                         ["exit", 0, 3, "Stop. <b>Minus 8,11 Dollar</b> netto."]]),
      pops=[pop("m0", "12:20 Uhr: kurzer Ausschlag", 700, 650, ROT), pop("m1", "Danach erholt: Schluss 326,49 $", 900, 300, GRAU)], dur=20),

 dict(name="gis", eyebrow="TAG 6 · SCHATTEN-SHORT", title="General Mills", side=-1,
      entrytag=("Short · 19 × 34,15 $", 330, 680), stamp=("STOP −9,31 $", "var(--loss)", "var(--loss)"), flash="var(--loss)",
      cfg=dict(key="GIS_2026-11-10", entryBar="09:55", exitBar="12:20", entry=34.15, stop=34.64, target=33.17, qty=19, side=-1,
               result=-9.31, yMin=32.9, yMax=35.1, yStep=.5, yDec=1, dimAfter=True,
               timeline=[[2.4, 0], [4.0, 6], [5.2, 6], [10.2, 35], [13.0, 35], [16.0, 78], [30, 78]],
               moments=[dict(id="m0", bar="12:20", price=34.68, color="var(--loss)", hold=2.6, delay=-.2, shake=True, rot=2)],
               captions=[[.3, 2.4, "Und mein Schatten-Short: General Mills."],
                         ["entry", 0, 3, "Eine Wette auf fallende Kurse, nur mitgerechnet."],
                         ["m0", -1.8, 1.7, "Dieselbe Fünf-Minuten-Kerze …"],
                         ["exit", 0, 4.5, "… Stop. Long und Short gleichzeitig falsch. Das war Rauschen, kein Trend."]]),
      pops=[pop("m0", "Dieselbe Kerze: 12:20 Uhr", 640, 250, ROT)], dur=20),

 dict(name="cboe", eyebrow="TAG 7 · MI, 11.11.", title="Cboe Global Markets", size=120,
      entrytag=("Kauf · 1 × 369,46 $", 330, 230), stamp=("BRUTTO +0,18 $ · NETTO −0,05 $", "var(--cost)", None, 76), flash=None,
      cfg=dict(key="CBOE_2026-11-11", entryBar="09:50", exitBar="15:50", entry=369.46, stop=363.92, target=375.00, qty=1,
               result=0.18, yMin=358, yMax=377, yStep=5, exitSfx="flat",
               timeline=[[2.4, 0], [4.0, 5], [5.2, 5], [12.0, 77], [30, 77]],
               moments=[dict(id="m0", bar="10:45", price=365.28, color="var(--loss)", hold=2.2, rot=-2)],
               captions=[[.3, 2.4, "Tag sieben. Cboe."], ["entry", 0, 3, "Ziel: einmal das Risiko."],
                         ["m0", 0, 2.4, "Erst ins Minus, dann seitwärts bis zum Schluss."],
                         ["exit", 0, 4.5, "Brutto plus 18 Cent, netto <b>minus 5 Cent</b>. Das ganze Experiment im Kleinen."]]),
      pops=[pop("m0", "Vormittags −4,18 $", 700, 660, ROT)], dur=18),

 dict(name="aapl", eyebrow="TAG 7 · MI, 11.11.", title="Apple",
      entrytag=("Kauf · 1 × 353,65 $", 330, 250), stamp=("GLATTGESTELLT +1,81 $", "var(--gain)", None), flash=None,
      cfg=dict(key="AAPL_2026-11-11", entryBar="09:50", exitBar="15:50", entry=353.65, stop=351.38, target=358.19, qty=1,
               result=1.81, yMin=349, yMax=359, yStep=2, exitSfx="flat",
               timeline=[[2.4, 0], [4.0, 5], [5.2, 5], [12.0, 77], [30, 77]], moments=[],
               captions=[[.3, 2.4, "Und Apple."], ["entry", 0, 3, "Kauf um fünf vor zehn, Ziel: das Doppelte des Risikos."],
                         ["exit", -3, 2.8, "Weder Stop noch Ziel …"],
                         ["exit", 0, 4.5, "… glattgestellt um 15:55 Uhr: <b>plus 1,59 Dollar</b> netto."]]),
      pops=[], dur=17),
]

TPL = """<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="basis.css"><link rel="stylesheet" href="trade.css">
<div id="stage">
  <div id="bg"></div>
  <div id="frame"><div id="chartwrap"><svg id="chart" viewBox="0 0 1680 640"></svg></div></div>
  <div id="clock"></div>
  <div id="pnlbox"><div class="k">{pnlk}</div><div id="pnl">+0,00 $</div></div>
  <div class="pop" id="entrytag" style="left:{ex}px;top:{ey}px">{etext}</div>
  {pops}
  <div id="stamp" style="color:{scol}{sfont}">{stext}</div>
  <div id="title"><div class="eyebrow">{eyebrow}</div><div class="name"{tsize}>{title}</div></div>
  <div id="flash"{flash}></div>
  <div class="disclaimer">PAPIERHANDEL · KEINE ANLAGEBERATUNG</div>
  <div class="caption"></div>
</div>
<script src="basis.js"></script>
<script src="../daten/kerzen.js"></script>
<script>window.TRADE={cfg};</script>
<script src="trade.js"></script>
"""

for s in SZENEN:
    st = s["stamp"]
    html = TPL.format(
        pnlk="ERGEBNIS (SCHATTEN)" if s.get("side") == -1 else "ERGEBNIS",
        ex=s["entrytag"][1], ey=s["entrytag"][2], etext=s["entrytag"][0], pops="\n  ".join(s["pops"]),
        scol=st[1], sfont=f";font-size:{st[3]}px" if len(st) > 3 else "", stext=st[0],
        eyebrow=s["eyebrow"], title=s["title"], tsize=f' style="font-size:{s["size"]}px"' if s.get("size") else "",
        flash=f' style="background:{s["flash"]}"' if s["flash"] else ' style="background:transparent"',
        cfg=json.dumps(s["cfg"], ensure_ascii=False))
    open(os.path.join(HERE, s["name"] + ".html"), "w").write(html)
    print(s["name"], s["dur"])
