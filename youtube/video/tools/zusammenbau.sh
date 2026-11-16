#!/bin/bash
# Hängt alle Szenen in Video-Reihenfolge zu ausgabe/probevideo.mp4 zusammen.
set -e
cd "$(dirname "$0")/../ausgabe"
REIHE="hook regeln timemachine tag1 merck kdp nke kosten mrna ftnt nxpi panw gis cboe aapl bilanz lehren abstimmung"
: > liste.txt
for n in $REIHE; do [ -f "$n.mp4" ] || { echo "fehlt: $n.mp4"; exit 1; }; echo "file '$n.mp4'" >> liste.txt; done
ffmpeg -y -loglevel error -f concat -safe 0 -i liste.txt -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart probevideo.mp4
rm liste.txt
ffprobe -v error -show_entries format=duration -of csv=p=0 probevideo.mp4
