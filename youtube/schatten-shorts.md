# Schatten-Shorts: Long vs. Short

Begleitrechnung zur Tages-Challenge. **Nicht im Depot gebucht**, nur zum
Vergleich, wie Leerverkäufe nach denselben Regeln gelaufen wären. Reine
Unterhaltung und Bildung, **keine Anlageberatung**.

## Warum nur im Schatten?

- Leerverkäufe brauchen in den USA ein Margin-Konto mit mindestens 2.000 $
  Eigenkapital. Mit 1.000 $ ginge das in echt nicht.
- Dazu kämen Leihgebühren, und nicht jede Aktie ist leihbar. Beides ist
  hier nicht eingerechnet.

## Regeln (Spiegelbild der Long-Regeln)

| Regel | Long (Depot) | Short (Schatten) |
| --- | --- | --- |
| Signal | 5-Min-Kerze schließt **über** dem Hoch der ersten 15 Minuten | 5-Min-Kerze schließt **unter** dem Tief der ersten 15 Minuten |
| Stop | Mitte der Eröffnungsspanne (darunter) | Mitte der Eröffnungsspanne (darüber) |
| Ziel | 1× oder 2× Risiko darüber | 1× oder 2× Risiko darunter |
| Größe | max. 10 $ Verlust, max. 900 $ Einsatz | gleich |
| Trade nur bei | positivem Erwartungswert nach Kosten (ab Tag 5) | gleich (Time Machine mit `--side sell`) |
| Einstiege | 9:45 bis 15:30 Uhr NY, max. 3 pro Tag | gleich |
| Glattstellen | bis 15:55 Uhr NY | gleich |

Werkzeuge: `tools/short_scan.py` (Scan), `tools/fresh.py --short`
(Nachprüfung), `tools/manage.py` (Stop/Ziel/Glattstellen).

## Logbuch

Startwert zum Vergleich: 1.000,00 $ (Start ab Tag 4).

| Tag | Datum | Trades | Ergebnis brutto | Schatten-Stand brutto | Kosten | Schatten-Stand netto |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | Fr, 06.11.2026 | 1 (CRM, Stop) | −6,98 $ | 993,02 $ | 0,27 $ | 992,75 $ |
| 5 | Mo, 09.11.2026 | 1 (EAT, Stop) | −5,87 $ | 987,15 $ | 0,13 $ | 986,75 $ |

### Schatten-Trades

| Tag | Aktie | Einstieg | Stück | Stop | Ziel | EV Sim. / Rückblick | Ausgang |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | CRM (Salesforce) | Short 213,90 $ um 10:00 Uhr NY | 2 | 217,39 $ | 206,92 $ | +0,109 / +0,286 | Stop in der 10:00-Kerze (Hoch 217,43 $, Schluss 213,65 $): Rückkauf 217,39 $, **−6,98 $** |
| 5 | EAT (Brinker International) | Short 200,37 $ um 9:55 Uhr NY | 1 | 206,24 $ | 188,63 $ | netto +0,067 / +0,159 | Stop in der 15:05-Kerze (Hoch 206,45 $): Rückkauf 206,24 $, brutto **−5,87 $**, Kosten 0,13 $, netto **−6,00 $** |
