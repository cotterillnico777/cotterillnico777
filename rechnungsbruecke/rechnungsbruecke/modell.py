"""Datenmodell einer Rechnung nach EN 16931 (Teilmenge) inklusive Berechnung.

Beträge werden mit Decimal und kaufmännischer Rundung auf zwei Nachkommastellen
berechnet. Die Kennungen in Kommentaren (BT-/BG-) verweisen auf EN 16931.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

# Steuerkategorien (UNTDID 5305), die die Rechnungsbrücke unterstützt
KATEGORIEN = {
    "S": "Umsatzsteuer (Regelsatz/ermäßigt)",
    "Z": "Nullsatz",
    "E": "Steuerbefreit",
    "AE": "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge)",
    "K": "Innergemeinschaftliche Lieferung",
    "G": "Ausfuhr in Drittland",
}
STANDARD_BEFREIUNGSGRUND = {
    "E": "Steuerbefreit",
    "AE": "Steuerschuldnerschaft des Leistungsempfängers",
    "K": "Steuerfreie innergemeinschaftliche Lieferung",
    "G": "Steuerfreie Ausfuhrlieferung",
}
KLEINUNTERNEHMER_GRUND = "Kein Ausweis von Umsatzsteuer, da Kleinunternehmer gemäß § 19 UStG"


def runden(betrag: Decimal) -> Decimal:
    return Decimal(betrag).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Anschrift:
    strasse: str
    plz: str
    ort: str
    land: str = "DE"


@dataclass
class Partei:
    name: str
    anschrift: Anschrift
    ust_id: str = ""            # BT-31 / BT-48
    steuernummer: str = ""      # BT-32
    registernummer: str = ""    # BT-30, z. B. Handelsregisternummer
    kennung: str = ""           # BT-29, z. B. Lieferantennummer beim Kunden
    email: str = ""             # BT-34 / BT-49 (elektronische Adresse)
    kontakt_name: str = ""      # BT-41
    kontakt_telefon: str = ""   # BT-42
    kontakt_email: str = ""     # BT-43


@dataclass
class Bankverbindung:
    iban: str
    bic: str = ""
    kontoinhaber: str = ""


@dataclass
class Position:
    bezeichnung: str
    menge: Decimal
    einzelpreis: Decimal        # BT-146, netto
    ust_satz: Decimal           # BT-152
    einheit: str = "C62"        # UN/ECE Rec. 20, C62 = Stück
    kategorie: str = "S"        # BT-151
    artikelnummer: str = ""

    @property
    def netto(self) -> Decimal:  # BT-131
        return runden(self.menge * self.einzelpreis)


@dataclass
class Steueraufschluesselung:   # BG-23
    kategorie: str
    satz: Decimal
    basis: Decimal
    steuer: Decimal
    befreiungsgrund: str = ""


@dataclass
class Rechnung:
    nummer: str                 # BT-1
    datum: date                 # BT-2
    verkaeufer: Partei
    kaeufer: Partei
    positionen: list[Position]
    bank: Bankverbindung | None = None
    typ: str = "380"            # BT-3: 380 Rechnung, 381 Gutschrift, 384 Korrektur
    waehrung: str = "EUR"
    leistungsdatum: date | None = None          # BT-72
    leistungszeitraum: tuple[date, date] | None = None  # BG-14
    faelligkeit: date | None = None             # BT-9
    zahlungsbedingungen: str = ""               # BT-20
    kaeufer_referenz: str = ""                  # BT-10 (Leitweg-ID oder Kundenreferenz)
    bestellnummer: str = ""                     # BT-13
    vorauszahlung: Decimal = Decimal("0")       # BT-113
    bemerkung: str = ""                         # BT-22
    befreiungsgruende: dict[str, str] = field(default_factory=dict)

    # --- Summen nach EN 16931 ---
    @property
    def summe_positionen(self) -> Decimal:      # BT-106
        return sum((p.netto for p in self.positionen), Decimal("0.00"))

    @property
    def steuern(self) -> list[Steueraufschluesselung]:
        gruppen: dict[tuple[str, Decimal], Decimal] = {}
        for p in self.positionen:
            key = (p.kategorie, Decimal(p.ust_satz))
            gruppen[key] = gruppen.get(key, Decimal("0.00")) + p.netto
        return [
            Steueraufschluesselung(
                kategorie=kat, satz=satz, basis=basis,
                steuer=runden(basis * satz / 100),
                befreiungsgrund=("" if kat in ("S", "Z") else
                                 self.befreiungsgruende.get(kat) or STANDARD_BEFREIUNGSGRUND.get(kat, "")),
            )
            for (kat, satz), basis in sorted(gruppen.items(), key=lambda kv: (kv[0][0], kv[0][1]))
        ]

    @property
    def netto(self) -> Decimal:                 # BT-109
        return self.summe_positionen

    @property
    def steuer(self) -> Decimal:                # BT-110
        return sum((s.steuer for s in self.steuern), Decimal("0.00"))

    @property
    def brutto(self) -> Decimal:                # BT-112
        return self.netto + self.steuer

    @property
    def zahlbetrag(self) -> Decimal:            # BT-115
        return self.brutto - runden(self.vorauszahlung)
