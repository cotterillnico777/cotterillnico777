"""Prüfung, Buchungsfreigabe, Dublettenerkennung und Quarantäne für Eingangsrechnungen.

Ablauf: einlesen → offizielle Prüfung (XSD, EN 16931, ggf. XRechnung) → Rechenkontrolle →
Dublettenprüfung gegen das Buchungsregister → nur bei bestandener Prüfung buchbar.
Fehlerhafte Rechnungen landen in der Quarantäne statt in der Buchungsliste. Bei Dublettenverdacht
ist eine ausdrückliche Bestätigung nötig; eine bereits gebuchte identische Datei wird nie erneut gebucht.
"""
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .ansicht import schreibe_buchungsliste
from .leser import Eingangsrechnung, lies
from .regeln import Regelwerk

STATUS_BESTANDEN = "bestanden"
STATUS_FEHLER = "fehler"
STATUS_UNGEPRUEFT = "ungeprüft"


class BuchungsFehler(RuntimeError):
    pass


@dataclass
class Dublette:
    art: str   # "identisch" (blockiert) oder "verdacht" (Bestätigung nötig)
    text: str


@dataclass
class Eingangspruefung:
    rechnung: Eingangsrechnung
    sha256: str
    status: str
    befunde: list[str] = field(default_factory=list)     # verhindern die Buchung
    warnungen: list[str] = field(default_factory=list)   # informativ
    dubletten: list[Dublette] = field(default_factory=list)
    testmodus: bool = False

    @property
    def buchbar(self) -> bool:
        return self.status == STATUS_BESTANDEN and not any(d.art == "identisch" for d in self.dubletten)

    @property
    def bestaetigung_noetig(self) -> bool:
        return any(d.art == "verdacht" for d in self.dubletten)

    def als_dict(self) -> dict:
        r = self.rechnung
        return {
            "status": self.status, "testmodus": self.testmodus, "buchbar": self.buchbar,
            "bestaetigung_noetig": self.bestaetigung_noetig, "befunde": self.befunde,
            "warnungen": self.warnungen, "dubletten": [asdict(d) for d in self.dubletten],
            "rechnung": {"nummer": r.nummer, "datum": r.datum, "lieferant": r.verkaeufer,
                         "lieferant_ust_id": r.verkaeufer_ust_id, "brutto": f"{r.brutto:.2f}",
                         "waehrung": r.waehrung, "profil": r.profil, "syntax": r.syntax},
            "sha256": self.sha256,
        }


def _norm(text: str) -> str:
    return re.sub(r"[\s\-_/.]", "", (text or "")).upper()


def lieferanten_schluessel(r: Eingangsrechnung) -> str:
    return _norm(r.verkaeufer_ust_id) or "NAME:" + _norm(r.verkaeufer)


class Buchungsregister:
    """Merkt sich jede gebuchte Rechnung (JSON-Zeilen neben der Buchungsliste)."""

    def __init__(self, buchungsliste: Path):
        self.buchungsliste = Path(buchungsliste)
        self.pfad = self.buchungsliste.with_name(self.buchungsliste.stem + ".register.jsonl")

    def eintraege(self) -> list[dict]:
        if not self.pfad.exists():
            return []
        return [json.loads(z) for z in self.pfad.read_text(encoding="utf-8").splitlines() if z.strip()]

    def dubletten(self, r: Eingangsrechnung, sha: str) -> list[Dublette]:
        funde = []
        lief, nr = lieferanten_schluessel(r), _norm(r.nummer)
        for e in self.eintraege():
            am = e["gebucht_am"][:16].replace("T", " ")
            if e["sha256"] == sha:
                funde.append(Dublette("identisch", f"Diese Datei wurde am {am} bereits gebucht."))
            elif e["lieferant"] == lief and e["nummer"] == nr:
                abweichung = "" if Decimal(e["brutto"]) == r.brutto else \
                    f" (damals {e['brutto']} €, jetzt {r.brutto:.2f} € – Korrekturrechnung?)"
                funde.append(Dublette("verdacht", f"Rechnung {r.nummer} dieses Lieferanten wurde am {am} "
                                                  f"bereits gebucht{abweichung}."))
            elif e["lieferant"] == lief and e["datum"] == r.datum and Decimal(e["brutto"]) == r.brutto:
                funde.append(Dublette("verdacht", f"Gleicher Lieferant, gleiches Datum und gleicher Betrag wie "
                                                  f"die am {am} gebuchte Rechnung {e['nummer_original']}."))
        return funde

    def eintragen(self, r: Eingangsrechnung, sha: str, bestaetigt: bool) -> None:
        eintrag = {"sha256": sha, "lieferant": lieferanten_schluessel(r), "nummer": _norm(r.nummer),
                   "nummer_original": r.nummer, "datum": r.datum, "brutto": f"{r.brutto:.2f}",
                   "gebucht_am": datetime.now().isoformat(timespec="seconds"),
                   "dublette_bestaetigt": bestaetigt}
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pfad, "a", encoding="utf-8") as f:
            f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")


def pruefe_eingang(xml: bytes, werk: Regelwerk | None, buchungsliste: Path | None = None,
                   ohne_offizielle_pruefung: bool = False) -> Eingangspruefung:
    """Prüft eine Eingangsrechnung vollständig. Ohne Regelwerk ist sie nicht buchbar (außer im Testmodus)."""
    r = lies(xml)
    sha = hashlib.sha256(xml).hexdigest()
    befunde, warnungen = [], []
    if werk is not None:
        from .offiziell import pruefe_offiziell

        for b in pruefe_offiziell(xml, werk, eingang=True):
            (befunde if b.schwere == "fatal" else warnungen).append(f"[{b.regel}] {b.text}")
    befunde += [f"Rechenfehler: {p}" for p in r.plausibilitaet()]
    if befunde:
        status = STATUS_FEHLER
    elif werk is None and not ohne_offizielle_pruefung:
        status = STATUS_UNGEPRUEFT
        befunde.append("Offizielle Prüfregeln sind nicht eingerichtet. Ungeprüfte Rechnungen werden nicht gebucht.")
    else:
        status = STATUS_BESTANDEN
    dubletten = Buchungsregister(buchungsliste).dubletten(r, sha) if buchungsliste else []
    return Eingangspruefung(r, sha, status, befunde, warnungen, dubletten,
                            testmodus=werk is None and ohne_offizielle_pruefung)


def buche(pruefung: Eingangspruefung, buchungsliste: Path, bestaetigt: bool = False) -> None:
    if pruefung.status != STATUS_BESTANDEN:
        raise BuchungsFehler("Die Rechnung hat die Prüfung nicht bestanden und wird nicht gebucht: "
                             + "; ".join(pruefung.befunde))
    identisch = [d.text for d in pruefung.dubletten if d.art == "identisch"]
    if identisch:
        raise BuchungsFehler(" ".join(identisch))
    if pruefung.bestaetigung_noetig and not bestaetigt:
        raise BuchungsFehler("Möglicherweise doppelt: " + " ".join(d.text for d in pruefung.dubletten)
                             + " Bitte prüfen und die Buchung ausdrücklich bestätigen.")
    schreibe_buchungsliste(buchungsliste, [pruefung.rechnung])
    Buchungsregister(buchungsliste).eintragen(pruefung.rechnung, pruefung.sha256, bestaetigt)


def in_quarantaene(ordner: Path, name: str, inhalt: bytes, gruende: list[str],
                   pruefung: Eingangspruefung | None = None) -> Path:
    """Legt die Originaldatei mit einem Bericht der Gründe in `ordner` ab."""
    ordner.mkdir(parents=True, exist_ok=True)
    sicher = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name) or "rechnung"
    # Gleicher Inhalt → gleicher Name: dieselbe Datei landet nur einmal in der Quarantäne
    ziel = ordner / f"{hashlib.sha256(inhalt).hexdigest()[:12]}_{sicher}"
    if ziel.exists():
        return ziel
    ziel.write_bytes(inhalt)
    bericht = {"datei": ziel.name, "abgelegt_am": datetime.now().isoformat(timespec="seconds"), "gruende": gruende}
    if pruefung:
        bericht["pruefung"] = pruefung.als_dict()
    ziel.with_name(ziel.name + ".quarantaene.json").write_text(
        json.dumps(bericht, indent=2, ensure_ascii=False), encoding="utf-8")
    return ziel
