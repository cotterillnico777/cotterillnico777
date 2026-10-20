"""Tarife, signierte Lizenzdateien (Ed25519, offline prüfbar) und Nutzungszähler.

Ohne Lizenz läuft die Rechnungsbrücke im Tarif "free". Lizenzdateien stellt der
Anbieter mit `werkzeuge/lizenz_ausstellen.py` und seinem privaten Schlüssel aus;
hier ist nur der öffentliche Schlüssel hinterlegt.
"""
import base64
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Vor dem Verkauf mit `python3 werkzeuge/lizenz_ausstellen.py schluessel` ein eigenes
# Schlüsselpaar erzeugen und den öffentlichen Schlüssel hier eintragen.
OEFFENTLICHER_SCHLUESSEL = "REPLACE_WITH_YOUR_ED25519_PUBLIC_KEY"

TARIFE = {
    "free": {"rechnungen_monat": 25, "hotfolder": False, "preis_monat": 0},
    "starter": {"rechnungen_monat": 300, "hotfolder": False, "preis_monat": 39},
    "business": {"rechnungen_monat": 3000, "hotfolder": True, "preis_monat": 99},
    "unternehmen": {"rechnungen_monat": None, "hotfolder": True, "preis_monat": 249},
}


class LizenzFehler(RuntimeError):
    pass


@dataclass
class Lizenz:
    kunde: str
    tarif: str
    gueltig_bis: date | None

    @property
    def limit(self) -> int | None:
        return TARIFE[self.tarif]["rechnungen_monat"]

    @property
    def hotfolder(self) -> bool:
        return TARIFE[self.tarif]["hotfolder"]


FREE = Lizenz("Free", "free", None)


def datenverzeichnis() -> Path:
    return Path(os.environ.get("RB_DATENVERZEICHNIS", Path.home() / ".rechnungsbruecke"))


def nutzdaten(kunde: str, tarif: str, gueltig_bis: str) -> bytes:
    return json.dumps({"kunde": kunde, "tarif": tarif, "gueltig_bis": gueltig_bis},
                      sort_keys=True, ensure_ascii=False).encode("utf-8")


def pruefe_lizenzdatei(pfad: Path, heute: date | None = None) -> Lizenz:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        d = json.loads(Path(pfad).read_text(encoding="utf-8"))
        signatur = base64.b64decode(d["signatur"])
        schluessel = Ed25519PublicKey.from_public_bytes(base64.b64decode(OEFFENTLICHER_SCHLUESSEL))
    except (OSError, ValueError, KeyError) as e:
        raise LizenzFehler(f"Lizenzdatei {pfad} ist nicht lesbar: {e}") from None
    try:
        schluessel.verify(signatur, nutzdaten(d["kunde"], d["tarif"], d["gueltig_bis"]))
    except InvalidSignature:
        raise LizenzFehler(f"Lizenzdatei {pfad} ist ungültig (Signatur passt nicht)") from None
    if d["tarif"] not in TARIFE:
        raise LizenzFehler(f"Unbekannter Tarif '{d['tarif']}'")
    bis = date.fromisoformat(d["gueltig_bis"])
    if bis < (heute or date.today()):
        raise LizenzFehler(f"Lizenz ist am {bis:%d.%m.%Y} abgelaufen. Bitte verlängern.")
    return Lizenz(d["kunde"], d["tarif"], bis)


def aktuelle_lizenz(pfad: str | Path | None = None) -> Lizenz:
    kandidat = pfad or os.environ.get("RB_LIZENZ") or datenverzeichnis() / "lizenz.json"
    if not Path(kandidat).exists():
        if pfad:
            raise LizenzFehler(f"Lizenzdatei {pfad} nicht gefunden")
        return FREE
    return pruefe_lizenzdatei(Path(kandidat))


class Nutzung:
    """Zählt erzeugte Rechnungen pro Kalendermonat."""

    def __init__(self, lizenz: Lizenz, heute: date | None = None):
        self.lizenz = lizenz
        self.monat = (heute or date.today()).strftime("%Y-%m")
        self.pfad = datenverzeichnis() / "nutzung.json"

    def _laden(self) -> dict:
        try:
            return json.loads(self.pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @property
    def verbraucht(self) -> int:
        return int(self._laden().get(self.monat, 0))

    @property
    def verbleibend(self) -> int | None:
        return None if self.lizenz.limit is None else max(0, self.lizenz.limit - self.verbraucht)

    def buchen(self, anzahl: int = 1) -> None:
        rest = self.verbleibend
        if rest is not None and anzahl > rest:
            raise LizenzFehler(
                f"Monatskontingent des Tarifs '{self.lizenz.tarif}' erreicht "
                f"({self.lizenz.limit} Rechnungen, noch {rest} frei). Upgrade: siehe README, Abschnitt Tarife.")
        daten = self._laden()
        daten[self.monat] = daten.get(self.monat, 0) + anzahl
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(json.dumps(daten), encoding="utf-8")
