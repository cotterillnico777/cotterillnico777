# Tages-Challenge: 1.000 $ Spielgeld

YouTube-Projekt: **7-Tage-Selbstexperiment mit Aktien** (Handelstage 1 bis 7:
Di, 03.11. bis Mi, 11.11.2026). Jeder US-Handelstag ist eine Episode. Gehandelt wird nur auf
dem Papier (Spielgeld, kein Broker verbunden), mit den Trader-Skills in
`.claude/skills/`. Reine Unterhaltung und Bildung, **keine Anlageberatung**.

## Regeln (aus `trader/config.json`)

| Regel | Wert |
| --- | --- |
| Startkapital | 1.000 $ |
| Bargeld-Reserve | immer 10 % (100 $) |
| Max. Verlust pro Trade | 10 $ (1 % des Kontos) |
| Max. Verlust pro Tag | 30 $ |
| Max. Trades pro Tag | 3 |
| Chance/Risiko mindestens | 1 : 1 (Standard-Ziel 2 : 1) |
| Einstiege nur | 9:45 bis 15:30 Uhr New York |
| Alles verkauft bis | 15:55 Uhr New York |
| Nur Long, keine Optionen, kein Hebel, keine Leerverkäufe | ✔ |
| Trade nur bei positivem Erwartungswert in der Time Machine | ✔ (ab Tag 2) |
| … und zwar **nach Kosten** (Spread, Slippage, Gebühren) | ✔ (ab Tag 5) |

Uhrzeiten in Deutschland: US-Börse 15:30 bis 22:00 Uhr; in der Woche nach der
Zeitumstellung in Europa (Ende Oktober) und ein paar Wochen im März eine
Stunde früher.

## Ablauf einer Episode

1. **Vor Börsenstart:** `/trader-scanner` (Pre-Market-Scan) und `/trader-news`
2. **Nach der ersten Viertelstunde:** `/trader-entry` wartet auf den Ausbruch
3. **Plan:** `/trader-exit` setzt Stop und Ziel
4. **Simulation:** `/trader-timemachine` zeigt die Chancen
5. **Größe und Check:** `/trader-budget`, dann `/trader-risk`
6. **Papier-Order:** `/trader-broker` erstellt das Ticket, die Füllung wird zum
   aktuellen Kurs eingetragen
7. **Schluss:** bis 15:55 Uhr glattstellen, Ergebnis ins Logbuch

## Kosten: Umsetzbarkeit ist der Kern

Ab Tag 5 zählt nur, was ein echter Trader auch hätte umsetzen können. Das
Kostenmodell steht in `tools/costs.py` und rechnet vorsichtig, als wären alle
Orders Market- bzw. Stop-Market-Orders:

| Posten | Aktien (Alpaca) | Krypto (Bitget USDT-M-Futures) |
| --- | --- | --- |
| Provision | 0 $ | Taker 0,06 % je Seite |
| Halber Spread + Slippage | 0,03 % je Seite | 0,02 % (BTC, ETH) bzw. 0,05 % je Seite |
| Sonstiges | SEC-Gebühr 0,00278 % und FINRA-TAF beim Verkauf | Funding pauschal 0,01 % |
| Summe Hin und Zurück | etwa 0,06 % | etwa 0,17 bis 0,23 % |

Drei Folgen:

1. **Entscheidung:** Erwartungswert der Simulation minus Kosten in R muss
   positiv sein (`python3 tools/costs.py ev SYM KURS RISIKO EV_SIM EV_RÜCKBLICK`).
   Je enger der Stop, desto teurer der Trade in R.
2. **Logbuch:** Jeder Trade wird brutto **und netto** geführt. Maßgeblich ist
   der Netto-Kontostand.
3. **Tage 1 bis 4 nachgerechnet:** Mit der Netto-Regel wäre MRK an Tag 2 nicht
   gekauft worden (EV +0,039 R brutto, Kosten 0,070 R). Das Ergebnis bleibt
   trotzdem im Logbuch, weil der Trade stattgefunden hat.

| Tag | Trade | Brutto | Kosten | Netto |
| --- | --- | --- | --- | --- |
| 2 | MRK, 6 Stück, 148,62 → 149,95 $ | +7,98 $ | 0,56 $ | +7,42 $ |
| 3 | KDP, 24 Stück, 37,49 → 37,13 $ | −8,64 $ | 0,57 $ | −9,21 $ |
| 4 | NKE, 23 Stück, 38,66 → 38,61 $ | −1,15 $ | 0,56 $ | −1,71 $ |
| 5 | MRNA, 1 Stück, 264,24 → 276,30 $ | +12,06 $ | 0,17 $ | +11,89 $ |
| 5 | FTNT, 4 Stück, 122,93 → 122,46 $ | −1,88 $ | 0,31 $ | −2,19 $ |
| 6 | NXPI, 1 Stück, 260,56 → 261,89 $ | +1,33 $ | 0,16 $ | +1,17 $ |
| 6 | PANW, 1 Stück, 328,92 → 321,01 $ | −7,91 $ | 0,20 $ | −8,11 $ |
| 7 | CBOE, 1 Stück, 369,46 → 369,64 $ | +0,18 $ | 0,23 $ | −0,05 $ |
| 7 | AAPL, 1 Stück, 353,65 → 355,46 $ | +1,81 $ | 0,22 $ | +1,59 $ |
| | **Summe** | **+3,78 $** | **2,98 $** | **+0,80 $** |

## Nebenprojekte (nur Schatten, nicht im Depot)

- [Schatten-Shorts](schatten-shorts.md): Leerverkäufe nach gespiegelten Regeln.

## Logbuch

Eine Datei pro Handelstag: `youtube/tag-NN-YYYY-MM-DD.md`, mit Watchlist,
Trades, Gewinn/Verlust und Kontostand für das Video.

| Tag | Datum | Trades | Ergebnis brutto | Kontostand brutto | Kontostand netto |
| --- | --- | --- | --- | --- | --- |
| 0 | Start | – | – | 1.000,00 $ | 1.000,00 $ |
| [1](tag-01-2026-11-03.md) | Di, 03.11.2026 | 0 (kein Vorteil, später Einstieg) | 0,00 $ | 1.000,00 $ | 1.000,00 $ |
| [2](tag-02-2026-11-04.md) | Mi, 04.11.2026 | 1 (MRK, Ziel erreicht) | +7,98 $ | 1.007,98 $ | 1.007,42 $ |
| [3](tag-03-2026-11-05.md) | Do, 05.11.2026 | 1 (KDP, Stop) | −8,64 $ | 999,34 $ | 998,21 $ |
| [4](tag-04-2026-11-06.md) | Fr, 06.11.2026 | 1 (NKE, Glattstellen) | −1,15 $ | 998,19 $ | 996,50 $ |
| [5](tag-05-2026-11-09.md) | Mo, 09.11.2026 | 2 (MRNA Ziel, FTNT Glattstellen) | +10,18 $ | 1.008,37 $ | 1.006,20 $ |
| [6](tag-06-2026-11-10.md) | Di, 10.11.2026 | 2 (NXPI Glattstellen, PANW Stop) | −6,58 $ | 1.001,79 $ | 999,26 $ |
| [7](tag-07-2026-11-11.md) | Mi, 11.11.2026 | 2 (CBOE, AAPL Glattstellen) | +1,99 $ | 1.003,78 $ | 1.000,80 $ |

## Abschlussbilanz nach 7 Tagen

**Endstand 1.003,78 $ brutto, 1.000,80 $ netto.** 9 Trades, brutto +3,78 $,
Kosten 2,98 $, netto **+0,80 $ (+0,08 %)**. Die Kosten haben fast 80 % des
Bruttogewinns aufgezehrt. Ausführlich mit Lehren in
[Tag 7](tag-07-2026-11-11.md#abschlussbilanz-7-tage-1000--spielgeld).
