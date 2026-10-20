"""Einrichtung und Verwaltung der offiziellen Prüfregeln (kompilierte Schematron-XSLT).

Die Regeln stammen aus der XRechnung-Konfiguration der KoSIT (enthält auch die EN-16931-Regeln
von CEN/TC 434). `einrichten()` übernimmt sie aus dem heruntergeladenen ZIP oder Ordner, prüft die
XRechnung-Version und legt ein Manifest mit SHA-256-Prüfsummen an. Vor jeder Prüfung wird das
Manifest gegen die Dateien abgeglichen, damit nur die eingerichteten, unveränderten Regeln
verwendet werden.
"""
import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .lizenz import datenverzeichnis
from .standards import XRECHNUNG_VERSION

PFLICHT = ("EN16931-CII-validation", "XRechnung-CII-validation")
OPTIONAL = ("EN16931-UBL-validation", "XRechnung-UBL-validation")
ENDUNGEN = (".xsl", ".xslt")


class RegelFehler(RuntimeError):
    pass


@dataclass
class Regelwerk:
    ordner: Path
    manifest: dict

    def datei(self, name: str) -> Path | None:
        for endung in ENDUNGEN:
            if (self.ordner / f"{name}{endung}").exists():
                return self.ordner / f"{name}{endung}"
        return None

    @property
    def beschreibung(self) -> dict:
        return {k: self.manifest.get(k) for k in ("quelle", "eingerichtet_am", "xrechnung_version", "dateien")}


def sha256(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


def xrechnung_version(xsl: bytes) -> str | None:
    m = re.search(rb'name="XR-MAJOR-MINOR-VERSION"\s+select="\'([0-9.]+)\'"', xsl)
    return m.group(1).decode() if m else None


def standardordner() -> Path:
    return datenverzeichnis() / "regeln"


def _kandidaten(quelle: Path) -> dict[str, bytes]:
    """Sucht die Regeldateien in einem Ordner oder ZIP, unabhängig von der Verzeichnisstruktur."""
    gesucht = {n.lower(): n for n in PFLICHT + OPTIONAL}
    gefunden: dict[str, bytes] = {}

    def nimm(pfadname: str, lesen):
        basis = Path(pfadname).name
        stamm, endung = os.path.splitext(basis)
        if endung.lower() in ENDUNGEN and stamm.lower() in gesucht:
            name = gesucht[stamm.lower()]
            if name in gefunden:
                raise RegelFehler(f"Regeldatei {name} kommt in {quelle} mehrfach vor. Bitte genau eine "
                                  f"Konfigurationsversion angeben.")
            gefunden[name] = lesen()

    if quelle.is_dir():
        for p in quelle.rglob("*"):
            if p.is_file():
                nimm(str(p), p.read_bytes)
    elif zipfile.is_zipfile(quelle):
        with zipfile.ZipFile(quelle) as z:
            for info in z.infolist():
                if not info.is_dir():
                    nimm(info.filename, lambda i=info: z.read(i))
    else:
        raise RegelFehler(f"{quelle} ist weder ein Ordner noch eine ZIP-Datei")
    return gefunden


def einrichten(quelle: Path, ziel: Path | None = None) -> Regelwerk:
    quelle, ziel = Path(quelle), Path(ziel or standardordner())
    dateien = _kandidaten(quelle)
    fehlend = [n for n in PFLICHT if n not in dateien]
    if fehlend:
        raise RegelFehler(f"In {quelle} fehlen: {', '.join(fehlend)}. Erwartet wird die XRechnung-Konfiguration "
                          f"der KoSIT (validator-configuration-xrechnung).")
    version = xrechnung_version(dateien["XRechnung-CII-validation"])
    if version != XRECHNUNG_VERSION:
        raise RegelFehler(f"Die Regeln sind für XRechnung {version or 'unbekannt'}, diese Version der "
                          f"Rechnungsbrücke erzeugt XRechnung {XRECHNUNG_VERSION}.")
    if ziel.exists():
        shutil.rmtree(ziel)
    ziel.mkdir(parents=True)
    manifest = {
        "quelle": quelle.name,
        "eingerichtet_am": datetime.now().isoformat(timespec="seconds"),
        "xrechnung_version": version,
        "dateien": {},
    }
    for name, inhalt in dateien.items():
        (ziel / f"{name}.xsl").write_bytes(inhalt)
        manifest["dateien"][f"{name}.xsl"] = sha256(inhalt)
    (ziel / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return lade(ziel)


def lade(ordner: Path) -> Regelwerk:
    """Lädt ein Regelwerk und prüft es gegen sein Manifest.

    Ordner ohne Manifest (z. B. für Entwicklung über RB_REGELN) werden akzeptiert, wenn die
    Pflichtdateien vorhanden sind und die XRechnung-Version passt; das Manifest wird dann im
    Speicher erzeugt.
    """
    ordner = Path(ordner)
    mpfad = ordner / "manifest.json"
    if mpfad.exists():
        manifest = json.loads(mpfad.read_text(encoding="utf-8"))
        for datei, soll in manifest["dateien"].items():
            pfad = ordner / datei
            if not pfad.exists() or sha256(pfad.read_bytes()) != soll:
                raise RegelFehler(f"Regeldatei {pfad} fehlt oder wurde verändert. Bitte die Regeln neu einrichten.")
        werk = Regelwerk(ordner, manifest)
    else:
        dateien = {}
        for name in PFLICHT + OPTIONAL:
            for endung in ENDUNGEN:
                if (ordner / f"{name}{endung}").exists():
                    dateien[f"{name}{endung}"] = sha256((ordner / f"{name}{endung}").read_bytes())
        werk = Regelwerk(ordner, {"quelle": str(ordner), "eingerichtet_am": None, "dateien": dateien})
    for name in PFLICHT:
        if not werk.datei(name):
            raise RegelFehler(f"Pflicht-Regeldatei {name}.xsl fehlt in {ordner}")
    version = xrechnung_version(werk.datei("XRechnung-CII-validation").read_bytes())
    if version != XRECHNUNG_VERSION:
        raise RegelFehler(f"Regeln in {ordner} sind für XRechnung {version}, erwartet {XRECHNUNG_VERSION}")
    werk.manifest["xrechnung_version"] = version
    return werk


def aktuelles_regelwerk(ordner: Path | None = None) -> Regelwerk | None:
    """Regelwerk aus Parameter, RB_REGELN oder dem Standardordner; None, wenn keines eingerichtet ist."""
    kandidat = ordner or (Path(os.environ["RB_REGELN"]) if os.environ.get("RB_REGELN") else None)
    if kandidat:
        return lade(kandidat)
    if (standardordner() / "manifest.json").exists():
        return lade(standardordner())
    return None
