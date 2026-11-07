# Krypto-Schatten-Depot

Eigenes Depot mit **1.000 $ Spielgeld**, getrennt von der Aktien-Challenge.
Kein Broker, keine echten Orders, **keine Anlageberatung**. Kurse von Yahoo
Finance (kostenlos, leicht verzögert), 5-Minuten-Kerzen.

## Regeln (gespiegelt von den Aktien)

| Regel | Wert |
| --- | --- |
| Coins | BTC, ETH, SOL, BNB, LINK, AVAX, LTC, BCH (alle über 5 $) |
| Eröffnungsspanne | 9:30 bis 9:45 Uhr New York (15:30 bis 15:45 Uhr bei uns) |
| Einstieg | erste fertige 5-Minuten-Kerze, die über dem Hoch der Spanne schließt, Kurs hält noch |
| Stop | Mitte der Spanne |
| Ziel | 1× oder 2× Risiko |
| Trade nur wenn | Time Machine: Erwartungswert positiv (Simulation, bevorzugt auch Rückblick) |
| Max. Verlust pro Trade | 10 $ |
| Max. Position | 900 $, 10 % Bargeld-Reserve |
| Menge | Bruchteile erlaubt (z. B. 0,0058 BTC) |
| Pro Tag | max. 3 Trades, max. 30 $ Verlust |
| Einstiege | 9:45 bis 15:30 Uhr New York |
| Glattstellen | spätestens 15:55 Uhr New York |
| Richtung | nur Long (Spot) |
| Handelstage | täglich, auch am Wochenende |

Ergebnisse sind **brutto**. Gebühren (Spot meist etwa 0,1 % pro Seite) und
Spread werden am Ende abgezogen.

Werkzeug: `python3 tools/crypto.py scan`, Buchungen in
`trader/crypto-portfolio.json`.

## Logbuch

| Tag | Datum | Trades | Ergebnis | Kontostand |
| --- | --- | --- | --- | --- |
| 0 | Start | – | – | 1.000,00 $ |

## Trades

| Datum | Coin | Kauf (NY) | Menge | Kurs | Stop | Ziel | EV Sim / Rückblick | Verkauf (NY) | Kurs | Ergebnis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
