# Abnahme des Windows-Pakets auf einem sauberen Rechner

Vor der Auslieferung an Pilotkunden einmal pro Version durchführen. **Sauber** heißt: frisches Windows 10/11
(64 Bit) ohne installiertes Python, ohne Entwicklerwerkzeuge, mit einem **Standardbenutzer ohne
Administratorrechte**, z. B. eine neue Windows-VM oder Windows-Sandbox (in Windows 11 Pro enthalten).

Paket bauen: `python3 werkzeuge/windows_paket.py` → `dist/Rechnungsbruecke-<version>-windows-x64.zip`
(Prüfsumme in der `.sha256`-Datei daneben).

## Checkliste

| # | Schritt | Erwartet | ✓ |
|---|---|---|---|
| 1 | ZIP auf den Rechner kopieren, Prüfsumme vergleichen: `certutil -hashfile <zip> SHA256` | stimmt mit `.sha256` überein | |
| 2 | ZIP nach `%USERPROFILE%\Rechnungsbruecke-Programm` entpacken (Rechtsklick → Alle extrahieren) | Ordner mit `python\`, zwei `.cmd`-Dateien, `LIESMICH.txt` | |
| 3 | Doppelklick „Rechnungsbruecke starten.cmd“ | ggf. SmartScreen-Warnung → „Trotzdem ausführen“; schwarzes Fenster, Browser öffnet `http://127.0.0.1:8765/` | |
| 4 | Windows-Firewall-Abfrage (falls sie kommt) **ablehnen** | Oberfläche funktioniert trotzdem (nur lokal) | |
| 5 | Kopfzeile | „Prüfregeln fehlen“, „Firmendaten fehlen“, „free: 0 / 25“ | |
| 6 | Einstellungen → Firmendaten eintragen (Werte aus `beispiele\stammdaten.json`) → speichern | „Firmendaten gespeichert.“ | |
| 7 | Einstellungen → Prüfregeln → **originales KoSIT-ZIP** auswählen | „Prüfregeln eingerichtet“, grüner Chip „Prüfregeln XRechnung 3.0“ | |
| 8 | Rechnungen erstellen → `rechnungen.csv` aus dem Beispielordner ablegen → Format „Beides“ → Prüfen | „3 von 3 Rechnungen fehlerfrei“ (Dauer notieren: ____ s) | |
| 9 | E-Rechnungen erzeugen → eine PDF und eine XML herunterladen, ZIP herunterladen | Dateien öffnen sich; PDF zeigt Rechnung mit korrekten Umlauten | |
| 10 | PDF in Adobe Reader öffnen → Büroklammer/Anlagen | Anlage `factur-x.xml` vorhanden | |
| 11 | Rechnung lesen → `tests\daten\ubl_eingang.xml` aus dem Projekt → zur Buchungsliste hinzufügen | „Prüfung bestanden“, danach „Gebucht“ | |
| 12 | dieselbe Datei erneut lesen | „Bereits gebucht“, Buchen gesperrt | |
| 13 | Buchungsliste herunterladen, in Excel öffnen | Umlaute korrekt, eine Zeile je Steuersatz | |
| 14 | Fenster schließen, erneut starten | Firmendaten, Regeln, Zähler „3 / 25“ bleiben erhalten | |
| 15 | „Rechnungsbruecke Kommandozeile.cmd“ → `rechnungsbruecke info` | Versionen und Regelquelle werden angezeigt | |
| 16 | Ordner an anderen Ort verschieben (z. B. `D:\`), erneut starten | startet ohne Fehler | |
| 17 | Optional: Hotfolder mit Business-Testlizenz über Aufgabenplanung (`ueberwachen … --einmal`) | Dateien werden verarbeitet | |

## Ergebnis festhalten

Windows-Version: ______ · Paketversion: ______ · Prüfsumme: ______ · Datum: ______ · geprüft von: ______

Auffälligkeiten (mit Screenshot) als Ticket anlegen. Erst wenn 1–16 bestanden sind, geht das Paket an Pilotkunden.
