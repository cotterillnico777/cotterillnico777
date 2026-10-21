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
| `rechnungsbruecke/standards.py` | Festgeschriebene Versionen (XRechnung 3.0, ZUGFeRD-Profil) |
| `rechnungsbruecke/regeln.py` | Einrichtung der offiziellen Prüfregeln (KoSIT-ZIP), Manifest mit SHA-256, Versionsprüfung |
| `rechnungsbruecke/offiziell.py` | Pflichtprüfung gegen XSD + Schematron (saxonche), kompilierte Regeln im Cache |
| `rechnungsbruecke/pdf.py` | ZUGFeRD-PDF (reportlab + factur-x), eingebettete Schriften, sRGB-OutputIntent |
| `rechnungsbruecke/leser.py`, `ansicht.py` | Eingangsrechnungen lesen (CII/UBL), HTML-Ansicht, Buchungsliste |
| `rechnungsbruecke/eingang.py` | Eingang: offizielle Prüfung, Buchungsfreigabe, Dublettenregister, Quarantäne |
| `rechnungsbruecke/verarbeitung.py`, `cli.py` | Konvertierung mit Pflichtprüfung und Prüfbericht, Hotfolder, Kommandozeile |
| `rechnungsbruecke/oberflaeche.py`, `oberflaeche.html` | Lokale Browser-Oberfläche (127.0.0.1, Token + Host-Prüfung) |
| `rechnungsbruecke/lizenz.py`, `werkzeuge/lizenz_ausstellen.py` | Tarife, Ed25519-Lizenzen, Nutzungszähler |
| `werkzeuge/` | `abnahme.sh` (Abnahme mit KoSIT-Regeln), `externe_pruefung.sh` (veraPDF, Mustang), `windows_paket.py`, `lizenz_ausstellen.py` |
| `geschaeft/` | Finanzmodell (`annahmen.json` → `finanzmodell.py` → `ergebnisse/`) |
| `website/` | Landingpage (`index.html` im Artifact-Format, `index_standalone.html` zum Hosten) |
| `vertrieb/` | Gesprächsleitfaden für die Validierung |

## Einrichten und prüfen
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e . pyflakes
python -m unittest discover tests            # muss grün sein (52 Tests)
python -m pyflakes rechnungsbruecke tests werkzeuge geschaeft
RB_REGELN=/pfad/zu/regeln python -m unittest discover tests   # zusätzlich gegen offizielle Regeln
python geschaeft/finanzmodell.py              # nach Änderungen an geschaeft/annahmen.json
werkzeuge/externe_pruefung.sh beispielausgabe/*.pdf beispielausgabe/*.xml   # veraPDF + Mustang vor jedem Release
```
Die offiziellen Regeln (EN16931-CII-validation.xsl(t), XRechnung-CII-validation.xsl(t), UBL-Varianten)
liegen nicht im Repository; Quelle: KoSIT validator-configuration-xrechnung bzw. CEN eInvoicing-EN16931.

## Konventionen
- Code, Kommentare, Meldungen und Dokumentation auf **Deutsch**; Bezeichner deutsch (`rechnung`, `pruefe`).
- Geldbeträge immer `Decimal`, nie `float`; Rundung über `modell.runden`.
- Jede fachliche Änderung an der XML-/PDF-Erzeugung mit den offiziellen Regeln (`RB_REGELN`) und `werkzeuge/externe_pruefung.sh` prüfen.
- Die offizielle Prüfung nie still abschalten; `--ohne-offizielle-pruefung` ist nur für Tests.
- Die Käuferreferenz (BT-10) nie selbst befüllen; sie kommt vom Kunden.
- Eingangsrechnungen nur nach bestandener Prüfung buchen; Fehlerfälle in die Quarantäne, Dubletten nur mit Bestätigung.
- Abhängigkeiten sind exakt gepinnt; Updates nur mit vollständigem Prüflauf (siehe `PRUEFPROTOKOLL.md`).
- Mehrdeutige Eingaben ablehnen statt raten (Beispiel: Zahl `1.250` ohne festgelegtes Zahlenformat).
- Keine Kundendaten ins Repository; Testdaten mit Fantasienamen.
- Der private Lizenzschlüssel gehört **nie** ins Repository; `OEFFENTLICHER_SCHLUESSEL` in `lizenz.py` ist ein Platzhalter.
- Finanzmodell-Ergebnisse (`geschaeft/ergebnisse/`) werden generiert, nicht von Hand bearbeitet.

## Offene Punkte
Status: GO für kontrollierte Pilotkunden, NO-GO für breiten Verkauf. **Keine neuen Features vor den Pilotergebnissen.**

Vor dem ersten produktiven Pilot (P0):
- `werkzeuge/abnahme.sh` mit dem originalen KoSIT-Paket ausführen, Archiv aufbewahren (bisher Testkopie aus PyPI, siehe `PRUEFPROTOKOLL.md`)
- Windows-Paket nach `vertrieb/windows_abnahme.md` auf sauberem Rechner abnehmen

Nach dem Pilot, je nach Rückmeldung:
- Zu-/Abschläge auf Belegebene, strukturiertes Skonto
- Lizenzkontrolle härten (signierter Zähler, optionale Online-Aktivierung), Code-Signatur für Windows
- Website: Kontaktadresse, Impressum/Datenschutz/AGB, Fonts selbst hosten (siehe `website/README.md`)
