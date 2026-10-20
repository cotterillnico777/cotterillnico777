"""Verarbeitet Ausgangsrechnungen (CSV → E-Rechnung) und Eingangsrechnungen (E-Rechnung → HTML/Buchungsliste)."""
import json
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
from .regeln import Regelwerk
from .vorpruefung import pruefe

FORMATE = ("xrechnung", "zugferd", "beide")
OHNE_REGELN = ("Offizielle Prüfregeln sind nicht eingerichtet. Einmalig ausführen: rechnungsbruecke "
               "regeln-einrichten <XRechnung-Konfiguration der KoSIT als ZIP>. Ohne Prüfung (nur zum Testen): "
               "--ohne-offizielle-pruefung")


@dataclass
class Ergebnis:
    erzeugt: list[Path] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)
    berichte: list[Path] = field(default_factory=list)
    rechnungen: list[dict] = field(default_factory=list)  # je Rechnung: nummer, kunde, brutto, ok, meldungen

    @property
    def ok(self) -> bool:
        return not self.fehler


def dateiname(nummer: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", nummer)


def _eintrag(r, ok: bool, meldungen: list[str]) -> dict:
    return {"nummer": r.nummer, "kunde": r.kaeufer.name, "brutto": f"{r.brutto:.2f}", "ok": ok, "meldungen": meldungen}


def _pruefbericht(r, dateien: list[Path], werk: Regelwerk | None, warnungen: list[str]) -> dict:
    return {
        "rechnung": r.nummer,
        "erstellt_am": datetime.now().isoformat(timespec="seconds"),
        "dateien": [p.name for p in dateien],
        "offizielle_pruefung": "bestanden" if werk else "übersprungen",
        "regeln": werk.beschreibung if werk else None,
        "warnungen": warnungen,
        "summen": {"netto": f"{r.netto:.2f}", "steuer": f"{r.steuer:.2f}", "brutto": f"{r.brutto:.2f}",
                   "zahlbetrag": f"{r.zahlbetrag:.2f}", "waehrung": r.waehrung},
    }


def konvertiere(csv_pfad: Path, stamm: Stammdaten, ziel: Path, lizenz: Lizenz, format: str = "xrechnung",
                mapping: dict | None = None, regeln: Regelwerk | None = None,
                ohne_offizielle_pruefung: bool = False, nur_pruefen: bool = False) -> Ergebnis:
    """Erzeugt E-Rechnungen aus einer CSV-Datei.

    Jede Rechnung durchläuft Vorprüfung und offizielle Prüfung (EN 16931, bei XRechnung zusätzlich
    die XRechnung-Regeln); geschrieben wird nur, was beide besteht. Zu jeder Rechnung entsteht ein
    Prüfbericht (`<nummer>.pruefbericht.json`). Ohne eingerichtete Regeln wird nichts geschrieben,
    außer `ohne_offizielle_pruefung` ist ausdrücklich gesetzt. `nur_pruefen` schreibt nichts und
    verbraucht kein Kontingent.
    """
    if format not in FORMATE:
        raise ValueError(f"Format muss eines von {FORMATE} sein")
    erg = Ergebnis()
    if regeln is None and not ohne_offizielle_pruefung:
        erg.fehler.append(OHNE_REGELN)
        return erg
    try:
        rechnungen = importiere(csv_pfad, stamm, mapping)
    except ImportFehler as e:
        erg.fehler.append(str(e))
        return erg

    from .offiziell import pruefe_offiziell

    nutzung = Nutzung(lizenz)
    for r in rechnungen:
        meldungen = pruefe(r, "xrechnung" if format in ("xrechnung", "beide") else "zugferd")
        erg.hinweise += [m.text for m in meldungen if m.schwere == "hinweis"]
        fehler = [m.text for m in meldungen if m.schwere == "fehler"]
        if fehler:
            erg.fehler += fehler
            erg.rechnungen.append(_eintrag(r, False, fehler))
            continue
        xmls = {}
        if format in ("xrechnung", "beide"):
            xmls["xrechnung"] = erzeuge_cii(r, "xrechnung")
        if format in ("zugferd", "beide"):
            xmls["zugferd"] = erzeuge_cii(r, "zugferd")
        fatal, warnungen = [], []
        if regeln is not None:
            for profil, xml in xmls.items():
                for b in pruefe_offiziell(xml, regeln):
                    text = f"Rechnung {r.nummer} ({profil}): [{b.regel}] {b.text}"
                    (fatal if b.schwere == "fatal" else warnungen).append(text)
        erg.hinweise += warnungen
        if fatal:
            erg.fehler += fatal
            erg.rechnungen.append(_eintrag(r, False, fatal))
            continue
        erg.rechnungen.append(_eintrag(r, True, warnungen))
        if nur_pruefen:
            continue
        dateien: dict[Path, bytes] = {}
        if "xrechnung" in xmls:
            dateien[ziel / f"{dateiname(r.nummer)}.xml"] = xmls["xrechnung"]
        if "zugferd" in xmls:
            from .pdf import erzeuge_zugferd

            dateien[ziel / f"{dateiname(r.nummer)}.pdf"] = erzeuge_zugferd(r, xmls["zugferd"])
        try:
            nutzung.buchen(1)
        except LizenzFehler as e:
            erg.fehler.append(f"Rechnung {r.nummer} nicht erzeugt: {e}")
            erg.rechnungen[-1]["ok"] = False
            break
        ziel.mkdir(parents=True, exist_ok=True)
        for pfad, inhalt in dateien.items():
            pfad.write_bytes(inhalt)
            erg.erzeugt.append(pfad)
        bericht = ziel / f"{dateiname(r.nummer)}.pruefbericht.json"
        bericht.write_text(json.dumps(_pruefbericht(r, list(dateien), regeln, warnungen), indent=2,
                                      ensure_ascii=False), encoding="utf-8")
        erg.berichte.append(bericht)
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
                        format: str = "xrechnung", mapping: dict | None = None, regeln: Regelwerk | None = None,
                        mindestalter_s: float = 2.0, ohne_offizielle_pruefung: bool = False
                        ) -> list[tuple[Path, Ergebnis]]:
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
                erg = konvertiere(datei, stamm, ziel / "ausgang", lizenz, format, mapping, regeln,
                                  ohne_offizielle_pruefung=ohne_offizielle_pruefung)
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
