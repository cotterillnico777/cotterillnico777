# Rechnungsbrücke

**Macht aus dem Rechnungsexport Ihres bestehenden Systems gültige E-Rechnungen – lokal, ohne Cloud, ohne ERP-Wechsel.**

- **Ausgang:** CSV-Export (eine Zeile je Position) → **XRechnung 3.0** (CII-XML) und/oder **ZUGFeRD/Factur-X** (PDF/A-3 mit eingebettetem XML, Profil EN 16931)
- **Eingang:** XRechnung/ZUGFeRD (CII oder UBL, als XML oder PDF) → lesbare HTML-Ansicht + Buchungsliste (CSV)
- **Prüfung:** verständliche Vorprüfung auf Deutsch und **verpflichtend** die Prüfung gegen die offiziellen EN-16931- und XRechnung-Regeln, bevor eine Rechnung geschrieben wird; je Rechnung ein Prüfbericht
- **Grafische Oberfläche** im Browser für die Buchhaltung, ohne Kommandozeile
- **Hotfolder:** Das Altsystem legt CSV-Dateien ab, die Rechnungsbrücke erzeugt automatisch die E-Rechnungen
- Läuft vollständig **on-premises** (Windows, Linux, macOS; Python ≥ 3.10). Rechnungsdaten verlassen das Haus nicht.

Geschäftsmodell und Finanzplan: [`GESCHAEFTSMODELL.md`](GESCHAEFTSMODELL.md).

## Schnellstart

```bash
pip install .
rechnungsbruecke regeln-einrichten validator-configuration-xrechnung.zip   # einmalig, offizielle KoSIT-Regeln
rechnungsbruecke oberflaeche       # grafische Oberfläche im Browser (Arbeitsordner ~/Rechnungsbruecke)
```

Oder per Kommandozeile:

```bash
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
| `kunde_referenz` | für XRechnung ja | Referenz, die **Ihr Kunde** vorgibt: Leitweg-ID bei Behörden, sonst z. B. Bestellzeichen oder Kostenstelle. Nicht Ihre eigene Kunden- oder Rechnungsnummer. |
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

## Grafische Oberfläche

`rechnungsbruecke oberflaeche` startet die Oberfläche im Browser. Sie ist nur auf diesem Rechner erreichbar (127.0.0.1)
und durch einen Sitzungsschlüssel gegen Zugriffe anderer Webseiten geschützt.

- **Rechnungen erstellen:** CSV-Export ablegen, Format wählen, „Prüfen“ (schreibt nichts, verbraucht kein Kontingent),
  dann „E-Rechnungen erzeugen“; Download einzeln oder als ZIP
- **Rechnung lesen:** eingegangene XRechnung/ZUGFeRD ansehen, Rechenkontrolle, zur Buchungsliste hinzufügen
- **Einstellungen:** Firmendaten, Prüfregeln (KoSIT-ZIP auswählen), Lizenz, Spaltenzuordnung für den Export

Arbeitsordner (Standard `~/Rechnungsbruecke`, änderbar mit `--ordner`): `stammdaten.json`, `mapping.json`,
`eingang/` (hochgeladene Exporte), `ausgabe/JJJJ-MM/` (E-Rechnungen und Prüfberichte), `gelesen/`.

## Offizielle Prüfung (Pflicht)

Jede Ausgangsrechnung wird vor dem Schreiben gegen die offiziellen Regeln geprüft: XSD, EN 16931 (CII) und bei
XRechnung zusätzlich die XRechnung-Regeln; auch das XML im ZUGFeRD-PDF. Was eine fatale Regel verletzt, wird nicht
geschrieben. Zu jeder Rechnung entsteht `<nummer>.pruefbericht.json` (Zeitpunkt, Ergebnis, Regelquelle,
Prüfsummen, Beträge) als Nachweis.

Einrichtung einmalig: die XRechnung-Konfiguration der KoSIT (`validator-configuration-xrechnung`, passend zu
XRechnung 3.0) als ZIP herunterladen und `rechnungsbruecke regeln-einrichten <zip>` ausführen (oder in der Oberfläche
unter Einstellungen auswählen). Die Rechnungsbrücke prüft die XRechnung-Version, legt die Regeln mit SHA-256-Prüfsummen
ab und verweigert die Arbeit, wenn Dateien später verändert wurden. `rechnungsbruecke info` zeigt den Stand.

Ohne eingerichtete Regeln werden keine Rechnungen erzeugt. Nur für Tests gibt es `--ohne-offizielle-pruefung`.

## Käuferreferenz (BT-10)

XRechnung verlangt eine Käuferreferenz. Sie wird **vom Kunden vergeben**: bei Behörden die Leitweg-ID, sonst z. B.
das Bestellzeichen. Die Rechnungsbrücke erfindet sie nie, auch nicht aus Rechnungs- oder Kundennummer. Fehlt sie,
wird die XRechnung abgelehnt (ZUGFeRD ist ohne möglich). Leitweg-IDs werden auf ihre Prüfziffer kontrolliert.

## Festgeschriebene Versionen

XRechnung 3.0, ZUGFeRD/Factur-X Profil EN 16931 als PDF/A-3b. Alle Python-Abhängigkeiten sind in `pyproject.toml`
auf die getesteten Versionen festgelegt. Nachweise und externe Prüfung (veraPDF, Mustang):
[`PRUEFPROTOKOLL.md`](PRUEFPROTOKOLL.md), wiederholbar mit `werkzeuge/externe_pruefung.sh`.

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

## Grenzen (Version 1.1)

- Keine Zu-/Abschläge auf Belegebene und kein strukturiertes Skonto (Skonto als Text in den Zahlungsbedingungen möglich)
- Steuerkategorie „nicht steuerbar“ (O) und Fremdwährungs-Steuerausweis werden nicht unterstützt
- Kein Versand (E-Mail/Peppol) – die Dateien werden über die vorhandenen Wege verschickt
- Die Oberfläche ist für einen Arbeitsplatz gedacht (kein Mehrbenutzerbetrieb, keine Anmeldung)

## Entwicklung

```bash
python3 -m unittest discover tests                    # 47 Tests
RB_REGELN=/pfad/zu/regeln python3 -m unittest discover tests   # inkl. Prüfung gegen offizielle Regeln
```
