# AGENTS.md – Rechnungsbrücke

Hinweise für Coding-Agents (Codex u. a.), die an diesem Projekt arbeiten.

## Was das Projekt ist
Python-Programm, das CSV-Rechnungsexporte bestehender Systeme in E-Rechnungen umwandelt
(XRechnung 3.0 als CII-XML, ZUGFeRD/Factur-X EN 16931 als PDF/A-3) und eingehende E-Rechnungen
(CII/UBL, XML/PDF) lesbar macht. Läuft lokal (on-premises), Lizenzierung über signierte Lizenzdateien.
Geschäftsmodell: `GESCHAEFTSMODELL.md`. Bedienung: `README.md`.

## Aufbau
| Pfad | Inhalt |
|---|---|
| `rechnungsbruecke/modell.py` | Datenmodell und Berechnung nach EN 16931 (Decimal, kaufmännische Rundung) |
| `rechnungsbruecke/cii.py` | CII-XML-Erzeugung; Elementreihenfolge folgt dem XSD, nicht umsortieren |
| `rechnungsbruecke/csv_import.py` | CSV-Import, Mapping, Zahlen-/Datumsformate, Stammdaten |
| `rechnungsbruecke/vorpruefung.py` | Eigene Prüfungen mit deutschen Meldungen |
| `rechnungsbruecke/offiziell.py` | Optionale Prüfung gegen offizielle Schematron-XSLT (saxonche) |
| `rechnungsbruecke/pdf.py` | ZUGFeRD-PDF (reportlab + factur-x), eingebettete Schriften, sRGB-OutputIntent |
| `rechnungsbruecke/leser.py`, `ansicht.py` | Eingangsrechnungen lesen, HTML-Ansicht, Buchungsliste |
| `rechnungsbruecke/verarbeitung.py`, `cli.py` | Konvertierung, Hotfolder, Kommandozeile |
| `rechnungsbruecke/lizenz.py`, `werkzeuge/lizenz_ausstellen.py` | Tarife, Ed25519-Lizenzen, Nutzungszähler |
| `geschaeft/` | Finanzmodell (`annahmen.json` → `finanzmodell.py` → `ergebnisse/`) |
| `website/` | Landingpage (`index.html` im Artifact-Format, `index_standalone.html` zum Hosten) |
| `vertrieb/` | Gesprächsleitfaden für die Validierung |

## Einrichten und prüfen
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[offiziell]" pyflakes
python -m unittest discover tests            # muss grün sein (37 Tests)
python -m pyflakes rechnungsbruecke tests werkzeuge geschaeft
RB_REGELN=/pfad/zu/regeln python -m unittest discover tests   # zusätzlich gegen offizielle Regeln
python geschaeft/finanzmodell.py              # nach Änderungen an geschaeft/annahmen.json
```
Die offiziellen Regeln (EN16931-CII-validation.xsl(t), XRechnung-CII-validation.xsl(t), UBL-Varianten)
liegen nicht im Repository; Quelle: KoSIT validator-configuration-xrechnung bzw. CEN eInvoicing-EN16931.

## Konventionen
- Code, Kommentare, Meldungen und Dokumentation auf **Deutsch**; Bezeichner deutsch (`rechnung`, `pruefe`).
- Geldbeträge immer `Decimal`, nie `float`; Rundung über `modell.runden`.
- Jede fachliche Änderung an der XML-Erzeugung mit den offiziellen Regeln testen (`RB_REGELN`).
- Mehrdeutige Eingaben ablehnen statt raten (Beispiel: Zahl `1.250` ohne festgelegtes Zahlenformat).
- Keine Kundendaten ins Repository; Testdaten mit Fantasienamen.
- Der private Lizenzschlüssel gehört **nie** ins Repository; `OEFFENTLICHER_SCHLUESSEL` in `lizenz.py` ist ein Platzhalter.
- Finanzmodell-Ergebnisse (`geschaeft/ergebnisse/`) werden generiert, nicht von Hand bearbeitet.

## Offene Punkte (Fahrplan)
- v1.1: lokale Weboberfläche für Anwender ohne Kommandozeile
- v1.2: Zu-/Abschläge auf Belegebene, strukturiertes Skonto
- PDF/A-3 der ZUGFeRD-Ausgabe mit veraPDF bestätigen
- Website: Kontaktadresse, Impressum/Datenschutz/AGB, Fonts selbst hosten (siehe `website/README.md`)
