# Krypto-Schatten-Depot

Eigenes Depot mit **1.000 $ Spielgeld**, getrennt von der Aktien-Challenge.
Kein Broker, keine echten Orders, **keine Anlageberatung**. Kurse von Yahoo
Finance (kostenlos, leicht verzögert), 5-Minuten-Kerzen.

## Regeln (gespiegelt von den Aktien)

| Regel | Wert |
| --- | --- |
| Coins | BTC, ETH, SOL, BNB, LINK, AVAX, LTC, BCH (alle über 5 $) |
| Eröffnungsspanne | 9:30 bis 9:45 Uhr New York (15:30 bis 15:45 Uhr bei uns) |
| Einstieg Long | erste fertige 5-Minuten-Kerze, die über dem Hoch der Spanne schließt, Kurs hält noch |
| Einstieg Short | erste fertige 5-Minuten-Kerze, die unter dem Tief der Spanne schließt, Kurs hält noch |
| Stop | Mitte der Spanne, mindestens 0,2 % vom Einstieg entfernt |
| Ziel | 1× oder 2× Risiko |
| Trade nur wenn | Time Machine: Erwartungswert positiv (Simulation, bevorzugt auch Rückblick) |
| Max. Verlust pro Trade | 10 $ |
| Max. Position | 900 $, 10 % Bargeld-Reserve |
| Menge | Bruchteile erlaubt (z. B. 0,0058 BTC) |
| Pro Tag | max. 3 Trades, max. 30 $ Verlust |
| Einstiege | 9:45 bis 15:30 Uhr New York |
| Glattstellen | spätestens 15:55 Uhr New York |
| Richtung | Long und Short (ab 07.11.2026), eine Position gleichzeitig |
| Handelstage | täglich, auch am Wochenende |

Ergebnisse sind **brutto**. Gebühren (meist etwa 0,02 bis 0,1 % pro Seite) und
Spread werden am Ende abgezogen.

Shorts gibt es bei Krypto nur über Futures oder Margin. Dort kommen
Finanzierungsgebühren (Funding) hinzu, die wir hier nicht mitrechnen. Ein
Short bindet im Schatten-Depot so viel Bargeld wie ein Long gleicher Größe.

Werkzeug: `python3 tools/crypto.py scan`, Buchungen in
`trader/crypto-portfolio.json`.

## Logbuch

| Tag | Datum | Trades | Ergebnis | Kontostand |
| --- | --- | --- | --- | --- |
| 0 | Start | – | – | 1.000,00 $ |

## Trades

| Datum | Coin | Seite | Einstieg (NY) | Menge | Kurs | Stop | Ziel | EV Sim / Rückblick | Ausstieg (NY) | Kurs | Ergebnis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
