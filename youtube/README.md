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
| | **Summe** | **−1,81 $** | **1,69 $** | **−3,50 $** |

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
