# Abschlussbericht: 7 Tage, 1.000 $ Spielgeld, 9 Trades

**YouTube-Selbstexperiment mit Aktien, Di 03.11. bis Mi 11.11.2026.**
Gehandelt wurde nur auf dem Papier, also mit Spielgeld und ohne Broker. Das
ist reine Unterhaltung und Bildung, **keine Anlageberatung**.

---

## Auf einen Blick

| | Brutto | Kosten | **Netto** |
| --- | --- | --- | --- |
| Start | 1.000,00 $ | | 1.000,00 $ |
| Ergebnis nach 9 Trades | +3,78 $ | 2,98 $ | **+0,80 $** |
| **Endstand** | 1.003,78 $ | | **1.000,80 $ (+0,08 %)** |

- **9 Trades** an 6 von 7 Handelstagen. An Tag 1 gab es keinen Trade.
- **Ausgänge:** 2× Ziel erreicht, 2× Stop, 5× zum Handelsschluss glattgestellt.
- **Netto:** 4 Gewinner, 5 Verlierer.
- **Größter Gewinn:** MRNA, +11,89 $. **Größter Verlust:** KDP, −9,21 $.
- **Limits:** Das Verlustlimit von 10 $ pro Trade hat jedes Mal gehalten. Kein
  Tag kam in die Nähe des Tageslimits von 30 $.
- **Kosten:** Sie haben **fast 80 % des Bruttogewinns** aufgezehrt.

---

## Die Regeln

| Regel | Wert |
| --- | --- |
| Strategie | Ausbruch aus der Eröffnungsspanne (erste 15 Minuten), nur Long |
| Einstieg | erste fertige 5-Minuten-Kerze, die über dem Hoch der Spanne schließt |
| Stop | Mitte der Eröffnungsspanne |
| Ziel | 1× oder 2× Risiko |
| Trade nur wenn | die Time Machine einen positiven Erwartungswert zeigt (ab Tag 2), **nach Kosten** (ab Tag 5) |
| Max. Verlust | 10 $ pro Trade, 30 $ pro Tag, höchstens 3 Trades pro Tag |
| Position | höchstens 900 $, immer 10 % Bargeld-Reserve |
| Zeiten | Einstiege von 9:45 bis 15:30 Uhr New York, alles verkauft bis 15:55 Uhr |

**Time Machine:** Für jeden Kandidaten spielt sie den Rest des Handelstags
10.000-mal durch. Grundlage sind die 5-Minuten-Kerzen der Aktie aus den
letzten 60 Tagen. Dazu rechnet sie dieselbe Regel auf jedem vergangenen Tag
nach („Rückblick“). Das Ergebnis ist der Erwartungswert in R
(1 R = Risiko pro Aktie).

**Kostenmodell (ab Tag 5):** Hin und zurück kostet ein Trade etwa 0,06 %
(Spread, Slippage, SEC- und FINRA-Gebühr). Vorher habe ich ohne Kosten
gerechnet. Die Kosten für die Tage 2 bis 4 sind nachträglich ergänzt.

---

## Tag für Tag

| Tag | Datum | Trades | Brutto | Kosten | Netto | Stand brutto | Stand netto |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Di, 03.11. | – (kein Vorteil, später Einstieg) | 0,00 $ | 0,00 $ | 0,00 $ | 1.000,00 $ | 1.000,00 $ |
| 2 | Mi, 04.11. | MRK (Ziel) | +7,98 $ | 0,56 $ | +7,42 $ | 1.007,98 $ | 1.007,42 $ |
| 3 | Do, 05.11. | KDP (Stop) | −8,64 $ | 0,57 $ | −9,21 $ | 999,34 $ | 998,21 $ |
| 4 | Fr, 06.11. | NKE (Glattstellen) | −1,15 $ | 0,56 $ | −1,71 $ | 998,19 $ | 996,50 $ |
| 5 | Mo, 09.11. | MRNA (Ziel), FTNT (Glattstellen) | +10,18 $ | 0,48 $ | +9,70 $ | 1.008,37 $ | 1.006,20 $ |
| 6 | Di, 10.11. | NXPI (Glattstellen), PANW (Stop) | −6,58 $ | 0,36 $ | −6,94 $ | 1.001,79 $ | 999,26 $ |
| 7 | Mi, 11.11. | CBOE, AAPL (beide Glattstellen) | +1,99 $ | 0,45 $ | +1,54 $ | 1.003,78 $ | 1.000,80 $ |
| | **Summe** | **9 Trades** | **+3,78 $** | **2,98 $** | **+0,80 $** | | |

Höchster Stand netto: 1.007,42 $ nach Tag 2. Tiefster Stand netto: 996,50 $
nach Tag 4.

---

## Alle 9 Trades

Uhrzeiten in New York, bei uns 6 Stunden später.

| # | Tag | Aktie | Einstieg | Stück × Kurs | Stop | Ziel | Erwartungswert Sim. / Rückblick | Ausstieg | Brutto | Kosten | **Netto** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | **MRK** (Merck) | 12:40 | 6 × 148,62 $ | 147,29 $ | 149,95 $ (1R) | +0,039 / −0,053 ¹ | 15:35, **Ziel** 149,95 $ | +7,98 $ | 0,56 $ | **+7,42 $** |
| 2 | 3 | **KDP** (Keurig Dr Pepper) | 11:25 | 24 × 37,49 $ | 37,13 $ | 38,21 $ (2R) | +0,117 / +0,346 ¹ | 12:10, **Stop** 37,13 $ | −8,64 $ | 0,57 $ | **−9,21 $** |
| 3 | 4 | **NKE** (Nike) | 10:00 | 23 × 38,66 $ | 38,28 $ | 39,42 $ (2R) | +0,075 / +0,230 ¹ | 15:55, Glattstellen 38,61 $ | −1,15 $ | 0,56 $ | **−1,71 $** |
| 4 | 5 | **MRNA** (Moderna) | 9:55 | 1 × 264,24 $ | 258,21 $ | 276,30 $ (2R) | +0,191 / +0,131 | 11:25, **Ziel** 276,30 $ | +12,06 $ | 0,17 $ | **+11,89 $** |
| 5 | 5 | **FTNT** (Fortinet) | 10:00 | 4 × 122,93 $ | 120,78 $ | 127,23 $ (2R) | +0,012 / +0,191 | 15:55, Glattstellen 122,46 $ | −1,88 $ | 0,31 $ | **−2,19 $** |
| 6 | 6 | **NXPI** (NXP Semiconductors) | 10:00 | 1 × 260,56 $ | 253,59 $ | 274,50 $ (2R) | +0,133 / +0,102 | 15:55, Glattstellen 261,89 $ | +1,33 $ | 0,16 $ | **+1,17 $** |
| 7 | 6 | **PANW** (Palo Alto Networks) | 10:00 | 1 × 328,92 $ | 321,01 $ | 344,74 $ (2R) | +0,035 / +0,122 | 12:20, **Stop** 321,01 $ | −7,91 $ | 0,20 $ | **−8,11 $** |
| 8 | 7 | **CBOE** (Cboe Global Markets) | 9:55 | 1 × 369,46 $ | 363,92 $ | 375,00 $ (1R) | +0,062 / +0,138 | 15:55, Glattstellen 369,64 $ | +0,18 $ | 0,23 $ | **−0,05 $** |
| 9 | 7 | **AAPL** (Apple) | 9:55 | 1 × 353,65 $ | 351,38 $ | 358,19 $ (2R) | +0,043 / +0,250 | 15:55, Glattstellen 355,46 $ | +1,81 $ | 0,22 $ | **+1,59 $** |
| | | | | | | | | **Summe** | **+3,78 $** | **2,98 $** | **+0,80 $** |

¹ Tage 2 bis 4: Erwartungswert noch **ohne** Kosten. Ab Tag 5 sind die Werte
nach Kosten gerechnet. Mit der Kostenregel wäre MRK nicht gekauft worden:
+0,039 R brutto, aber 0,070 R Kosten.

---

## Die 5 wichtigsten Erkenntnisse

1. **Umsetzbarkeit entscheidet.** Brutto +3,78 $, netto nur +0,80 $. Ohne
   Kosten sähe die Strategie fast fünfmal so gut aus, wie sie wirklich ist.
2. **Die Regeln schützen, machen aber nicht reich.** Es gab keinen großen
   Verlusttag, aber auch keinen klaren Vorteil. Nach 7 Tagen steht die
   Challenge praktisch bei null.
3. **Knappe Kandidaten verlieren.** FTNT (+0,012 R), PANW (+0,035 R) und CBOE
   hatten wenig Abstand zu den Kosten und brachten zusammen −10,35 $. Die
   klaren Kandidaten MRNA und NXPI kamen auf +13,06 $. Der nächste Test wäre
   eine Mindestschwelle, z. B. netto > +0,05 R.
4. **Ein Ziel von 2× Risiko ist schwer.** Von 7 Trades mit 2R-Ziel hat nur
   MRNA das Ziel erreicht. Insgesamt endeten fünf Trades zum Handelsschluss ohne Stop
   und ohne Ziel.
5. **7 Tage sind statistisch nichts.** 9 Trades zeigen Tendenzen, beweisen
   aber nichts, weder in die eine noch in die andere Richtung.

---

## Bonus: Schatten-Shorts (nicht im Depot)

Leerverkäufe nach gespiegelten Regeln, nur mitgerechnet. Mit 1.000 $ wären
sie in echt nicht möglich, dafür braucht man ein Margin-Konto ab 2.000 $.

| Tag | Aktie | Einstieg | Ausgang | Brutto | Kosten | Netto |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | CRM | Short 2 × 213,90 $ | Stop 217,39 $ | −6,98 $ | 0,27 $ | −7,25 $ |
| 5 | EAT | Short 1 × 200,37 $ | Stop 206,24 $ | −5,87 $ | 0,13 $ | −6,00 $ |
| 6 | GIS | Short 19 × 34,15 $ | Stop 34,64 $ | −9,31 $ | 0,41 $ | −9,72 $ |
| 7 | SOFI | Short 39 × 16,43 $ | Glattstellen 16,265 $ | +6,43 $ | 0,41 $ | +6,03 $ |
| | **Summe** | | | **−15,73 $** | **1,22 $** | **−16,94 $** |

Im selben Zeitraum (Tag 4 bis 7) kamen die Longs netto auf +2,59 $. Gegen die
Shorts lagen sie damit um 19,53 $ vorne. Drei von vier Shorts wurden durch
kurze Kursspitzen nach oben ausgestoppt.

---

## Vorschlag für den Video-Ablauf

1. **Hook (0:00):** „7 Tage, 9 Trades, 1.000 $ – am Ende 80 Cent Gewinn.
   Und warum das ein ehrliches Ergebnis ist.“
2. **Setup (0:30):** Regeln, Spielgeld, die Time Machine in einem Satz.
3. **Tag 1 (1:30):** Kein Trade. Warum Nichtstun auch eine Entscheidung ist.
4. **Achterbahn (2:30):** MRK an Tag 2 (+1,14 $ → −2,04 $ → Ziel) und KDP an
   Tag 3 (Stop nach 45 Minuten).
5. **Wendepunkt (4:00):** Die Kosten kommen dazu. „Was hätte ein echter
   Trader bezahlt?“
6. **Highlight (5:00):** MRNA trifft an Tag 5 das Ziel in 90 Minuten
   (+11,89 $).
7. **Rückschlag (6:00):** PANW an Tag 6, Stop in der 12:20-Kerze. Long und
   Schatten-Short werden in derselben Kerze ausgestoppt.
8. **Finale (7:00):** Tag 7, CBOE ist brutto im Plus und netto im Minus. Das
   ist die Kostenlücke im Kleinen.
9. **Bilanz (8:00):** Tabelle „Tag für Tag“ und Kurve brutto gegen netto.
10. **Lehren und Ausblick (9:00):** die 5 Erkenntnisse und was ich als
    Nächstes testen würde (Mindestschwelle, Limit-Orders).

**Grafik-Ideen**

- Kontostand-Kurve über 7 Tage als zwei Linien, brutto und netto. Die
  Fläche dazwischen sind die Kosten.
- Balken pro Trade (grün und rot), sortiert nach Erwartungswert. Sie zeigen:
  Je knapper der Erwartungswert, desto eher ein Verlust.
- Kuchendiagramm der Ausgänge: Ziel 2, Stop 2, Glattstellen 5.

---

Details zu jedem Tag stehen in den Logbüchern [Tag 1](tag-01-2026-11-03.md)
bis [Tag 7](tag-07-2026-11-11.md). Die Schatten-Shorts sind in
[schatten-shorts.md](schatten-shorts.md) beschrieben.
