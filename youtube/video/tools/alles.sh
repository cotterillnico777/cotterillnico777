#!/bin/bash
# Rendert alle Szenen neu, setzt das Probevideo zusammen und legt die Musik darunter.
cd "$(dirname "$0")/.."
python3 tools/szenen.py >/dev/null
for s in hook:24 regeln:29 timemachine:22 tag1:22 merck:29.5 kdp:25 nke:22.5 kosten:30 mrna:25 ftnt:20 nxpi:20 panw:23 gis:20 cboe:20 aapl:22 bilanz:31.5 lehren:27 abstimmung:28; do
  n=${s%%:*}; w=in,out; [ $n = hook ] && w=out; [ $n = abstimmung ] && w=in
  WIPE=$w node tools/render.js szenen/$n.html ${s##*:} ausgabe/$n.mp4 >/dev/null 2>&1 || echo "FEHLER $n"
done
tools/zusammenbau.sh && python3 tools/musik.py
