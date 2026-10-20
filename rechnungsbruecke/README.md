# Rechnungsbrücke

**Macht aus dem Rechnungsexport Ihres bestehenden Systems gültige E-Rechnungen – lokal, ohne Cloud, ohne ERP-Wechsel.**

- **Ausgang:** CSV-Export (eine Zeile je Position) → **XRechnung 3.0** (CII-XML) und/oder **ZUGFeRD/Factur-X** (PDF/A-3 mit eingebettetem XML, Profil EN 16931)
- **Eingang:** XRechnung/ZUGFeRD (CII oder UBL, als XML oder PDF) → lesbare HTML-Ansicht + Buchungsliste (CSV)
- **Prüfung:** verständliche Vorprüfung auf Deutsch; optional vollständige Prüfung gegen die offiziellen EN-16931- und XRechnung-Schematron-Regeln
- **Hotfolder:** Das Altsystem legt CSV-Dateien ab, die Rechnungsbrücke erzeugt automatisch die E-Rechnungen
- Läuft vollständig **on-premises** (Windows, Linux, macOS; Python ≥ 3.10). Rechnungsdaten verlassen das Haus nicht.

Geschäftsmodell und Finanzplan: [`GESCHAEFTSMODELL.md`](GESCHAEFTSMODELL.md).

## Schnellstart

```bash
pip install .                      # optional: pip install ".[offiziell]" für die Prüfung mit offiziellen Regeln
rechnungsbruecke beispiel demo     # Beispieldateien anlegen
rechnungsbruecke konvertieren demo/rechnungen.csv --stammdaten demo/stammdaten.json --ziel demo/ausgabe --format beide
rechnungsbruecke pruefen demo/ausgabe/RE-2026-1001.xml
rechnungsbruecke lesen demo/ausgabe/RE-2026-1002.pdf --ziel demo/lesbar --buchungsliste demo/buchungen.csv
```

Ohne Installation: `python3 -m rechnungsbruecke …` im Ordner `rechnungsbruecke/`.

## Eingabe

### Stammdaten (`stammdaten.json`)
Ihre Firmendaten, einmalig gepflegt: Name, Anschrift, USt-IdNr. und/oder Steuernummer, Registernummer,
elektronische Rechnungsadresse (E-Mail), Ansprechpartner (Name, Telefon, E-Mail), Bankverbindung,
Standard-Zahlungsziel und -Steuersatz, optional `"kleinunternehmer": true` (§ 19 UStG).
Vorlage: [`rechnungsbruecke/beispiele/stammdaten.json`](rechnungsbruecke/beispiele/stammdaten.json).

### Rechnungs-CSV
Eine Zeile je Rechnungsposition; Zeilen mit gleicher Rechnungsnummer ergeben eine Rechnung.
Trennzeichen `;` `,` Tab oder `|`, Kodierung UTF-8 oder Windows-1252 werden erkannt.

| Spalte | Pflicht | Hinweis |
|---|---|---|
| `rechnungsnummer`, `rechnungsdatum` | ja | Datum als `TT.MM.JJJJ` oder `JJJJ-MM-TT` |
| `kunde_name`, `kunde_strasse`, `kunde_plz`, `kunde_ort` | ja | |
| `bezeichnung`, `menge`, `einzelpreis` | ja | Einzelpreis netto |
| `kunde_email` | für XRechnung ja | elektronische Adresse des Käufers |
| `kunde_referenz` | empfohlen | Leitweg-ID (öffentliche Auftraggeber) oder Ihre Kundennummer |
| `leistungsdatum`, `kunde_land`, `kunde_ustid`, `bestellnummer`, `einheit`, `ust_satz`, `steuerkategorie`, `artikelnummer`, `zahlungsziel_tage`, `typ`, `bemerkung` | nein | `einheit` z. B. Stk, Std, kg, m, pauschal; `steuerkategorie` S, Z, E, AE (Reverse Charge), K (innergem. Lieferung), G (Export); `typ` 380 Rechnung, 381 Gutschrift |

### Mapping für Altsysteme
Heißen die Spalten Ihres Exports anders, ordnet eine Mapping-Datei sie zu
(Beispiel: [`mapping_altsystem.json`](rechnungsbruecke/beispiele/mapping_altsystem.json)):

```json
{ "_zahlenformat": "de", "rechnungsnummer": "BelegNr", "einzelpreis": "EP netto" }
```

`_zahlenformat`: `de` (1.234,56), `en` (1,234.56) oder `auto`. Bei `auto` werden mehrdeutige Werte wie `1.250`
abgelehnt statt geraten – lieber eine Fehlermeldung als eine Rechnung über den falschen Betrag.

## Hotfolder (ab Tarif Business)

```bash
rechnungsbruecke ueberwachen /pfad/hotfolder --ziel /pfad/ausgabe --stammdaten stammdaten.json --format beide
```

- `*.csv` → Ausgangsrechnungen in `ausgabe/ausgang/`
- `*.xml`, `*.pdf` (eingehende E-Rechnungen) → HTML in `ausgabe/eingang/` + `ausgabe/eingang/buchungsliste.csv`
- Verarbeitete Dateien → `hotfolder/verarbeitet/`, fehlerhafte → `hotfolder/fehler/` mit `.log`
- `--einmal` für einen einzelnen Durchlauf, z. B. per Windows-Aufgabenplanung oder cron

## Prüfung mit den offiziellen Regeln

`pruefen`, `konvertieren` und `ueberwachen` akzeptieren `--regeln ORDNER`. Der Ordner enthält die kompilierten
Schematron-Regeln `EN16931-CII-validation.xsl(t)`, `XRechnung-CII-validation.xsl(t)` und für UBL die
entsprechenden `-UBL-`-Dateien – aus der XRechnung-Konfiguration der KoSIT bzw. den Releases von
CEN/TC 434 (eInvoicing-EN16931). Dazu `pip install ".[offiziell]"` (Saxon-XSLT-Prozessor).
Bei `konvertieren --regeln` wird keine Rechnung geschrieben, die eine fatale Regel verletzt.

## Tarife

| Tarif | Preis (netto) | Rechnungen/Monat | Hotfolder |
|---|---:|---:|:---:|
| Free | 0 € | 25 | – |
| Starter | 39 €/Monat | 300 | – |
| Business | 99 €/Monat | 3.000 | ✓ |
| Unternehmen | 249 €/Monat | unbegrenzt | ✓ |

Lesen und Prüfen eingehender Rechnungen ist in allen Tarifen unbegrenzt. `rechnungsbruecke lizenz` zeigt Tarif und
Verbrauch. Die Lizenzdatei (`~/.rechnungsbruecke/lizenz.json` oder `--lizenz`) ist mit Ed25519 signiert und wird
offline geprüft. Anbieterseitig: [`werkzeuge/lizenz_ausstellen.py`](werkzeuge/lizenz_ausstellen.py) – vor dem
ersten Verkauf ein eigenes Schlüsselpaar erzeugen und den öffentlichen Schlüssel in `rechnungsbruecke/lizenz.py`
eintragen.

## Grenzen (Version 1.0)

- Keine Zu-/Abschläge auf Belegebene und kein strukturiertes Skonto (Skonto als Text in den Zahlungsbedingungen möglich)
- Steuerkategorie „nicht steuerbar“ (O) und Fremdwährungs-Steuerausweis werden nicht unterstützt
- Kein Versand (E-Mail/Peppol) – die Dateien werden über die vorhandenen Wege verschickt
- ZUGFeRD-PDFs werden als PDF/A-3 aufgebaut (eingebettete Schriften, sRGB-OutputIntent, XMP), sind aber noch
  nicht mit veraPDF zertifiziert; das eingebettete XML ist gegen die EN-16931-Regeln geprüft

## Entwicklung

```bash
python3 -m unittest discover tests                    # 37 Tests
RB_REGELN=/pfad/zu/regeln python3 -m unittest discover tests   # inkl. Prüfung gegen offizielle Regeln
```
