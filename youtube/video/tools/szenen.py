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
 dict(name="merck", bg="grid", eyebrow="TAG 2 · MI, 04.11.", title="Merck", entrytag=("Kauf · 6 × 148,62 $", 930, 250),
      stamp=("ZIEL +7,98 $", "var(--gain)"), flash="#fff",
      cfg=dict(key="MRK_2026-11-04", day=2, showdown="ZIEL ODER STOP?", konto=1007.42, kontoVor=1000, prog=.039, progBrutto=True, progPct=["25,9 %", "22,3 %"], outcome="ZIEL", slow=dict(bar="14:25", level=147.29, up=False, label="Abstand zum Stop"), entryBar="12:35", exitBar="15:35", entry=148.62, stop=147.29, target=149.95, qty=6,
               result=7.98, yMin=145.8, yMax=150.6, yStep=1,
               timeline=[[2.4, 0], [6.3, 38], [7.4, 38], [10.8, 59], [13.6, 60], [15.4, 60], [19.6, 74], [30, 74]], tEntry=6.4, tExit=19.7,
               moments=[dict(id="m0", bar="14:25", price=148.28, color="var(--loss)", t=13.7, hold=2.3, shake=True, rot=-2, sfx="heart")],
               captions=[[.3, 2.3, "Tag 2: <b>Merck</b>"], [2.6, 6.2, "Ausbruch über die ersten 15 Minuten"],
                         ["entry", .1, 3, "Claude kauft: 6 Aktien zu <b>148,62 $</b>"], [8.4, 10.6, "Erst leicht im Plus …"],
                         ["m0", 0, 3, "… dann <b>−2,04 $</b>. Der Stop ist ganz nah."], [16, 19.5, "Letzte halbe Stunde: Sie dreht."],
                         ["exit", .1, 4.5, "Ziel erreicht: <b>+7,98 $</b>"]]),
      pops=[pop("m0", "−2,04 $ · Stop nur 0,99 $ entfernt", 520, 650, ROT)], dur=24),

 dict(name="kdp", bg="violet", eyebrow="TAG 3 · DO, 05.11.", title="Keurig Dr Pepper", size=130, entrytag=("Kauf · 24 × 37,49 $", 520, 240),
      stamp=("STOP −8,64 $", "var(--loss)"), flash="var(--loss)",
      cfg=dict(key="KDP_2026-11-05", day=3, showdown="ZIEL ODER STOP?", konto=998.21, kontoVor=1007.42, prog=.117, progBrutto=True, progPct=["5,4 %", "25,1 %"], outcome="STOP", entryBar="11:20", exitBar="12:10", entry=37.49, stop=37.13, target=38.21, qty=24,
               result=-8.64, yMin=36.6, yMax=38.4, yStep=.5, yDec=1, dimAfter=True,
               timeline=[[2.4, 0], [5.6, 23], [7, 23], [12.4, 33], [15, 33], [18.5, 78], [30, 78]], tEntry=5.7, tExit=12.5,
               moments=[dict(id="m0", bar="14:40", price=37.885, color="var(--muted)", t=18.6, hold=20, sfx="swish")],
               captions=[[.3, 2.4, "Tag 3: <b>Keurig Dr Pepper</b>"], [2.6, 5.5, "Die Time Machine sagt: klar positiv"],
                         ["entry", 0, 3.4, "Claude kauft: 24 Aktien zu <b>37,49 $</b>"], [9.6, 12.3, "45 Minuten später …"],
                         ["exit", 0, 3.6, "… Stop. <b>−8,64 $</b>"], [16.4, 21.5, "Guter Schnitt heißt nicht: guter Tag."]]),
      pops=[pop("m0", "Danach: Ziel 38,21 $ nie erreicht", 900, 300, GRAU)], dur=22),

 dict(name="nke", bg="teal", eyebrow="TAG 4 · FR, 06.11.", title="Nike", entrytag=("Kauf · 23 × 38,66 $", 330, 250),
      stamp=("GLATTGESTELLT −1,15 $", "var(--ink)"), flash=None,
      cfg=dict(key="NKE_2026-11-06", day=4, konto=996.50, kontoVor=998.21, prog=.075, progBrutto=True, outcome="GLATTGESTELLT", slow=dict(bar="10:25", level=39.42, up=True, label="Abstand zum Ziel"), entryBar="09:55", exitBar="15:50", entry=38.66, stop=38.28, target=39.42, qty=23,
               result=-1.15, yMin=37.8, yMax=39.6, yStep=.5, yDec=1, timeline=[[2.4, 0], [4.0, 6], [5.2, 6], [6.6, 11], [9.4, 12], [15.4, 77], [30, 77]], exitSfx="flat",
               moments=[dict(id="m0", bar="10:25", price=39.175, color="var(--gain)", hold=2.2, sfx="pop"),
                        dict(id="m1", bar="12:35", price=38.41, color="var(--loss)", hold=2.2, rot=-2, sfx="heart")],
               captions=[[.3, 2.4, "Tag 4: <b>Nike</b>"], ["entry", 0, 2.6, "Claude kauft: 23 Aktien zu <b>38,66 $</b>"],
                         ["m0", 0, 2.2, "Nur <b>25 Cent</b> bis zum Ziel"], ["m1", 0, 2.4, "Mittags: 13 Cent über dem Stop"],
                         ["exit", 0, 4.5, "Kein Stop, kein Ziel: <b>−1,15 $</b>"]]),
      pops=[pop("m0", "Nur 25 Cent vom Ziel", 700, 210, BLAU), pop("m1", "13 Cent über dem Stop", 900, 640, ROT)], dur=18),

 dict(name="mrna", bg="grid", eyebrow="TAG 5 · MO, 09.11.", title="Moderna", entrytag=("Kauf · 1 × 264,24 $", 330, 300),
      stamp=("ZIEL +12,06 $", "var(--gain)"), flash="#fff",
      cfg=dict(key="MRNA_2026-11-09", day=5, showdown="ZIEL ODER STOP?", konto=1008.39, kontoVor=996.50, prog=.191, outcome="ZIEL", entryBar="09:50", exitBar="11:20", entry=264.24, stop=258.21, target=276.30, qty=1,
               result=12.06, yMin=252, yMax=283, yStep=5, dimAfter=True,
               timeline=[[2.4, 0], [4.2, 5], [5.4, 5], [11.6, 23], [14.6, 23], [17.6, 78], [30, 78]], tEntry=4.3, tExit=11.7,
               moments=[dict(id="m0", bar="10:10", price=264.29, color="var(--ink)", t=7.7, hold=1.6, rot=-2, sfx="heart"),
                        dict(id="m1", bar="11:20", price=277.02, color="var(--accent)", t=12.6, hold=3, rot=2, sfx="pop")],
               captions=[[.3, 2.4, "Tag 5: <b>Moderna</b>"], [2.6, 4.2, "Der stärkste Kandidat der Woche"],
                         ["entry", .1, 3.1, "Claude kauft zu <b>264,24 $</b>. Ziel: doppeltes Risiko"], ["m0", 0, 1.7, "Kurzer Rücksetzer …"],
                         [9.6, 11.6, "… dann nur noch nach oben"], ["exit", 0, 3.8, "Ziel nach 90 Minuten: <b>+11,89 $</b> netto"],
                         [15.8, 21.5, "12,06 $ Gewinn, 17 Cent Kosten"]]),
      pops=[pop("m0", "Kurz zurück auf den Einstand", 560, 620, GRAU), pop("m1", "90 Minuten bis zum Ziel", 1060, 600, BLAU)], dur=22),

 dict(name="ftnt", bg="violet", eyebrow="TAG 5 · MO, 09.11.", title="Fortinet", entrytag=("Kauf · 4 × 122,93 $", 330, 230),
      stamp=("GLATTGESTELLT −1,88 $", "var(--ink)"), flash=None,
      cfg=dict(key="FTNT_2026-11-09", day=5, konto=1006.20, kontoVor=1008.39, prog=.012, outcome="GLATTGESTELLT", entryBar="09:55", exitBar="15:50", entry=122.93, stop=120.78, target=127.23, qty=4,
               result=-1.88, yMin=119, yMax=128, yStep=2, timeline=FLACH, exitSfx="flat",
               moments=[dict(id="m0", bar="09:55", price=122.93, color="var(--cost)", hold=3, delay=1.2, rot=-2)],
               captions=[[.3, 2.4, "Gleicher Tag: <b>Fortinet</b>"], ["m0", 0, 3, "Nur hauchdünn über der Kostengrenze"],
                         ["exit", 0, 4.5, "Ergebnis: <b>−2,19 $</b> netto"]]),
      pops=[pop("m0", "Nur +0,012 R über den Kosten", 560, 660, "background:var(--cost);color:#1a1205")], dur=18),

 dict(name="nxpi", bg="teal", eyebrow="TAG 6 · DI, 10.11.", title="NXP Semiconductors", size=120,
      entrytag=("Kauf · 1 × 260,56 $", 330, 230), stamp=("GLATTGESTELLT +1,33 $", "var(--gain)"), flash=None,
      cfg=dict(key="NXPI_2026-11-10", day=6, konto=1007.37, kontoVor=1006.20, prog=.133, outcome="GLATTGESTELLT", entryBar="09:55", exitBar="15:50", entry=260.56, stop=253.59, target=274.50, qty=1,
               result=1.33, yMin=249, yMax=277, yStep=5, timeline=FLACH, exitSfx="flat",
               moments=[dict(id="m0", bar="12:00", price=255.73, color="var(--loss)", hold=2.4, rot=-2, sfx="heart")],
               captions=[[.3, 2.4, "Tag 6: <b>NXP</b>"], ["entry", 0, 2.8, "Claudes bester Kandidat des Tages"],
                         ["m0", 0, 2.6, "Mittags fast <b>5 $</b> im Minus"], ["exit", 0, 4.5, "Am Ende doch im Plus: <b>+1,33 $</b>"]]),
      pops=[pop("m0", "Mittags −4,83 $", 760, 650, ROT)], dur=18),

 dict(name="panw", bg="grid", eyebrow="TAG 6 · DI, 10.11.", title="Palo Alto Networks", size=120,
      entrytag=("Kauf · 1 × 328,92 $", 330, 210), stamp=("STOP −7,91 $", "var(--loss)"), flash="var(--loss)",
      cfg=dict(key="PANW_2026-11-10", day=6, showdown="ZIEL ODER STOP?", konto=999.26, kontoVor=1007.37, prog=.035, outcome="STOP", entryBar="09:55", exitBar="12:20", entry=328.92, stop=321.01, target=344.74, qty=1,
               result=-7.91, yMin=314, yMax=347, yStep=5, dimAfter=True,
               timeline=[[2.4, 0], [4.0, 6], [5.2, 6], [10.2, 35], [13.0, 35], [16.0, 78], [30, 78]],
               moments=[dict(id="m0", bar="12:20", price=320.93, color="var(--loss)", hold=2.6, delay=-.2, shake=True, rot=-2),
                        dict(id="m1", bar="15:55", price=326.49, color="var(--muted)", hold=20, sfx="swish")],
               captions=[[.3, 2.4, "Dann: <b>Palo Alto</b>"], ["entry", 0, 3, "Wieder ein knapper Kandidat"],
                         ["m0", -1.8, 1.7, "12:20 Uhr: Der Markt zuckt"], ["exit", 0, 3, "Stop. <b>−8,11 $</b> netto"]]),
      pops=[pop("m0", "12:20 Uhr: kurzer Ausschlag", 700, 650, ROT), pop("m1", "Danach erholt: Schluss 326,49 $", 900, 300, GRAU)], dur=20),

 dict(name="gis", bg="violet", eyebrow="TAG 6 · SCHATTEN-SHORT", title="General Mills", side=-1,
      entrytag=("Short · 19 × 34,15 $", 330, 680), stamp=("STOP −9,31 $", "var(--loss)"), flash="var(--loss)",
      cfg=dict(key="GIS_2026-11-10", day=6, prog=.058, entryBar="09:55", exitBar="12:20", entry=34.15, stop=34.64, target=33.17, qty=19, side=-1,
               result=-9.31, yMin=32.9, yMax=35.1, yStep=.5, yDec=1, dimAfter=True,
               timeline=[[2.4, 0], [4.0, 6], [5.2, 6], [10.2, 35], [13.0, 35], [16.0, 78], [30, 78]],
               moments=[dict(id="m0", bar="12:20", price=34.68, color="var(--loss)", hold=2.6, delay=-.2, shake=True, rot=2)],
               captions=[[.3, 2.4, "Claudes Schatten-Short: <b>General Mills</b>"], ["entry", 0, 3, "Wette auf fallende Kurse, nur mitgerechnet"],
                         ["m0", -1.8, 1.7, "Dieselbe 5-Minuten-Kerze …"], ["exit", 0, 4.5, "… auch Stop. Das war <b>Rauschen</b>, kein Trend."]]),
      pops=[pop("m0", "Dieselbe Kerze: 12:20 Uhr", 640, 250, ROT)], dur=20),

 dict(name="cboe", bg="teal", eyebrow="TAG 7 · MI, 11.11.", title="Cboe Global Markets", size=120,
      entrytag=("Kauf · 1 × 369,46 $", 330, 230), stamp=("BRUTTO +0,18 $ · NETTO −0,05 $", "var(--cost)", 76), flash=None,
      cfg=dict(key="CBOE_2026-11-11", day=7, konto=999.21, kontoVor=999.26, prog=.062, outcome="GLATTGESTELLT", entryBar="09:50", exitBar="15:50", entry=369.46, stop=363.92, target=375.00, qty=1,
               result=0.18, yMin=358, yMax=377, yStep=5, exitSfx="flat",
               timeline=[[2.4, 0], [4.0, 5], [5.2, 5], [12.0, 77], [30, 77]],
               moments=[dict(id="m0", bar="10:45", price=365.28, color="var(--loss)", hold=2.2, rot=-2, sfx="heart")],
               captions=[[.3, 2.4, "Tag 7: <b>Cboe</b>"], ["entry", 0, 3, "Ziel: einmal das Risiko"],
                         ["m0", 0, 2.4, "Erst Minus, dann seitwärts"], ["exit", 0, 3.5, "Brutto +18 Cent, netto <b>−5 Cent</b>"]]),
      pops=[pop("m0", "Vormittags −4,18 $", 700, 660, ROT)], dur=18),

 dict(name="aapl", bg="grid", eyebrow="TAG 7 · MI, 11.11.", title="Apple",
      entrytag=("Kauf · 1 × 353,65 $", 330, 250), stamp=("GLATTGESTELLT +1,81 $", "var(--gain)"), flash=None,
      cfg=dict(key="AAPL_2026-11-11", day=7, showdown="RETTET APPLE DAS KONTO?", konto="?", kontoVor=999.21, prog=.043, entryBar="09:50", exitBar="15:50", entry=353.65, stop=351.38, target=358.19, qty=1,
               result=1.81, yMin=349, yMax=359, yStep=2, exitSfx="flat",
               timeline=[[2.4, 0], [4.0, 5], [5.2, 5], [12.0, 77], [30, 77]], moments=[],
               captions=[[.3, 2.4, "Letzter Trade: <b>Apple</b>"], ["entry", 0, 3, "Konto im Minus. Alles hängt an Apple."],
                         ["exit", -3, 2.8, "Kein Stop, kein Ziel …"], ["exit", 0, 4.5, "… am Ende <b>+1,59 $</b> netto"]]),
      pops=[], dur=17),
]

TPL = """<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="basis.css"><link rel="stylesheet" href="trade.css">
<div id="stage" data-bg="{bg}">
  <div id="bg"></div>
  <div id="frame"><div id="chartwrap"><svg id="chart" viewBox="0 0 1680 640"></svg></div></div>
  <div id="clock"></div>
  <div id="pnlbox"><div class="k">{pnlk}</div><div id="pnl">+0,00 $</div></div>
  <div class="pop" id="entrytag" style="left:{ex}px;top:{ey}px">{etext}</div>
  {pops}
  <div id="stamp" style="color:{scol}{sfont}">{stext}</div>
  <div id="title"><div class="eyebrow">{eyebrow}</div><div class="name"{tsize}>{title}</div></div>
  <div id="flash"{flash}></div>
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
        bg=s["bg"], scol=st[1], sfont=f";font-size:{st[2]}px" if len(st) > 2 else "", stext=st[0],
        eyebrow=s["eyebrow"], title=s["title"], tsize=f' style="font-size:{s["size"]}px"' if s.get("size") else "",
        flash=f' style="background:{s["flash"]}"' if s["flash"] else ' style="background:transparent"',
        cfg=json.dumps(s["cfg"], ensure_ascii=False))
    open(os.path.join(HERE, s["name"] + ".html"), "w").write(html)
    print(s["name"], s["dur"])
