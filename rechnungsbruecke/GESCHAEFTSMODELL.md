# Rechnungsbrücke – Geschäftsmodell

**E-Rechnungspflicht ohne ERP-Wechsel: Der vorhandene Rechnungsexport wird lokal zu einer gültigen XRechnung oder ZUGFeRD-Rechnung.**

Stand: 20.10.2026 · Die Zahlen stammen aus [`geschaeft/finanzmodell.py`](geschaeft/finanzmodell.py) und lassen sich mit einem Befehl neu berechnen. Das Produkt selbst ist in diesem Ordner fertig umgesetzt und getestet ([`README.md`](README.md)).

---

## 1. Kurzfassung

| | |
|---|---|
| **Problem** | Ab **01.01.2027** müssen Unternehmen mit mehr als 800.000 € Vorjahresumsatz B2B-Rechnungen als E-Rechnung verschicken, ab **01.01.2028** fast alle. Viele KMU fakturieren mit Branchensoftware, Altsystemen oder Excel, die das nicht können. |
| **Lösung** | Die Rechnungsbrücke nimmt den CSV-Export, den praktisch jedes System erzeugen kann, und macht daraus eine geprüfte XRechnung 3.0 oder ein ZUGFeRD-PDF. Sie läuft lokal, liest auch eingehende E-Rechnungen und erstellt daraus eine Buchungsliste. |
| **Warum wir** | Wir erzeugen die Rechnung **aus Daten**, nicht per KI aus einem PDF wie viele Konkurrenten. Dadurch gibt es keine Lesefehler. Geprüft wird gegen die **offiziellen Regeln** (in Tests über 1.600 EN-16931-Regeln plus BR-DE). Die Software läuft **on-premises**, Rechnungsdaten verlassen das Haus nicht. Die Preise sind transparent, ohne Projektgeschäft. |
| **Erlöse** | Lizenz-Abo in 4 Stufen (0 / 39 / 99 / 249 € netto pro Monat) + Einrichtung (590 €) + Partnerkanal (IT-Systemhäuser, 25 % Provision) |
| **Finanzen (Basis)** | Umsatz J1 19 T€ → J2 125 T€ → **J3 294 T€** · Ergebnis J3 **+116 T€ nach Unternehmerlohn** · dauerhaft profitabel ab **Monat 21** · Kapitalbedarf **≈ 37 T€** |
| **Worst Case** | Bremst man die Kosten rechtzeitig (Szenario „pessimistisch_gegensteuern“), ist das Geschäft trotzdem **ab Monat 14 profitabel**, bei nur ≈ 7 T€ Kapitalbedarf. |
| **Minimalkapital** | Wenn du nur Gehalt entnimmst, was schon verdient ist, und vor dem ersten Umsatz kein Geld für Werbung oder Personal ausgibst, sinkt der Kapitalbedarf auf **unter 1.000 €**. Das gilt im Basis- **und** im pessimistischen Szenario (siehe Kapitel 7a). |
| **Stand** | Version 1.1, bereit für Pilotkunden: grafische Oberfläche, Pflichtprüfung jeder Rechnung mit Prüfbericht, festgeschriebene Versionen, 47 automatische Tests. ZUGFeRD-PDFs extern bestätigt mit veraPDF (PDF/A-3b) und Mustang. Vor dem Produktivbetrieb: offizielle KoSIT-Regeln einrichten ([`PRUEFPROTOKOLL.md`](PRUEFPROTOKOLL.md)). |

---

## 2. Markt und Zeitfenster

**Rechtsrahmen** (Wachstumschancengesetz, § 14 UStG; Stand der Recherche Oktober 2026):

| Seit / ab | Pflicht |
|---|---|
| 01.01.2025 | Alle Unternehmen müssen E-Rechnungen **empfangen** können |
| 01.01.2027 | **Versandpflicht** bei mehr als 800.000 € Gesamtumsatz im Vorjahr |
| 01.01.2028 | Versandpflicht für **alle** Unternehmen im B2B-Inland (Ausnahmen u. a. Kleinbetragsrechnungen bis 250 €) |

> Kleinunternehmer nach § 19 UStG sind laut den meisten Quellen vom *Versand* ausgenommen. Die Quellen widersprechen sich hier aber. Der ZDH fordert außerdem, die Frist für 2027 zu verschieben. Vor dem Start daher mit dem aktuellen BMF-Schreiben abgleichen. Das Geschäftsmodell hängt nicht an Kleinunternehmern.

**Zielkunden**
1. **KMU mit 10–250 Mitarbeitenden und Altsystemen:** Großhandel, Hersteller, Handwerksbetriebe mit älterer Branchensoftware, Hausverwaltungen, Dienstleister mit eigener Fakturierung oder Excel. Sie wollen ihr System nicht wechseln, sondern bis zum Stichtag „einfach compliant“ sein.
2. **IT-Systemhäuser** (Partner): Sie betreuen genau diese Kunden und brauchen eine schnelle Lösung, die sie selbst einrichten und weiterverkaufen können.
3. **Später: Hersteller von Branchensoftware** (OEM): Für sie ist die Rechnungsbrücke ein E-Rechnungs-Export, den sie in ihr Produkt einbauen, statt ihn selbst zu entwickeln.

**Marktgröße** (bewusst vorsichtig, vor dem Start mit der Umsatzsteuerstatistik von Destatis/GENESIS untermauern): In Deutschland gibt es mehrere Hunderttausend Unternehmen über der 800-T€-Schwelle und mehrere Millionen umsatzsteuerpflichtige Unternehmen. Das Basis-Szenario braucht nach 36 Monaten **383 zahlende Kunden**. Das ist ein Promille-Anteil der Zielgruppe. Das Risiko liegt also nicht in der Marktgröße, sondern in der Reichweite. Deshalb ist der Partnerkanal so wichtig.

---

## 3. Wettbewerb und Positionierung

| Alternative | Stärke | Schwäche aus Kundensicht | Unsere Antwort |
|---|---|---|---|
| Komplette Buchhaltungs- oder Rechnungssoftware (sevdesk, Lexware Office, easybill …) | Alles in einem, günstig | Man muss die **Fakturierung umstellen**, Stammdaten migrieren, Prozesse ändern. Für Firmen mit Branchensoftware unrealistisch | Kein Wechsel nötig: Der Export bleibt, wie er ist |
| KI-Konverter PDF → XRechnung (z. B. RechneX, Treesoft PDF2XRechnung) | Arbeiten mit bestehenden PDFs | Ergebnis hängt von Texterkennung ab, Preise oft nur auf Anfrage | **Deterministisch aus Daten** und gegen offizielle Regeln geprüft |
| EDI- und Peppol-Dienstleister | Umfassend, mit Versand | Einrichtungsprojekte, Mindestvolumen, Daten in der Cloud | Selbst in einer Stunde eingerichtet, läuft lokal, Festpreis |
| ERP-Update oder Eigenentwicklung | Passgenau | Teuer, langsam. Viele Altsysteme bekommen kein Update mehr | Ab 39 €/Monat, sofort einsatzbereit |

**Positionierung:** „In einem Tag E-Rechnungs-fähig, ohne Systemwechsel und ohne Cloud.“

---

## 4. Produkt (umgesetzt in Version 1.1)

| Funktion | Nutzen |
|---|---|
| CSV → XRechnung 3.0 (CII) und ZUGFeRD/Factur-X EN 16931 (PDF/A-3 mit eingebettetem XML) | Erfüllt die Versandpflicht. Kund:innen erhalten wie gewohnt ein PDF, ihr System liest automatisch das XML |
| Zuordnung beliebiger Spaltennamen per Mapping, Windows-1252 und deutsches Zahlenformat, Ablehnung mehrdeutiger Zahlen | Funktioniert mit dem vorhandenen Export des Altsystems, ohne Anpassungen dort |
| Vorprüfung mit deutschen Klartext-Meldungen (IBAN-Prüfziffer, Pflichtfelder, Steuerlogik für Reverse Charge, innergemeinschaftliche Lieferung, Kleinunternehmer) | Fehler fallen vor dem Versand auf, nicht erst beim Kunden |
| Pflichtprüfung gegen die offiziellen EN-16931- und XRechnung-Regeln vor jedem Schreiben | Gleiche Prüftiefe wie beim Validator der KoSIT |
| Lesen eingehender E-Rechnungen (CII/UBL, XML/PDF) → HTML + Buchungsliste, mit Rechenkontrolle | Erfüllt die Empfangspflicht und spart das Abtippen in der Buchhaltung |
| Hotfolder für automatischen Betrieb | Vollautomatisch: Das Altsystem exportiert, die E-Rechnung entsteht von selbst |
| Signierte Offline-Lizenzen, Monatskontingente | Lizenzierung ohne Server und ohne Datenabfluss |
| Grafische Oberfläche im Browser (lokal) | Buchhaltung arbeitet ohne Kommandozeile: Export ablegen, prüfen, erzeugen |
| Pflichtprüfung mit Prüfbericht je Rechnung, festgeschriebene Regel- und Bibliotheksversionen | Nachweisbar korrekt: Nichts verlässt das Haus ungeprüft |

**Kosten pro Kunde für uns:** nahezu null. Die Software läuft beim Kunden, wir brauchen keine Server und schließen keinen Auftragsverarbeitungsvertrag, weil wir keine Daten verarbeiten. Variable Kosten sind nur Support (im Modell 4 € je Kunde und Monat) und Zahlungsgebühren.

**Fahrplan:** v1.1 lokale Weboberfläche ✓ · v1.2 Zu- und Abschläge, strukturiertes Skonto · v1.3 Versand per E-Mail und Anbindung an einen Peppol-Zugangspunkt eines Partners · jährlich: Updates auf neue XRechnung-Versionen (im Freelancer-Budget enthalten).

---

## 5. Preise und Erlösmodell

| Tarif | Netto/Monat | Rechnungen/Monat | Für wen |
|---|---:|---:|---|
| Free | 0 € | 25 | Testen, sehr kleine Betriebe, gewinnt neue Kunden |
| Starter | 39 € | 300 | Kleine Betriebe mit wenigen B2B-Kunden |
| Business | 99 € | 3.000 | Typischer Mittelständler, mit Hotfolder |
| Unternehmen | 249 € | unbegrenzt | Mehrere Firmen, hohe Volumen, priorisierter Support |

- **Jahreszahlung** mit 2 Monaten Rabatt. Im Modell ist das als 10 % Abschlag auf den Listenpreis gerechnet.
- **Einrichtung** 590 €: Mapping auf den ERP-Export, Hotfolder einrichten, Testrechnung mit dem Kunden. Im Modell kaufen das 40 % der Neukunden in den Tarifen Business und Unternehmen.
- **Partnerprogramm:** 25 % wiederkehrende Provision für IT-Systemhäuser und Steuerberatungen, die Kunden vermitteln oder betreuen.
- **Zusätzliches Potenzial, nicht im Modell:** OEM-Lizenzen für Hersteller von Branchensoftware (2–10 T€ pro Jahr), Wartungsverträge für Großkunden.

---

## 6. Vertrieb und Markteinführung

### Phase 1 – Start vor dem Stichtag (Nov 2026 – Jan 2027)
- Website mit **kostenlosem Download** (Free-Tarif), Anleitung „In 15 Minuten von CSV zu XRechnung“, Bezahlung per Paddle oder Stripe, Lizenzdatei per E-Mail.
- Suchmaschinen-Content für Suchanfragen mit Kaufabsicht: „CSV in XRechnung umwandeln“, „XRechnung aus Excel“, „ZUGFeRD ohne neue Software“, „E-Rechnungspflicht 2027 Altsystem“.
- Google Ads mit 500 €/Monat auf genau diese Begriffe.
- **10 Pilotkunden** mit kostenloser Einrichtung, im Gegenzug für ein Referenzzitat.

### Phase 2 – Partner aufbauen (Feb – Okt 2027)
- 20 IT-Systemhäuser direkt ansprechen (LinkedIn, regionale IHK-Veranstaltungen). Partner-Kit mit Demo, Preisliste und Einrichtungsanleitung.
- Werbebudget steigt auf 1.200 €/Monat, aber nur solange eine Free-Installation ≤ 25 € kostet.
- Freelancer für Entwicklung (Weboberfläche, Skonto, Pflege der XRechnung-Version).

### Phase 3 – Stichtag 2028 und Ausbau (Nov 2027 – 2029)
- Die Nachfrage steigt vor dem 01.01.2028 deutlich (im Modell 2,0-fach im Nov/Dez 2027).
- Teilzeit-Support ab Monat 13, Gespräche mit Herstellern von Branchensoftware über OEM-Lizenzen.
- Ausbau: Österreich (dort gilt E-Rechnungspflicht für den Bund), Peppol-Versand über einen Partner.

---

## 7. Finanzplan

Vollständige Ergebnisse: [`geschaeft/ergebnisse/zusammenfassung.md`](geschaeft/ergebnisse/zusammenfassung.md), Monatswerte als CSV je Szenario.

| Kennzahl | pessimistisch | pessimistisch, gegengesteuert | **Basis** | optimistisch |
|---|---:|---:|---:|---:|
| Umsatz Jahr 1 (Nov 26 – Okt 27) | 9.854 € | 9.432 € | **19.293 €** | 33.190 € |
| Umsatz Jahr 2 | 55.591 € | 48.307 € | **124.720 €** | 227.110 € |
| Umsatz Jahr 3 | 114.503 € | 94.474 € | **294.107 €** | 539.177 € |
| Ergebnis Jahr 3 (nach Unternehmerlohn) | −42.603 € | 43.293 € | **116.194 €** | 333.243 € |
| Unternehmerlohn über 36 Monate | 111.000 € | 48.000 € | **111.000 €** | 111.000 € |
| Zahlende Kunden Monat 36 | 143 | 117 | **383** | 689 |
| Wiederkehrender Monatsumsatz (MRR) Monat 36 | 10.795 € | 8.843 € | **28.928 €** | 52.126 € |
| Dauerhaft profitabel ab Monat | – | 14 | **21** | 14 |
| Max. Kapitalbedarf | 139.728 € | 7.225 € | **36.530 €** | 13.321 € |
| Kasse nach 36 Monaten (vor Steuern) | −139.728 € | 54.812 € | **88.347 €** | 408.574 € |

**Unit Economics (Basis):** Ø 75,60 € Umsatz je Kunde und Monat · Ø Kundenlebensdauer 40 Monate · LTV 2.773 € · Werbekosten je zahlendem Kunden 400 € · **LTV/CAC 6,9** · Werbekosten nach **5,8 Monaten** wieder eingespielt.

**Wichtigste Annahmen** (in `geschaeft/annahmen.json`, bewusst vorsichtig):
- 40 organische Free-Installationen im ersten Monat, +8 % pro Monat, höchstens 300; mehr Nachfrage vor den Stichtagen
- Nur **6 %** der Free-Installationen werden zahlende Kunden (0,8 % pro Monat, 12 % springen monatlich ab)
- 2,5 % Kündigungen pro Monat; Tarifmix 50 % Starter / 40 % Business / 10 % Unternehmen
- Partnerkanal: 0,5 Neukunden pro Monat (ab Monat 4), steigt auf 4 pro Monat (ab Monat 25)
- Kosten: 3.500 € einmalig (AGB/EULA, Marke, Website), Freelancer Entwicklung 1.500 €/Monat ab Monat 7, Teilzeit-Support ab Monat 13, Unternehmerlohn 2.500 €/Monat ab Monat 7 und 4.500 €/Monat ab Monat 19
- Umsatzmix J3 (Basis): Lizenzen 89 %, Einrichtung 11 %

**Finanzierung:** Für die ≈ 37 T€ Kapitalbedarf im Basis-Szenario kommen Eigenmittel, ein KfW-Gründerkredit oder der Gründungszuschuss infrage. Wer früh auf Unternehmerlohn verzichtet, kommt mit ≈ 7 T€ aus (siehe Szenario mit Gegensteuern).

```bash
python3 geschaeft/finanzmodell.py    # nach Änderung von geschaeft/annahmen.json
```

---

## 7a. Variante mit minimalem Kapital (empfohlen für den Start)

Warum braucht das Basis-Szenario ≈ 37 T€? Das Produkt selbst kostet kaum etwas, es ist schon fertig. Bis zum
tiefsten Kontostand (Monat 20) fließen 87 T€ Umsatz herein. Ausgegeben werden aber **39 T€ Unternehmerlohn,
26 T€ Werbung, 21 T€ Freelancer und 16 T€ Teilzeit-Support**. Dazu kommen nur ≈ 11 T€ unvermeidbare Kosten
(einmalige Einrichtung, Steuerberatung, Versicherung, Tools). Kapital braucht man also nur, weil man Geld
ausgibt, bevor der Umsatz da ist.

**Regeln der Minimalkapital-Variante** (Szenarien `minimalkapital` und `minimalkapital_pessimistisch`):
1. **Gehalt nur aus Gewinn:** Entnommen wird höchstens, was der Monat erwirtschaftet hat (Obergrenze wie im Basis-Szenario).
2. **Kein Personal vor dem Umsatz:** Die Pflege der Software übernimmst du selbst, Teilzeit-Support kommt erst ab Monat 19.
3. **Werbung erst nach den ersten Verkäufen:** Im Basis-Fall ab Monat 7 mit 300 €. Im pessimistischen Fall gar keine Werbung, nur Suchmaschinen-Content und Partner.
4. **Einmalkosten von 500 €:** Markenanmeldung beim DPMA (290 €, online, bis zu drei Klassen), B2B-AGB/EULA aus einem AGB-Generator bzw. einer Vorlage eines Rechtsdienstleisters (Einrichtung ≈ 150 €, danach ≈ 20 €/Monat für Aktualisierungen, in den laufenden Tool-Kosten von 60 €/Monat enthalten), Domain. Steuerberatung zunächst 100 €/Monat. Eine anwaltliche Prüfung der Haftungsklausel (≈ 200–600 €) wird erst aus den ersten Einnahmen bezahlt.

| Kennzahl | Minimalkapital (Basis-Nachfrage) | Minimalkapital (pessimistische Nachfrage) |
|---|---:|---:|
| Max. Kapitalbedarf | **848 €** | **967 €** |
| Dauerhaft profitabel ab Monat | 4 | 4 |
| Umsatz Jahr 1 / 2 / 3 | 15.567 / 107.669 / 270.909 € | 8.274 / 44.798 / 89.352 € |
| Entnommenes Gehalt Jahr 1 / 2 / 3 | 8.438 / 41.576 / 54.000 € | 4.732 / 26.421 / 49.730 € |
| Ergebnis Jahr 3 (nach Gehalt) | 138.644 € | 6.244 € |
| Kasse nach 36 Monaten (vor Steuern) | 160.362 € | 6.292 € |

**Der Preis dafür:** Im ersten Jahr verdienst du kaum Gehalt (≈ 400–700 € pro Monat). Die Variante passt also,
wenn du nebenher angestellt bist, Rücklagen hast oder den Gründungszuschuss bekommst. Das Risiko ist dann
nicht mehr Geld, sondern deine Zeit: etwa 10–15 Stunden pro Woche im ersten Jahr.

---

## 8. Rechtliches und Compliance (Checkliste)

> Orientierung, keine Rechtsberatung. Budget für Kanzlei und Steuerberatung ist im Modell enthalten (3.500 € einmalig).

- [ ] **Marke:** DPMA- und EUIPO-Recherche zu „Rechnungsbrücke“, Domain sichern.
- [ ] **Software-AGB/EULA (B2B)** mit Haftungsbegrenzung: Die Software unterstützt bei der Erstellung, die Verantwortung für den Rechnungsinhalt liegt beim Kunden. Dazu Nutzungsrechte nach Tarif und ein Prüfrecht bei Überschreitung des Kontingents.
- [ ] **IT-/Vermögensschadenhaftpflicht** (im Modell mit 60 €/Monat).
- [ ] **Datenschutz:** Die Software verarbeitet beim Kunden lokal, daher ist kein Auftragsverarbeitungsvertrag nötig. Datenschutzerklärung nur für Website und Shop.
- [ ] **Impressum** (§ 5 DDG), Gewerbeanmeldung. Umsatzsteuer: B2B-Inland mit 19 %, B2B-EU mit Reverse Charge. Der Zahlungsanbieter als Händler (Merchant of Record) vereinfacht das.
- [ ] **Open-Source-Lizenzen:** Die Pflichtabhängigkeiten (factur-x, reportlab, lxml, pypdf, Pillow, cryptography) stehen unter BSD, MIT oder Apache und sind kommerziell nutzbar. Lizenzhinweise mitliefern. Die Lizenz von saxonche (SaxonC-HE, jetzt Pflichtabhängigkeit für die Prüfung) vor der Weitergabe prüfen.
- [ ] **Offizielle Regelwerke** (KoSIT, CEN) werden nicht mitgeliefert. Die Kunden laden sie selbst herunter, oder die Lizenzbedingungen werden vor einer Weitergabe geprüft.
- [ ] **Vor dem ersten Verkauf:** Schlüsselpaar für die Lizenzen erzeugen (`werkzeuge/lizenz_ausstellen.py schluessel`), den privaten Schlüssel sicher und offline aufbewahren.
- [x] **PDF/A-3b** der ZUGFeRD-Ausgabe mit veraPDF 1.28.2 und Mustang 2.26.0 bestätigt ([`PRUEFPROTOKOLL.md`](PRUEFPROTOKOLL.md)).
- [ ] **Offizielle KoSIT-Regeln** einrichten und Prüflauf wiederholen. Testrechnungen mit 3 Pilotkunden und deren Buchhaltungssoftware (DATEV, Lexware, sevdesk) austauschen.

---

## 9. Risiken und Gegenmaßnahmen

| Risiko | Wahrscheinlichkeit | Auswirkung | Gegenmaßnahme |
|---|---|---|---|
| Stichtag wird verschoben (ZDH-Forderung) | mittel | mittel | Die Pflicht ab 2028 für alle bleibt der Haupttreiber. Die Empfangspflicht gilt schon. Die Kosten steigen erst mit dem Umsatz |
| Große Rechnungsprogramme kopieren die Funktion | mittel | mittel | Unsere Nische sind Kunden, die *nicht* wechseln wollen. Partnerkanal und Lösungen für Altsysteme lassen sich schlecht kopieren |
| Haftung für fehlerhafte Rechnungen | gering | hoch | Offizielle Regelprüfung vor dem Schreiben, Ablehnung mehrdeutiger Zahlen, AGB mit Haftungsbegrenzung, Haftpflichtversicherung |
| Neue XRechnung-Versionen (jährlich) | sicher | mittel | Freelancer-Budget für Pflege. Die Regeln sind austauschbar, sodass Prüfungen ohne neues Release aktualisiert werden können |
| Kontingente werden umgangen | mittel | gering | Signierte Lizenzen, Prüfrecht in den AGB. B2B-Kunden halten Lizenzen in der Regel ein |
| Bedienung zu technisch für Fachanwender | mittel | mittel | Grafische Oberfläche (v1.1), Einrichtung als Service, Hotfolder; als Nächstes ein Windows-Installationspaket |
| Reichweite zu gering | mittel | hoch | Stop-/Go-Kriterien (Kapitel 10), Partnerkanal, Kostenbremse im Szenario „gegensteuern“ |

---

## 10. KPIs und Stop-/Go-Kriterien

**Wöchentlich messen:** Free-Installationen nach Kanal · Kosten je Installation · Wechsel von Free zu bezahlt · Kündigungen · aktive Partner · Supportanfragen je Kunde.

| Zeitpunkt | Ziel Basis | Untergrenze (= pessimistisch, gegengesteuert) | Wenn die Untergrenze verfehlt wird |
|---|---|---|---|
| Monat 3 (Jan 2027) | ≈ 95 Installationen pro Monat, erste zahlende Kunden, 10 Piloten | 80 Installationen pro Monat | Positionierung und Suchbegriffe überarbeiten |
| Monat 6 (Apr 2027) | 10 Kunden, 740 € MRR | 5 Kunden | **Gegensteuern:** Werbung auf 300 €, kein Freelancer, Lohn verschieben |
| Monat 12 (Okt 2027) | 42 Kunden, 3.200 € MRR, 10 Partnerkunden | 19 Kunden, 1.450 € MRR | Schwerpunkt ganz auf Partnerkanal und Einrichtung als Service legen |
| Monat 18 (Apr 2028) | 108 Kunden, 8.200 € MRR | 44 Kunden, 3.300 € MRR | Prüfen, ob OEM-Modell (an Softwarehersteller lizenzieren) oder Verkauf des Produkts sinnvoller ist |

---

## 11. 90-Tage-Plan (ab November 2026)

| Woche | Aufgabe | Ergebnis |
|---|---|---|
| 1 | Marke prüfen, Domain, Gewerbe, Lizenzschlüssel erzeugen, AGB/EULA beauftragen | Rechtlich startklar |
| 1–2 | Website mit Download, Anleitung, Preisseite, Paddle/Stripe, automatische Lizenz-E-Mail | Verkaufsfähig |
| 2 | PDF/A mit veraPDF prüfen, Testaustausch mit DATEV, Lexware und sevdesk | Kompatibilität belegt |
| 2–4 | 10 Pilotkunden aus dem eigenen Netzwerk und über IHK-Kontakte, kostenlose Einrichtung | Referenzen und echte Exportformate |
| 3–6 | 8 Suchmaschinen-Artikel, Google Ads mit 500 € | Erste Free-Installationen |
| 6–8 | Mappings der Piloten als Vorlagen veröffentlichen (Sage, Navision, Branchensoftware X) | Einrichtung wird schneller |
| 8–12 | Partner-Kit, 20 IT-Systemhäuser ansprechen, 3 Partnerverträge | Partnerkanal startet |
| 13 | Review gegen die KPIs, Annahmen mit echten Werten aktualisieren, Modell neu rechnen | Entscheidung über Phase 2 |

---

**Quellen zum Rechtsrahmen und Wettbewerb** (Recherche 20.10.2026):
[kostenlose-erechnung.de – Versandpflicht 2027](https://kostenlose-erechnung.de/ratgeber/e-rechnungspflicht-2027-versandpflicht/) ·
[sevdesk – E-Rechnung Update](https://sevdesk.de/blog/e-rechnung-update/) ·
[Taxfix – E-Rechnungspflicht](https://taxfix.de/ratgeber/selbststaendige/e-rechnung-pflicht/) ·
[boerse-express – Pflicht ab 2027/2028](https://www.boerse-express.com/news/articles/e-rechnung-pflicht-ab-2027-fuer-grosse-firmen-2028-fuer-alle-928282) ·
[kostenlose-erechnung.de – lexoffice vs. sevdesk](https://kostenlose-erechnung.de/ratgeber/lexoffice-vs-sevdesk/) ·
[Treesoft PDF2XRechnung](https://treesoft.de/en/software/treesoft-e-invoice-toolkit/pdf2xinvoice-converter) ·
[RechneX](https://www.startbase.com/organization/rechnex/)
