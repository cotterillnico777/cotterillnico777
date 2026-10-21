# Prüfprotokoll Rechnungsbrücke 1.2.1

Stand: 21.10.2026 · Prüfgegenstand: `beispielausgabe/` (erzeugt aus `rechnungsbruecke/beispiele/rechnungen.csv`, Format „beide“)

## Ergebnis

| Prüfung | Werkzeug / Regelwerk | Ergebnis |
|---|---|---|
| XRechnung-XML (3 Rechnungen) | EN 16931 (CII) + XRechnung 3.0 Schematron, XSD | 0 fatale Befunde |
| ZUGFeRD-XML im PDF (3 Rechnungen) | EN 16931 (CII) Schematron, XSD | 0 fatale Befunde |
| ZUGFeRD-PDF (3 Rechnungen) | **veraPDF 1.28.2**, Profil PDF/A-3b | **PASS** (3/3) |
| ZUGFeRD-PDF (PDF + eingebettetes XML) | **Mustang 2.26.0** (eigene ZUGFeRD-2.5-Regeln, Profil EN 16931) | **VALID** (3/3; z. B. 2.579 PDF/A-Prüfungen, 119 XML-Regeln, 0 Fehler) |
| XRechnung-XML | **Mustang 2.26.0** | **VALID** (3/3) |
| Gegenprobe: PDF ohne PDF/A-Merkmale | veraPDF / Mustang | FAIL / INVALID („XMP Metadata not found“, „Not a PDF/A-3“) – die Prüfung erkennt Fehler |
| Gegenprobe: falsche Summe, fehlende Käuferreferenz, XSD-Verstoß | EN 16931 / XRechnung Schematron | BR-CO-15, BR-DE-15, XSD erkannt (automatische Tests) |

Wiederholen: `werkzeuge/externe_pruefung.sh beispielausgabe/*.pdf beispielausgabe/*.xml`
(lädt veraPDF und Mustang in festgelegten Versionen über Maven).

## Herkunft der verwendeten Prüfregeln – bitte beachten

Die Schematron-Regeln für diesen Lauf stammen **nicht direkt von der KoSIT**, sondern aus einer kompilierten
Kopie im PyPI-Paket `mcp-einvoicing-de` 0.11.4 (XRechnung 3.0, kompiliert 02.09.2026 mit SchXslt), weil
GitHub in der Entwicklungsumgebung nicht erreichbar war. Die Prüfberichte nennen diese Quelle
(`testkopie-aus-pypi-mcp-einvoicing-de-0.11.4.zip`).

Absicherung: Mustang prüft mit einem **unabhängigen** Regelwerk (ZUGFeRD 2.5 von FeRD) und kommt zum
selben Ergebnis.

**Vor dem Produktivbetrieb:** die offizielle XRechnung-Konfiguration der KoSIT herunterladen
(`validator-configuration-xrechnung`, Release für XRechnung 3.0.x), mit
`rechnungsbruecke regeln-einrichten <zip>` einrichten und die Tests mit `RB_REGELN` erneut ausführen.

## Festgeschriebene Versionen

| Komponente | Version |
|---|---|
| XRechnung | 3.0 (`urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0`) |
| ZUGFeRD/Factur-X | Profil EN 16931 (`urn:cen.eu:en16931:2017`), PDF/A-3b, eingebettet als `factur-x.xml` |
| Python-Abhängigkeiten | lxml 6.1.3 · reportlab 5.0.1 · pypdf 6.21.1 · factur-x 7.7 · pillow 13.0.0 · cryptography 50.0.2 · saxonche 13.1.0 |
| Externe Prüfwerkzeuge | veraPDF 1.28.2 · Mustang 2.26.0 |

## Automatische Tests

56 Tests (`python -m unittest discover tests`); 6 davon benötigen die offiziellen Regeln (`RB_REGELN`).
Letzter Lauf (21.10.2026, Linux, Python 3.13): alle bestanden, mit und ohne `RB_REGELN`; Abnahmelauf
`werkzeuge/abnahme.sh` mit der Testkopie bestanden, Gegenprobe mit falscher Regelversion korrekt abgelehnt.

## Eingangsrechnungen (neu in 1.2)

| Fall | Ergebnis |
|---|---|
| gültige UBL-XRechnung | Prüfung bestanden, gebucht |
| dieselbe Datei erneut | „bereits gebucht“, Buchung gesperrt |
| gleiche Rechnungsnummer, andere Datei | Dublettenverdacht, Buchung nur mit Bestätigung |
| gleicher Lieferant, Datum, Betrag, andere Nummer | Dublettenverdacht |
| falsche Gesamtsumme | BR-CO-15/16 + Rechenfehler → Quarantäne, nicht buchbar |
| fehlende Käuferreferenz (XRechnung) | BR-DE-15 → nicht buchbar |
| ZUGFeRD MINIMUM / BASIC WL | als „keine E-Rechnung“ abgelehnt |
| ohne eingerichtete Regeln | „ungeprüft“, nicht buchbar |

## XML-Sicherheit (neu in 1.2.1)

Befund im Review: Saxon löst externe Entities selbst auf (nachgewiesen mit einer XXE-Testdatei). In 1.2.0 war das
nicht ausnutzbar, weil die XSD-Prüfung vorher abbrach – darauf sollte man sich nicht verlassen. Seit 1.2.1 läuft
jedes fremde XML durch `xmlsicher.py`: DOCTYPE/ENTITY werden abgelehnt (auch in UTF-16), Saxon und XSD-Prüfung
erhalten nur neu serialisiertes XML ohne DTD.

| Angriff | Ergebnis |
|---|---|
| XXE (externe Entity auf lokale Datei) | abgelehnt, Quarantäne, kein Dateiinhalt in Bericht oder Meldung |
| XXE in UTF-16 | abgelehnt (zweite Sicherung über `docinfo`) |
| Entity-Expansion („Billion Laughs“) | abgelehnt |

## Lizenzschlüssel

Der Ablauf Schlüssel erzeugen → eintragen → Lizenz ausstellen → vom Programm akzeptiert → Tests → Paketbau wurde
in einer Projektkopie mit einem Wegwerf-Schlüssel geprüft (danach gelöscht). Im Repository steht weiterhin der
Platzhalter; der Paketbau verweigert damit Auslieferungspakete.

## Noch nicht geprüft

- Lauf mit dem **originalen** KoSIT-Paket (`werkzeuge/abnahme.sh`)
- Windows-Paket auf einem sauberen Windows-Rechner (`vertrieb/windows_abnahme.md`); gebaut und inhaltlich geprüft
  (CPython 3.13.16 von NuGet, ausschließlich Windows-Binärdateien), aber nicht unter Windows ausgeführt
- Interoperabilität mit der Buchhaltungssoftware der Pilotkunden (DATEV, Lexware, sevdesk)
