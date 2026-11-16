#!/bin/bash
# Rendert alle Szenen neu und setzt das Probevideo zusammen.
cd "$(dirname "$0")/.."
for s in hook:24 regeln:29 timemachine:22 tag1:22 merck:24 kdp:22 nke:18 kosten:30 mrna:22 ftnt:18 nxpi:18 panw:20 gis:20 cboe:18 aapl:17 bilanz:31.5 lehren:27 abstimmung:28; do
  n=${s%%:*}; w=in,out; [ $n = hook ] && w=out; [ $n = abstimmung ] && w=in
  WIPE=$w node tools/render.js szenen/$n.html ${s##*:} ausgabe/$n.mp4 >/dev/null 2>&1 || echo "FEHLER $n"
done
tools/zusammenbau.sh
