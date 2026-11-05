# Tages-Challenge: 1.000 $ Spielgeld

YouTube-Projekt: Jeder US-Handelstag ist eine Episode. Gehandelt wird nur auf
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

## Gebühren und Spread

Die Tagesergebnisse im Logbuch sind **brutto**. Gebühren und Spread werden
am Ende der Challenge für alle Trades zusammen abgezogen. Dafür steht bei
jedem Trade: Stückzahl, Kauf- und Verkaufskurs und Uhrzeit.

## Logbuch

Eine Datei pro Handelstag: `youtube/tag-NN-YYYY-MM-DD.md`, mit Watchlist,
Trades, Gewinn/Verlust und Kontostand für das Video.

| Tag | Datum | Trades | Ergebnis | Kontostand |
| --- | --- | --- | --- | --- |
| 0 | Start | – | – | 1.000,00 $ |
| [1](tag-01-2026-11-03.md) | Di, 03.11.2026 | 0 (kein Vorteil, später Einstieg) | 0,00 $ | 1.000,00 $ |
| [2](tag-02-2026-11-04.md) | Mi, 04.11.2026 | 1 (MRK, Ziel erreicht) | +7,98 $ | 1.007,98 $ |
