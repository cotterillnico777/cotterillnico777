#!/usr/bin/env bash
# Prüft erzeugte E-Rechnungen mit unabhängigen Referenzwerkzeugen:
#   veraPDF  – PDF/A-3b-Konformität der ZUGFeRD-PDFs
#   Mustang  – ZUGFeRD/Factur-X (PDF + eingebettetes XML) und XRechnung-XML
# Vor jedem Release ausführen, wenn Abhängigkeiten oder die XML-/PDF-Erzeugung geändert wurden.
#
#   werkzeuge/externe_pruefung.sh DATEI.pdf|DATEI.xml ...
#
# Voraussetzungen: Java ≥ 11, Maven. Die Werkzeuge werden beim ersten Lauf nach $RB_WERKZEUGE
# (Standard ~/.rechnungsbruecke/werkzeuge) geladen. MAVEN_SPIEGEL erlaubt einen Maven-Central-Spiegel.
set -euo pipefail

VERAPDF_VERSION=1.28.2
MUSTANG_VERSION=2.26.0
ZIEL=${RB_WERKZEUGE:-$HOME/.rechnungsbruecke/werkzeuge}
SPIEGEL=${MAVEN_SPIEGEL:-https://repo1.maven.org/maven2/}

[ $# -ge 1 ] || { echo "Aufruf: $0 DATEI.pdf|DATEI.xml ..." >&2; exit 1; }

holen() {  # holen <ordner> <groupId> <artifactId> <version>
  local ordner=$ZIEL/$1
  [ -f "$ordner/.fertig-$4" ] && return
  mkdir -p "$ordner"
  cat > "$ordner/settings.xml" <<EOF
<settings><mirrors><mirror><id>spiegel</id><mirrorOf>*</mirrorOf><url>$SPIEGEL</url></mirror></mirrors></settings>
EOF
  cat > "$ordner/pom.xml" <<EOF
<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
<groupId>rechnungsbruecke</groupId><artifactId>$1</artifactId><version>1</version>
<dependencies><dependency><groupId>$2</groupId><artifactId>$3</artifactId><version>$4</version></dependency></dependencies>
</project>
EOF
  (cd "$ordner" && mvn -q -s settings.xml -Dmaven.repo.local="$ZIEL/m2" dependency:copy-dependencies \
      -DoutputDirectory="$ordner/lib")
  touch "$ordner/.fertig-$4"
}

holen verapdf org.verapdf.apps greenfield-apps "$VERAPDF_VERSION"
holen mustang org.mustangproject Mustang-CLI "$MUSTANG_VERSION"

fehler=0
for datei in "$@"; do
  if [[ "$datei" == *.pdf ]]; then
    ergebnis=$(java -cp "$ZIEL/verapdf/lib/*" org.verapdf.apps.GreenfieldCliWrapper --flavour 3b --format text "$datei" 2>/dev/null | tail -1) || true
    echo "veraPDF $VERAPDF_VERSION: $ergebnis"
    [[ "$ergebnis" == PASS* ]] || fehler=1
  fi
  bericht=$(java -cp "$ZIEL/mustang/lib/*" org.mustangproject.commandline.Main --action validate --source "$datei" --no-notices 2>/dev/null) || true  # Mustang meldet ungültige Dateien mit Exit-Code ≠ 0
  if [[ "$(grep -c '<summary status="valid"/>' <<<"$bericht")" -ge 1 ]] && ! grep -q 'status="invalid"' <<<"$bericht"; then
    echo "Mustang $MUSTANG_VERSION: VALID $datei"
  else
    echo "Mustang $MUSTANG_VERSION: INVALID $datei"
    echo "$bericht" | grep -E "<error|<summary" || true
    fehler=1
  fi
done
exit $fehler
