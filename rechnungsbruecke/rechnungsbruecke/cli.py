"""Kommandozeile der Rechnungsbrücke."""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from .csv_import import Stammdaten
from .leser import LeseFehler, lies_datei, xml_aus_datei
from .lizenz import TARIFE, LizenzFehler, Nutzung, aktuelle_lizenz
from .regeln import RegelFehler, aktuelles_regelwerk, einrichten
from .standards import PDFA, XRECHNUNG_VERSION, ZUGFERD_PROFIL
from .verarbeitung import FORMATE, hotfolder_durchlauf, konvertiere, lese_eingang

BEISPIELE = Path(__file__).resolve().parent / "beispiele"


def _mapping(pfad):
    return json.loads(Path(pfad).read_text(encoding="utf-8")) if pfad else None


def _bericht(erg, ausgabe=print) -> None:
    for p in erg.erzeugt:
        ausgabe(f"  ✓ {p}")
    for h in erg.hinweise:
        ausgabe(f"  Hinweis: {h}")
    for f in erg.fehler:
        ausgabe(f"  ✗ {f}")


def _regelwerk(a):
    werk = aktuelles_regelwerk(a.regeln)
    if werk is None and getattr(a, "ohne_offizielle_pruefung", False):
        print("WARNUNG: Offizielle Prüfung abgeschaltet. Die Rechnungen sind nicht gegen EN 16931/XRechnung "
              "geprüft und dürfen so nicht an Kunden gehen.", file=sys.stderr)
    return werk


def cmd_konvertieren(a) -> int:
    lizenz = aktuelle_lizenz(a.lizenz)
    erg = konvertiere(a.csv, Stammdaten.laden(a.stammdaten), a.ziel, lizenz, a.format, _mapping(a.mapping),
                      _regelwerk(a), ohne_offizielle_pruefung=a.ohne_offizielle_pruefung)
    _bericht(erg)
    rechnungen = len([p for p in erg.erzeugt if p.suffix in (".xml", ".pdf")]) // (2 if a.format == "beide" else 1)
    print(f"{rechnungen} Rechnung(en) erzeugt, {len(erg.fehler)} Fehler.")
    return 0 if erg.ok else 2


def cmd_ueberwachen(a) -> int:
    lizenz = aktuelle_lizenz(a.lizenz)
    stamm = Stammdaten.laden(a.stammdaten) if a.stammdaten else None
    werk = _regelwerk(a)
    a.eingang.mkdir(parents=True, exist_ok=True)
    print(f"Überwache {a.eingang} → {a.ziel} (Tarif {lizenz.tarif}). Beenden mit Strg+C.")
    while True:
        for datei, erg in hotfolder_durchlauf(a.eingang, a.ziel, stamm, lizenz, a.format, _mapping(a.mapping),
                                              werk, mindestalter_s=0 if a.einmal else 2,
                                              ohne_offizielle_pruefung=a.ohne_offizielle_pruefung):
            print(f"{'OK    ' if erg.ok else 'FEHLER'} {datei.name}")
            _bericht(erg)
        if a.einmal:
            return 0
        time.sleep(a.intervall)


def cmd_lesen(a) -> int:
    erg = lese_eingang(a.datei, a.ziel, a.buchungsliste, _regelwerk(a), a.ohne_offizielle_pruefung, a.bestaetigt)
    _bericht(erg)
    return 0 if erg.ok else 2


def cmd_pruefen(a) -> int:
    try:
        xml = xml_aus_datei(a.datei)
        r = lies_datei(a.datei)
    except (LeseFehler, ValueError) as e:
        print(f"✗ {e}")
        return 2
    print(f"{r.syntax}-Rechnung {r.nummer} von {r.verkaeufer}: {r.brutto} {r.waehrung}")
    probleme = r.plausibilitaet()
    for p in probleme:
        print(f"  ✗ {p}")
    fatal = 0
    werk = aktuelles_regelwerk(a.regeln)
    if werk:
        from .offiziell import pruefe_offiziell

        for b in pruefe_offiziell(xml, werk):
            fatal += b.schwere == "fatal"
            print(f"  {'✗' if b.schwere == 'fatal' else '!'} [{b.regel}] {b.text}")
    else:
        print("  (Nur Rechenprüfung. Für die vollständige Prüfung zuerst 'regeln-einrichten' ausführen.)")
    if not probleme and not fatal:
        print("  ✓ keine Fehler gefunden")
    return 0 if not probleme and not fatal else 2


def cmd_lizenz(a) -> int:
    lizenz = aktuelle_lizenz(a.lizenz)
    n = Nutzung(lizenz)
    print(f"Kunde: {lizenz.kunde}\nTarif: {lizenz.tarif}"
          + (f" (gültig bis {lizenz.gueltig_bis:%d.%m.%Y})" if lizenz.gueltig_bis else ""))
    print(f"Diesen Monat erzeugt: {n.verbraucht}"
          + (f" von {lizenz.limit}" if lizenz.limit else " (unbegrenzt)"))
    print("\nTarife:")
    for name, t in TARIFE.items():
        print(f"  {name:12} {t['preis_monat']:>4} €/Monat  "
              f"{t['rechnungen_monat'] or 'unbegrenzt'} Rechnungen/Monat"
              f"{'  + Hotfolder' if t['hotfolder'] else ''}")
    return 0


def cmd_regeln_einrichten(a) -> int:
    werk = einrichten(a.quelle)
    print(f"Prüfregeln eingerichtet in {werk.ordner} (XRechnung {werk.manifest['xrechnung_version']}):")
    for datei, pruefsumme in werk.manifest["dateien"].items():
        print(f"  {datei}  sha256:{pruefsumme[:16]}…")
    return 0


def cmd_info(a) -> int:
    print(f"Rechnungsbrücke {__version__}")
    print(f"Ausgabe: XRechnung {XRECHNUNG_VERSION} (CII), ZUGFeRD/Factur-X Profil {ZUGFERD_PROFIL} als {PDFA}")
    try:
        werk = aktuelles_regelwerk(a.regeln)
    except RegelFehler as e:
        print(f"Prüfregeln: FEHLER – {e}")
        return 2
    if werk:
        print(f"Prüfregeln: {werk.ordner} · Quelle {werk.manifest.get('quelle')} · eingerichtet "
              f"{werk.manifest.get('eingerichtet_am') or '–'} · XRechnung {werk.manifest['xrechnung_version']}")
    else:
        print("Prüfregeln: nicht eingerichtet (rechnungsbruecke regeln-einrichten <KoSIT-Konfiguration.zip>)")
    from .lizenz import schluessel_eingebaut

    print("Lizenzschlüssel des Anbieters: " + ("eingebaut" if schluessel_eingebaut()
                                               else "NICHT eingebaut – nur Free-Tarif nutzbar"))
    from importlib.metadata import PackageNotFoundError, version
    for paket in ("lxml", "reportlab", "pypdf", "factur-x", "pillow", "cryptography", "saxonche"):
        try:
            print(f"  {paket} {version(paket)}")
        except PackageNotFoundError:
            print(f"  {paket} nicht installiert")
    return 0


def cmd_oberflaeche(a) -> int:
    from .oberflaeche import starte

    return starte(a.ordner, a.port, browser=not a.kein_browser, ohne_offizielle_pruefung=a.ohne_offizielle_pruefung)


def cmd_beispiel(a) -> int:
    a.ziel.mkdir(parents=True, exist_ok=True)
    for f in ("stammdaten.json", "rechnungen.csv", "mapping_altsystem.json", "export_altsystem.csv"):
        shutil.copy(BEISPIELE / f, a.ziel / f)
        print(f"  {a.ziel / f}")
    print(f"Weiter mit: rechnungsbruecke konvertieren {a.ziel / 'rechnungen.csv'} "
          f"--stammdaten {a.ziel / 'stammdaten.json'} --ziel {a.ziel / 'ausgabe'}")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="rechnungsbruecke",
                                 description="CSV-Rechnungsdaten → XRechnung/ZUGFeRD, E-Rechnungen lesen und prüfen.")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--lizenz", type=Path, help="Pfad zur Lizenzdatei (Standard: ~/.rechnungsbruecke/lizenz.json)")
    sub = ap.add_subparsers(dest="befehl", required=True)

    k = sub.add_parser("konvertieren", help="CSV-Export in E-Rechnungen umwandeln")
    k.add_argument("csv", type=Path)
    k.add_argument("--stammdaten", type=Path, required=True)
    k.add_argument("--ziel", type=Path, required=True)
    k.add_argument("--format", choices=FORMATE, default="xrechnung")
    k.add_argument("--mapping", type=Path, help="JSON: Spaltennamen des Altsystems → Standardnamen")
    k.add_argument("--regeln", type=Path, help="anderer Regelordner als der eingerichtete")
    k.add_argument("--ohne-offizielle-pruefung", action="store_true", help="nur zum Testen: ohne offizielle Prüfung")
    k.set_defaults(fn=cmd_konvertieren)

    u = sub.add_parser("ueberwachen", help="Hotfolder: CSV → Ausgangsrechnungen, XML/PDF → Eingangsrechnungen")
    u.add_argument("eingang", type=Path)
    u.add_argument("--ziel", type=Path, required=True)
    u.add_argument("--stammdaten", type=Path)
    u.add_argument("--format", choices=FORMATE, default="xrechnung")
    u.add_argument("--mapping", type=Path)
    u.add_argument("--regeln", type=Path)
    u.add_argument("--ohne-offizielle-pruefung", action="store_true")
    u.add_argument("--intervall", type=int, default=30, help="Sekunden zwischen zwei Durchläufen")
    u.add_argument("--einmal", action="store_true", help="nur ein Durchlauf (z. B. für Aufgabenplanung/cron)")
    u.set_defaults(fn=cmd_ueberwachen)

    le = sub.add_parser("lesen", help="Eingehende E-Rechnung (XML/PDF) prüfen, lesbar machen und optional buchen")
    le.add_argument("datei", type=Path)
    le.add_argument("--ziel", type=Path, default=Path("."))
    le.add_argument("--buchungsliste", type=Path,
                    help="nur bei bestandener Prüfung buchen; sonst Ablage in <ziel>/quarantaene")
    le.add_argument("--bestaetigt", action="store_true", help="Dublettenverdacht bewusst bestätigen und trotzdem buchen")
    le.add_argument("--regeln", type=Path)
    le.add_argument("--ohne-offizielle-pruefung", action="store_true", help="nur zum Testen")
    le.set_defaults(fn=cmd_lesen)

    p = sub.add_parser("pruefen", help="E-Rechnung prüfen (Rechenprüfung, optional offizielle Regeln)")
    p.add_argument("datei", type=Path)
    p.add_argument("--regeln", type=Path)
    p.set_defaults(fn=cmd_pruefen)

    re_ = sub.add_parser("regeln-einrichten", help="Offizielle Prüfregeln aus der KoSIT-Konfiguration übernehmen")
    re_.add_argument("quelle", type=Path, help="ZIP oder Ordner der XRechnung-Konfiguration (KoSIT)")
    re_.set_defaults(fn=cmd_regeln_einrichten)

    inf = sub.add_parser("info", help="Versionen von Standards, Prüfregeln und Bibliotheken anzeigen")
    inf.add_argument("--regeln", type=Path)
    inf.set_defaults(fn=cmd_info)

    ob = sub.add_parser("oberflaeche", help="Grafische Oberfläche im Browser starten")
    ob.add_argument("--ordner", type=Path, default=Path.home() / "Rechnungsbruecke", help="Arbeitsordner")
    ob.add_argument("--port", type=int, default=8765)
    ob.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch öffnen")
    ob.add_argument("--ohne-offizielle-pruefung", action="store_true", help=argparse.SUPPRESS)
    ob.set_defaults(fn=cmd_oberflaeche)

    li = sub.add_parser("lizenz", help="Tarif und Monatsverbrauch anzeigen")
    li.set_defaults(fn=cmd_lizenz)

    b = sub.add_parser("beispiel", help="Beispieldateien in einen Ordner kopieren")
    b.add_argument("ziel", type=Path)
    b.set_defaults(fn=cmd_beispiel)
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    try:
        return a.fn(a)
    except (LizenzFehler, RegelFehler, FileNotFoundError, KeyError, ValueError) as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
