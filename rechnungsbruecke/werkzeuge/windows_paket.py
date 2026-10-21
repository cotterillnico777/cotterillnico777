#!/usr/bin/env python3
"""Baut ein portables Windows-Paket (x64) der Rechnungsbrücke – auf jedem Betriebssystem.

  python3 werkzeuge/windows_paket.py [--ziel dist]

Ergebnis: dist/Rechnungsbruecke-<version>-windows-x64.zip mit
  python/                     offizielles CPython für Windows (NuGet-Paket „python“ der Python Software Foundation)
  python/Lib/site-packages/   Rechnungsbrücke und alle festgeschriebenen Abhängigkeiten, bereits installiert
  Rechnungsbruecke starten.cmd   startet die Oberfläche im Browser
  Rechnungsbruecke Kommandozeile.cmd   öffnet eine Eingabeaufforderung mit dem Befehl `rechnungsbruecke`
  LIESMICH.txt                Anleitung für Anwender

Auf dem Zielrechner ist keine Installation und kein Internet nötig: entpacken, Doppelklick, fertig.
Nach jedem Bau auf einem sauberen Windows-Rechner nach `vertrieb/windows_abnahme.md` prüfen.
"""
import argparse
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
PYTHON_VERSION = "3.13.16"  # muss zur Python-Version passen, mit der die Tests laufen
NUGET = f"https://api.nuget.org/v3-flatcontainer/python/{PYTHON_VERSION}/python.{PYTHON_VERSION}.nupkg"

STARTEN = r"""@echo off
rem Startet die Rechnungsbrücke im Browser. Fenster offen lassen, solange Sie arbeiten.
cd /d "%~dp0"
"%~dp0python\python.exe" -m rechnungsbruecke oberflaeche %*
if errorlevel 1 (
  echo.
  echo Die Rechnungsbruecke wurde mit einem Fehler beendet. Bitte diese Meldung an den Support senden.
  pause
)
"""
KOMMANDOZEILE = r"""@echo off
rem Eingabeaufforderung mit dem Befehl "rechnungsbruecke" (z. B. fuer Hotfolder oder Aufgabenplanung).
cd /d "%~dp0"
set "PATH=%~dp0python;%~dp0python\Scripts;%PATH%"
doskey rechnungsbruecke="%~dp0python\python.exe" -m rechnungsbruecke $*
echo Rechnungsbruecke-Kommandozeile. Beispiel: rechnungsbruecke info
cmd /k
"""
LIESMICH = """Rechnungsbrücke {version} für Windows (64 Bit)
==============================================

Starten
-------
1. Diesen Ordner an einen festen Ort entpacken, z. B. C:\\Programme\\Rechnungsbruecke
   oder in Ihr Benutzerverzeichnis. Nicht direkt aus der ZIP-Datei starten.
2. Doppelklick auf „Rechnungsbruecke starten.cmd“. Der Browser öffnet sich mit der Oberfläche.
   Das schwarze Fenster geöffnet lassen, solange Sie arbeiten; Schließen beendet die Rechnungsbrücke.
3. Beim ersten Start unter „Einstellungen“:
   - Firmendaten eintragen und speichern,
   - Prüfregeln einrichten: die XRechnung-Konfiguration der KoSIT als ZIP auswählen,
   - ggf. Lizenzdatei einspielen.

Windows-Hinweise
----------------
- Fragt die Windows-Firewall nach Netzwerkzugriff: Die Rechnungsbrücke braucht keinen Zugriff aus dem
  Netzwerk (sie lauscht nur auf 127.0.0.1). Sie können den Zugriff ablehnen.
- SmartScreen kann beim ersten Start warnen („Unbekannter Herausgeber“). Mit „Weitere Informationen“ →
  „Trotzdem ausführen“ starten. Für den Verkauf werden die Startdateien signiert.

Ihre Daten
----------
Arbeitsordner:  %USERPROFILE%\\Rechnungsbruecke   (Firmendaten, Ausgaben, Buchungsliste, Quarantäne)
Programmdaten:  %USERPROFILE%\\.rechnungsbruecke  (Prüfregeln, Lizenz, Nutzungszähler)

Enthaltene Komponenten
----------------------
Python {python} (Python Software Foundation, NuGet-Paket „python“)
{pakete}
"""


def lade(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as antwort:
        return antwort.read()


def gepinnte_abhaengigkeiten() -> list[str]:
    daten = tomllib.loads((PROJEKT / "pyproject.toml").read_text(encoding="utf-8"))
    abh = daten["project"]["dependencies"]
    if not all("==" in a for a in abh):
        raise SystemExit("Alle Abhängigkeiten müssen exakt gepinnt sein (==)")
    return abh


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ziel", type=Path, default=PROJEKT / "dist")
    args = ap.parse_args()

    version = re.search(r'__version__ = "([^"]+)"',
                        (PROJEKT / "rechnungsbruecke" / "__init__.py").read_text(encoding="utf-8")).group(1)
    name = f"Rechnungsbruecke-{version}-windows-x64"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        paket = tmp / name

        print(f"Lade Python {PYTHON_VERSION} für Windows (NuGet) …")
        nupkg = lade(NUGET)
        with zipfile.ZipFile(io.BytesIO(nupkg)) as z:
            for info in z.infolist():
                if info.filename.startswith("tools/") and not info.is_dir():
                    ziel = paket / "python" / info.filename[len("tools/"):]
                    ziel.parent.mkdir(parents=True, exist_ok=True)
                    ziel.write_bytes(z.read(info))
        if not (paket / "python" / "python.exe").exists():
            raise SystemExit("NuGet-Paket enthält kein python.exe")

        print("Baue Rechnungsbrücke-Wheel …")
        raeder = tmp / "wheels"
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", str(raeder), str(PROJEKT)],
                       check=True)
        print("Installiere Abhängigkeiten für Windows x64 / CPython 3.13 …")
        site = paket / "python" / "Lib" / "site-packages"
        py = PYTHON_VERSION.rsplit(".", 1)[0]
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--target", str(site),
                        "--platform", "win_amd64", "--python-version", py, "--implementation", "cp",
                        "--only-binary=:all:", "--upgrade", *gepinnte_abhaengigkeiten(),
                        *[str(w) for w in raeder.glob("*.whl")]], check=True)

        installiert = sorted(p.name for p in site.glob("*.dist-info"))
        (paket / "Rechnungsbruecke starten.cmd").write_text(STARTEN.replace("\n", "\r\n"), encoding="cp1252")
        (paket / "Rechnungsbruecke Kommandozeile.cmd").write_text(KOMMANDOZEILE.replace("\n", "\r\n"),
                                                                    encoding="cp1252")
        (paket / "LIESMICH.txt").write_text(
            LIESMICH.format(version=version, python=PYTHON_VERSION,
                            pakete="\n".join(re.sub(r"\.dist-info$", "", n).replace("-", " ", 1) for n in installiert)
                            ).replace("\n", "\r\n"), encoding="utf-8-sig")

        args.ziel.mkdir(parents=True, exist_ok=True)
        archiv = args.ziel / f"{name}.zip"
        if archiv.exists():
            archiv.unlink()
        shutil.make_archive(str(archiv.with_suffix("")), "zip", tmp, name)
    pruefsumme = hashlib.sha256(archiv.read_bytes()).hexdigest()
    (archiv.with_suffix(".zip.sha256")).write_text(f"{pruefsumme}  {archiv.name}\n", encoding="utf-8")
    print(f"Fertig: {archiv} ({archiv.stat().st_size / 1e6:.0f} MB), SHA-256 {pruefsumme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
