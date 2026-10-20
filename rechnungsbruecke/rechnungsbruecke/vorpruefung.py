"""Schnelle Vorprüfung mit verständlichen Meldungen, bevor eine E-Rechnung erzeugt wird.

Deckt die Fehler ab, die in der Praxis am häufigsten zur Ablehnung führen. Die
vollständige Prüfung nach EN 16931/XRechnung übernimmt `offiziell.py`.
"""
import re
from dataclasses import dataclass

from .modell import KATEGORIEN, Rechnung

UST_ID = re.compile(r"^[A-Z]{2}[0-9A-Z+*.]{2,13}$")


@dataclass
class Meldung:
    schwere: str  # "fehler" oder "hinweis"
    text: str


def iban_gueltig(iban: str) -> bool:
    s = iban.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    zahl = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(zahl) % 97 == 1


def pruefe(r: Rechnung) -> list[Meldung]:
    m: list[Meldung] = []

    def fehler(text):
        m.append(Meldung("fehler", f"Rechnung {r.nummer}: {text}"))

    def hinweis(text):
        m.append(Meldung("hinweis", f"Rechnung {r.nummer}: {text}"))

    v, k = r.verkaeufer, r.kaeufer
    kategorien = {p.kategorie for p in r.positionen}

    for wer, partei in (("Verkäufer", v), ("Käufer", k)):
        if not partei.name:
            fehler(f"{wer}: Name fehlt")
        a = partei.anschrift
        if not (a.strasse and a.plz and a.ort):
            fehler(f"{wer}: Anschrift unvollständig (Straße, PLZ und Ort sind Pflicht)")
        if not re.fullmatch(r"[A-Z]{2}", a.land or ""):
            fehler(f"{wer}: Ländercode '{a.land}' ungültig (zweistellig, z. B. DE)")
        if partei.ust_id and not UST_ID.match(partei.ust_id.replace(" ", "")):
            fehler(f"{wer}: USt-IdNr. '{partei.ust_id}' hat ein ungültiges Format")
        if partei.ust_id.startswith("DE") and not re.fullmatch(r"DE\d{9}", partei.ust_id.replace(" ", "")):
            fehler(f"{wer}: Deutsche USt-IdNr. muss aus DE und 9 Ziffern bestehen")

    if not v.email:
        fehler("Verkäufer: elektronische Adresse (E-Mail) fehlt (Pflicht in XRechnung)")
    if not k.email:
        fehler("Käufer: elektronische Adresse (E-Mail) fehlt (Pflicht in XRechnung). "
               "Spalte 'kunde_email' ergänzen.")
    if not (v.kontakt_name and v.kontakt_telefon and v.kontakt_email):
        fehler("Verkäufer: Ansprechpartner mit Name, Telefon und E-Mail ist in XRechnung Pflicht")
    if not v.ust_id and not v.steuernummer:
        fehler("Verkäufer: USt-IdNr. oder Steuernummer fehlt")
    if not (v.ust_id or v.registernummer or v.kennung):
        fehler("Verkäufer: Ohne USt-IdNr. ist eine Registernummer (z. B. Handelsregister) "
               "oder eine Verkäuferkennung ('kennung') nötig")

    if not r.bank:
        fehler("Bankverbindung fehlt (Zahlungsanweisung ist in XRechnung Pflicht)")
    elif not iban_gueltig(r.bank.iban):
        fehler(f"IBAN '{r.bank.iban}' ist ungültig (Prüfziffer stimmt nicht)")

    if not r.positionen:
        fehler("keine Positionen")
    for i, p in enumerate(r.positionen, start=1):
        if p.kategorie not in KATEGORIEN:
            fehler(f"Position {i}: Steuerkategorie '{p.kategorie}' wird nicht unterstützt "
                   f"(erlaubt: {', '.join(KATEGORIEN)})")
        elif p.kategorie == "S" and p.ust_satz <= 0:
            fehler(f"Position {i}: Kategorie S erfordert einen Steuersatz größer 0")
        elif p.kategorie != "S" and p.ust_satz != 0:
            fehler(f"Position {i}: Kategorie {p.kategorie} erfordert einen Steuersatz von 0 %")
        if p.menge == 0:
            hinweis(f"Position {i}: Menge ist 0")
        if p.einzelpreis < 0:
            fehler(f"Position {i}: Negativer Einzelpreis ist nicht erlaubt, stattdessen negative Menge verwenden")

    if kategorien & {"AE", "K"} and not k.ust_id:
        fehler("Reverse Charge/innergemeinschaftliche Lieferung erfordert die USt-IdNr. des Käufers")
    if "K" in kategorien and k.anschrift.land == v.anschrift.land:
        fehler("Innergemeinschaftliche Lieferung: Käufer muss in einem anderen EU-Land sitzen")
    if kategorien - {"S", "Z"} and not (v.ust_id or v.steuernummer):
        fehler("Steuerbefreite Umsätze erfordern USt-IdNr. oder Steuernummer des Verkäufers")
    if not (r.leistungsdatum or r.leistungszeitraum):
        hinweis("Leistungsdatum fehlt (nach § 14 UStG Pflichtangabe)")
    if r.faelligkeit and r.faelligkeit < r.datum:
        hinweis("Fälligkeit liegt vor dem Rechnungsdatum")
    if r.zahlbetrag < 0 and r.typ == "380":
        hinweis("Negativer Zahlbetrag. Ist eine Gutschrift (Typ 381) gemeint?")
    return m
