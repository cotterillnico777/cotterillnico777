"""Verarbeitet Ausgangsrechnungen (CSV → E-Rechnung) und Eingangsrechnungen (E-Rechnung → HTML/Buchungsliste)."""
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .ansicht import als_html, schreibe_buchungsliste
from .cii import erzeuge_cii
from .csv_import import ImportFehler, Stammdaten, importiere
from .leser import LeseFehler, lies_datei
from .lizenz import Lizenz, LizenzFehler, Nutzung
from .vorpruefung import pruefe

FORMATE = ("xrechnung", "zugferd", "beide")


@dataclass
class Ergebnis:
    erzeugt: list[Path] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fehler


def dateiname(nummer: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", nummer)


def konvertiere(csv_pfad: Path, stamm: Stammdaten, ziel: Path, lizenz: Lizenz, format: str = "xrechnung",
                mapping: dict | None = None, regeln: Path | None = None) -> Ergebnis:
    """Erzeugt E-Rechnungen aus einer CSV-Datei. Fehlerhafte Rechnungen werden übersprungen und gemeldet."""
    if format not in FORMATE:
        raise ValueError(f"Format muss eines von {FORMATE} sein")
    erg = Ergebnis()
    try:
        rechnungen = importiere(csv_pfad, stamm, mapping)
    except ImportFehler as e:
        erg.fehler.append(str(e))
        return erg

    nutzung = Nutzung(lizenz)
    ziel.mkdir(parents=True, exist_ok=True)
    for r in rechnungen:
        meldungen = pruefe(r)
        erg.hinweise += [m.text for m in meldungen if m.schwere == "hinweis"]
        fehler = [m.text for m in meldungen if m.schwere == "fehler"]
        if fehler:
            erg.fehler += fehler
            continue
        dateien: dict[Path, bytes] = {}
        if format in ("xrechnung", "beide"):
            xml = erzeuge_cii(r, "xrechnung")
            if regeln:
                from .offiziell import pruefe_offiziell

                fatal = [b for b in pruefe_offiziell(xml, regeln) if b.schwere == "fatal"]
                if fatal:
                    erg.fehler += [f"Rechnung {r.nummer}: [{b.regel}] {b.text}" for b in fatal]
                    continue
            dateien[ziel / f"{dateiname(r.nummer)}.xml"] = xml
        if format in ("zugferd", "beide"):
            from .pdf import erzeuge_zugferd

            dateien[ziel / f"{dateiname(r.nummer)}.pdf"] = erzeuge_zugferd(r)
        try:
            nutzung.buchen(1)
        except LizenzFehler as e:
            erg.fehler.append(f"Rechnung {r.nummer} nicht erzeugt: {e}")
            break
        for pfad, inhalt in dateien.items():
            pfad.write_bytes(inhalt)
            erg.erzeugt.append(pfad)
    return erg


def lese_eingang(datei: Path, ziel: Path, buchungsliste: Path | None = None) -> Ergebnis:
    """Macht eine eingehende E-Rechnung lesbar (HTML) und ergänzt optional die Buchungsliste."""
    erg = Ergebnis()
    try:
        r = lies_datei(datei)
    except (LeseFehler, ValueError) as e:
        erg.fehler.append(f"{datei.name}: {e}")
        return erg
    ziel.mkdir(parents=True, exist_ok=True)
    html_pfad = ziel / f"{dateiname(r.verkaeufer)[:40]}_{dateiname(r.nummer)}.html"
    html_pfad.write_text(als_html(r), encoding="utf-8")
    erg.erzeugt.append(html_pfad)
    erg.hinweise += [f"{datei.name}: {p}" for p in r.plausibilitaet()]
    if buchungsliste:
        schreibe_buchungsliste(buchungsliste, [r])
        erg.erzeugt.append(buchungsliste)
    return erg


def _ablegen(datei: Path, unterordner: str, protokoll: str = "") -> None:
    ordner = datei.parent / unterordner
    ordner.mkdir(exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    ziel = ordner / f"{stempel}_{datei.name}"
    shutil.move(str(datei), ziel)
    if protokoll:
        ziel.with_suffix(ziel.suffix + ".log").write_text(protokoll, encoding="utf-8")


def hotfolder_durchlauf(eingang: Path, ziel: Path, stamm: Stammdaten | None, lizenz: Lizenz,
                        format: str = "xrechnung", mapping: dict | None = None, regeln: Path | None = None,
                        mindestalter_s: float = 2.0) -> list[tuple[Path, Ergebnis]]:
    """Ein Durchlauf: CSV → Ausgangsrechnungen, XML/PDF → Eingangsrechnungen.

    Erfolgreich verarbeitete Dateien landen in `eingang/verarbeitet`, fehlerhafte in
    `eingang/fehler` (mit .log). Dateien, die jünger als `mindestalter_s` sind, werden
    übersprungen, damit noch laufende Exporte nicht halb gelesen werden.
    """
    if not lizenz.hotfolder:
        raise LizenzFehler(f"Der Hotfolder ist im Tarif '{lizenz.tarif}' nicht enthalten (ab Tarif 'business').")
    ergebnisse = []
    jetzt = time.time()
    for datei in sorted(p for p in eingang.iterdir() if p.is_file()):
        if jetzt - datei.stat().st_mtime < mindestalter_s:
            continue
        endung = datei.suffix.lower()
        if endung == ".csv":
            if stamm is None:
                erg = Ergebnis(fehler=["Keine Stammdaten angegeben, CSV-Dateien können nicht verarbeitet werden"])
            else:
                erg = konvertiere(datei, stamm, ziel / "ausgang", lizenz, format, mapping, regeln)
        elif endung in (".xml", ".pdf"):
            erg = lese_eingang(datei, ziel / "eingang", ziel / "eingang" / "buchungsliste.csv")
        else:
            continue
        if erg.ok:
            _ablegen(datei, "verarbeitet")
        else:
            # Teilweise erfolgreiche Dateien: erzeugte Rechnungen protokollieren, damit sie
            # nach der Korrektur nicht doppelt versendet werden.
            erzeugt = [f"Trotzdem erzeugt: {p.name}" for p in erg.erzeugt]
            _ablegen(datei, "fehler", "\n".join(erg.fehler + erg.hinweise + erzeugt) + "\n")
        ergebnisse.append((datei, erg))
    return ergebnisse
