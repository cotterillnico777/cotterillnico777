#!/usr/bin/env bash
# Abnahmelauf vor einem Release bzw. vor dem ersten Produktiveinsatz.
#
#   werkzeuge/abnahme.sh <validator-configuration-xrechnung.zip>
#
# 1. richtet die übergebenen (offiziellen KoSIT-)Prüfregeln in einem frischen Datenordner ein,
# 2. führt alle automatischen Tests gegen genau diese Regeln aus,
# 3. erzeugt die Beispielrechnungen neu (XRechnung + ZUGFeRD) mit Pflichtprüfung und Prüfberichten,
# 4. prüft sie extern mit veraPDF und Mustang (werkzeuge/externe_pruefung.sh),
# 5. archiviert alles unter abnahme/<Zeitstempel>/ samt SHA-256 des Regel-ZIPs und Versionsangaben.
#
# Exit-Code 0 nur, wenn alle Schritte bestanden sind. Das Archiv ist der Nachweis für die Freigabe.
set -uo pipefail

[ $# -eq 1 ] && [ -f "$1" ] || { echo "Aufruf: $0 <validator-configuration-xrechnung.zip>" >&2; exit 1; }
QUELLE=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
PROJEKT=$(cd "$(dirname "$0")/.." && pwd)
PY=${PYTHON:-python3}
STEMPEL=$(date +%Y%m%d-%H%M%S)
ARCHIV=$PROJEKT/abnahme/$STEMPEL
mkdir -p "$ARCHIV"
export RB_DATENVERZEICHNIS=$ARCHIV/daten
cd "$PROJEKT"

ergebnis=0
schritt() {  # schritt <name> <befehl...>
  local name=$1; shift
  if "$@" > "$ARCHIV/$name.log" 2>&1; then
    echo "BESTANDEN  $name"; echo "BESTANDEN  $name" >> "$ARCHIV/zusammenfassung.txt"
  else
    echo "FEHLER     $name (siehe $ARCHIV/$name.log)"; echo "FEHLER     $name" >> "$ARCHIV/zusammenfassung.txt"
    ergebnis=1
  fi
}

{
  echo "Abnahme Rechnungsbrücke – $STEMPEL"
  echo "Regelquelle: $(basename "$QUELLE")"
  echo "SHA-256:     $(sha256sum "$QUELLE" | cut -d' ' -f1)"
  echo
} > "$ARCHIV/zusammenfassung.txt"

schritt 1_regeln_einrichten "$PY" -m rechnungsbruecke regeln-einrichten "$QUELLE"
schritt 2_info              "$PY" -m rechnungsbruecke info
RB_REGELN=$RB_DATENVERZEICHNIS/regeln \
schritt 3_tests             "$PY" -m unittest discover -v tests
schritt 4_beispiele         "$PY" -m rechnungsbruecke konvertieren rechnungsbruecke/beispiele/rechnungen.csv \
                              --stammdaten rechnungsbruecke/beispiele/stammdaten.json --ziel "$ARCHIV/ausgabe" --format beide
schritt 5_extern            werkzeuge/externe_pruefung.sh "$ARCHIV"/ausgabe/*.pdf "$ARCHIV"/ausgabe/*.xml

# Übersprungene Tests wären hier ein Fehler: Die Abnahme muss alles gegen die echten Regeln prüfen.
if grep -q "skipped" "$ARCHIV/3_tests.log"; then
  echo "FEHLER     Tests wurden übersprungen" | tee -a "$ARCHIV/zusammenfassung.txt"; ergebnis=1
fi
cp "$RB_DATENVERZEICHNIS/regeln/manifest.json" "$ARCHIV/regeln-manifest.json" 2>/dev/null || true

echo
if [ $ergebnis -eq 0 ]; then
  echo "ABNAHME BESTANDEN – Archiv: $ARCHIV" | tee -a "$ARCHIV/zusammenfassung.txt"
else
  echo "ABNAHME NICHT BESTANDEN – Archiv: $ARCHIV" | tee -a "$ARCHIV/zusammenfassung.txt"
fi
exit $ergebnis
