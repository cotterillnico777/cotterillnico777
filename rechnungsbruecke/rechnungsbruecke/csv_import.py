"""Import von Rechnungen aus CSV-Exporten (eine Zeile je Rechnungsposition).

Zeilen mit gleicher Rechnungsnummer werden zu einer Rechnung zusammengefasst.
Spaltennamen lassen sich per Mapping (JSON) auf die Exportnamen des
Altsystems abbilden, z. B. {"rechnungsnummer": "Belegnr"}.
"""
import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .modell import (KLEINUNTERNEHMER_GRUND, Anschrift, Bankverbindung, Partei,
                     Position, Rechnung)

PFLICHTSPALTEN = ["rechnungsnummer", "rechnungsdatum", "kunde_name", "kunde_strasse", "kunde_plz",
                  "kunde_ort", "bezeichnung", "menge", "einzelpreis"]
OPTIONALE_SPALTEN = ["leistungsdatum", "kunde_land", "kunde_ustid", "kunde_email", "kunde_referenz",
                     "bestellnummer", "einheit", "ust_satz", "steuerkategorie", "artikelnummer",
                     "zahlungsziel_tage", "typ", "bemerkung"]
EINHEITEN = {"stk": "C62", "stück": "C62", "st": "C62", "h": "HUR", "std": "HUR", "stunde": "HUR",
             "stunden": "HUR", "tag": "DAY", "tage": "DAY", "kg": "KGM", "m": "MTR", "m2": "MTK",
             "m²": "MTK", "m3": "MTQ", "l": "LTR", "pauschal": "LS", "psch": "LS", "monat": "MON"}


class ImportFehler(ValueError):
    pass


class Semikolon(csv.excel):
    delimiter = ";"


@dataclass
class Stammdaten:
    verkaeufer: Partei
    bank: Bankverbindung | None
    zahlungsziel_tage: int = 14
    ust_satz: Decimal = Decimal("19")
    kleinunternehmer: bool = False
    zahlungsbedingungen: str = "Zahlbar innerhalb von {tage} Tagen ohne Abzug"

    @classmethod
    def laden(cls, pfad: Path) -> "Stammdaten":
        d = json.loads(Path(pfad).read_text(encoding="utf-8"))
        v = d.get("verkaeufer", {})
        fehlend = [f for f in ("name", "strasse", "plz", "ort", "email") if not v.get(f)]
        if fehlend:
            raise ImportFehler(f"{pfad}: In 'verkaeufer' fehlen: {', '.join(fehlend)}")
        verkaeufer = Partei(
            name=v["name"],
            anschrift=Anschrift(v["strasse"], v["plz"], v["ort"], v.get("land", "DE")),
            ust_id=v.get("ust_id", ""), steuernummer=v.get("steuernummer", ""),
            registernummer=v.get("registernummer", ""), kennung=v.get("kennung", ""),
            email=v["email"], kontakt_name=v.get("kontakt_name", ""),
            kontakt_telefon=v.get("kontakt_telefon", ""), kontakt_email=v.get("kontakt_email", ""),
        )
        b = d.get("bank")
        bank = Bankverbindung(b["iban"], b.get("bic", ""), b.get("kontoinhaber", v["name"])) if b else None
        return cls(verkaeufer, bank,
                   zahlungsziel_tage=int(d.get("zahlungsziel_tage", 14)),
                   ust_satz=Decimal(str(d.get("ust_satz", "19"))),
                   kleinunternehmer=bool(d.get("kleinunternehmer", False)),
                   zahlungsbedingungen=d.get("zahlungsbedingungen",
                                             "Zahlbar innerhalb von {tage} Tagen ohne Abzug"))


def dezimal(text: str, feld: str, zeile: int, zahlenformat: str = "auto") -> Decimal:
    """Wandelt Zahlen aus Exporten um.

    zahlenformat "de": 1.234,56 · "en": 1,234.56 · "auto": erkennt das Format, lehnt aber
    mehrdeutige Werte wie "1.250" ab (1250 oder 1,25?), statt falsch zu raten.
    """
    s = text.strip().replace("€", "").replace(" ", "").replace("\u00a0", "")
    if zahlenformat == "de":
        s = s.replace(".", "").replace(",", ".")
    elif zahlenformat == "en":
        s = s.replace(",", "")
    elif "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        if s.count(",") > 1:
            raise ImportFehler(f"Zeile {zeile}: '{text}' im Feld '{feld}' ist mehrdeutig. "
                               f"Bitte '_zahlenformat' (\"de\" oder \"en\") in der Mapping-Datei setzen.")
        s = s.replace(",", ".")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3):
        raise ImportFehler(f"Zeile {zeile}: '{text}' im Feld '{feld}' ist mehrdeutig (Tausenderpunkt oder "
                           f"Dezimalpunkt?). Bitte '_zahlenformat' (\"de\" oder \"en\") in der Mapping-Datei setzen.")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ImportFehler(f"Zeile {zeile}: '{text}' ist keine gültige Zahl im Feld '{feld}'") from None


def datum(text: str, feld: str, zeile: int) -> date:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%Y%m%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            pass
    raise ImportFehler(f"Zeile {zeile}: '{text}' ist kein gültiges Datum im Feld '{feld}' (erwartet TT.MM.JJJJ)")


def einheit(text: str) -> str:
    t = text.strip()
    return EINHEITEN.get(t.lower(), t.upper()) if t else "C62"


def lese_text(pfad: Path) -> str:
    roh = Path(pfad).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return roh.decode(enc)
        except UnicodeDecodeError:
            pass
    raise ImportFehler(f"{pfad}: Zeichenkodierung nicht erkannt (erwartet UTF-8 oder Windows-1252)")


def lese_zeilen(pfad: Path, mapping: dict[str, str] | None = None) -> list[dict[str, str]]:
    text = lese_text(pfad)
    try:
        dialekt = csv.Sniffer().sniff(text.splitlines()[0], delimiters=";,\t|")
    except (csv.Error, IndexError):
        dialekt = Semikolon
    reader = csv.DictReader(io.StringIO(text), dialect=dialekt)
    rueck = {quelle.strip().lower(): ziel for ziel, quelle in (mapping or {}).items() if not ziel.startswith("_")}
    zeilen = []
    for roh in reader:
        z = {}
        for k, v in roh.items():
            if k is None:
                continue
            name = k.strip().lower()
            z[rueck.get(name, name)] = (v or "").strip()
        if any(z.values()):
            zeilen.append(z)
    if not zeilen:
        raise ImportFehler(f"{pfad}: keine Datenzeilen gefunden")
    fehlend = [s for s in PFLICHTSPALTEN if s not in zeilen[0]]
    if fehlend:
        raise ImportFehler(f"{pfad}: Pflichtspalten fehlen: {', '.join(fehlend)} "
                           f"(vorhanden: {', '.join(zeilen[0])}). Ggf. Mapping-Datei anpassen.")
    return zeilen


def importiere(pfad: Path, stamm: Stammdaten, mapping: dict[str, str] | None = None) -> list[Rechnung]:
    zf = (mapping or {}).get("_zahlenformat", "auto")
    if zf not in ("auto", "de", "en"):
        raise ImportFehler(f"_zahlenformat '{zf}' ungültig (erlaubt: auto, de, en)")
    gruppen: dict[str, list[tuple[int, dict]]] = {}
    for nr, z in enumerate(lese_zeilen(pfad, mapping), start=2):
        if not z.get("rechnungsnummer"):
            raise ImportFehler(f"Zeile {nr}: Rechnungsnummer fehlt")
        gruppen.setdefault(z["rechnungsnummer"], []).append((nr, z))

    rechnungen = []
    for nummer, zeilen in gruppen.items():
        nr, kopf = zeilen[0]
        for feld in ("rechnungsdatum", "kunde_name", "kunde_strasse", "kunde_plz", "kunde_ort"):
            if not kopf.get(feld):
                raise ImportFehler(f"Zeile {nr}: Pflichtfeld '{feld}' ist leer (Rechnung {nummer})")
        rdatum = datum(kopf["rechnungsdatum"], "rechnungsdatum", nr)
        tage = int(kopf.get("zahlungsziel_tage") or stamm.zahlungsziel_tage)
        kaeufer = Partei(
            name=kopf["kunde_name"],
            anschrift=Anschrift(kopf["kunde_strasse"], kopf["kunde_plz"], kopf["kunde_ort"],
                                (kopf.get("kunde_land") or "DE").upper()),
            ust_id=kopf.get("kunde_ustid", ""), email=kopf.get("kunde_email", ""),
        )
        positionen = []
        for pnr, z in zeilen:
            if not z.get("bezeichnung"):
                raise ImportFehler(f"Zeile {pnr}: Bezeichnung der Position fehlt")
            if stamm.kleinunternehmer:
                kategorie, satz = "E", Decimal("0")
            else:
                satz = dezimal(z["ust_satz"], "ust_satz", pnr, zf) if z.get("ust_satz") else stamm.ust_satz
                kategorie = (z.get("steuerkategorie") or ("S" if satz > 0 else "")).upper()
                if not kategorie:
                    raise ImportFehler(f"Zeile {pnr}: Bei 0 % Umsatzsteuer muss 'steuerkategorie' angegeben "
                                       f"werden (E, AE, K, G oder Z)")
            positionen.append(Position(
                bezeichnung=z["bezeichnung"],
                menge=dezimal(z["menge"], "menge", pnr, zf),
                einzelpreis=dezimal(z["einzelpreis"], "einzelpreis", pnr, zf),
                ust_satz=satz, einheit=einheit(z.get("einheit", "")), kategorie=kategorie,
                artikelnummer=z.get("artikelnummer", ""),
            ))
        rechnungen.append(Rechnung(
            nummer=nummer, datum=rdatum, verkaeufer=stamm.verkaeufer, kaeufer=kaeufer,
            positionen=positionen, bank=stamm.bank, typ=kopf.get("typ") or "380",
            leistungsdatum=datum(kopf["leistungsdatum"], "leistungsdatum", nr) if kopf.get("leistungsdatum") else rdatum,
            faelligkeit=rdatum + timedelta(days=tage),
            zahlungsbedingungen=stamm.zahlungsbedingungen.format(tage=tage),
            kaeufer_referenz=kopf.get("kunde_referenz") or kopf.get("bestellnummer") or nummer,
            bestellnummer=kopf.get("bestellnummer", ""), bemerkung=kopf.get("bemerkung", ""),
            befreiungsgruende={"E": KLEINUNTERNEHMER_GRUND} if stamm.kleinunternehmer else {},
        ))
    return rechnungen
