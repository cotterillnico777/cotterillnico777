# Krypto-Schatten-Depot

**Separates Beobachtungs-Experiment, nicht Teil des YouTube-Projekts.** Ziel:
über längere Zeit beobachten, ob der Ausbruch nach Kosten bei Krypto wirkt.

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
| Trade nur wenn | Time Machine: Erwartungswert **nach Kosten** positiv (Simulation, bevorzugt auch Rückblick) |
| Max. Verlust pro Trade | 10 $ inklusive Kosten |
| Max. Position | 900 $, 10 % Bargeld-Reserve |
| Menge | Bruchteile erlaubt (z. B. 0,0058 BTC) |
| Pro Tag | max. 3 Trades, max. 30 $ Verlust |
| Einstiege | 9:45 bis 15:30 Uhr New York |
| Glattstellen | spätestens 15:55 Uhr New York |
| Richtung | Long und Short (ab 07.11.2026), eine Position gleichzeitig |
| Handelstage | täglich, auch am Wochenende |

## Kosten (ab dem ersten Tag eingerechnet)

Umgesetzt würde über **Bitget USDT-M Perpetual-Futures mit 1x Hebel** (Long und
Short möglich). Vorsichtig gerechnet, alle Orders als Taker:

| Posten | je Seite |
| --- | --- |
| Taker-Gebühr | 0,06 % |
| Halber Spread + Slippage | 0,02 % (BTC, ETH), 0,05 % (übrige) |
| Funding (pauschal, einmal) | 0,01 % |

Hin und zurück also etwa **0,17 % (BTC, ETH) bis 0,23 %**, rund dreimal so viel
wie bei den Aktien. Der Scan zieht die Kosten in R vom Erwartungswert ab, die
Menge ist so bemessen, dass der Verlust am Stop inklusive Kosten höchstens
10 $ beträgt, und jede Buchung zeigt brutto, Kosten und netto.

Rückblick 3. bis 6.11.: Ohne Kosten hätte es mehrere Trades gegeben (z. B. BTC,
ETH, SOL, BNB short am 5.11.), **nach Kosten kein einziger**. Die Vorteile
waren kleiner als die Gebühren.

Werkzeug: `python3 tools/crypto.py scan`, Buchungen in
`experimente/krypto-portfolio.json`.

## Logbuch

| Tag | Datum | Trades | Ergebnis netto | Kontostand netto |
| --- | --- | --- | --- | --- |
| 0 | Start | – | – | 1.000,00 $ |
| 1 | Sa, 07.11.2026 | 0 (8 Shorts ab 10:00 NY, alle nach Kosten negativ; bestes: AVAX 2R netto −0,145 R. Ruhiger Wochenendmarkt, Kosten 0,2 bis 1,1 R) | 0,00 $ | 1.000,00 $ |
| 2 | So, 08.11.2026 | 0 (Long-Ausbrüche um 9:50 NY bei BTC, ETH, SOL, AVAX, BCH: Stops zu eng oder netto −0,39 bis −0,68 R; bis 11:45 alle zurückgefallen. Bestes Signal: BCH Short 2R netto −0,362 R) | 0,00 $ | 1.000,00 $ |
| 3 | Mo, 09.11.2026 | 0 (8 Long-Ausbrüche um 9:50 NY, 4 zurückgefallen, Rest Kosten 0,44 bis 0,75 R; bis 11:45 bestes Signal BTC Long 2R netto −0,469 R) | 0,00 $ | 1.000,00 $ |
| 4 | Di, 10.11.2026 | 1 (Longs um 10:05 NY alle nach Kosten negativ und danach zurückgefallen; ab 10:30 brachen alle 8 Coins nach unten aus, nur AVAX Short 2R netto knapp positiv; AVAX glattgestellt) | −7,04 $ | 992,96 $ |
| 5 | Mi, 11.11.2026 | 0 (Long-Ausbrüche ab 10:05 NY bei allen 8 Coins, Shorts von SOL, BNB, LTC, BCH zurückgefallen; Kosten 0,16 bis 0,57 R. Bis 11:45 bestes Signal LINK Long 2R netto −0,061 / Rückblick +0,015 R, Simulation negativ) | 0,00 $ | 992,96 $ |
| 6 | Do, 12.11.2026 | 0 (um 9:53 NY kein Ausbruch; Shorts ab 9:55 und Longs ab 11:00 NY fielen fast alle zurück. Bestes Signal: BCH Short 2R netto −0,221 / Rückblick +0,006 R; Kosten 0,23 bis 0,34 R) | 0,00 $ | 992,96 $ |

## Trades

| Datum | Coin | Seite | Einstieg (NY) | Menge | Kurs | Stop | Ziel | EV netto Sim / Rückblick | Ausstieg (NY) | Kurs | Brutto | Kosten | Netto |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10.11.2026 | AVAX | Short | 10:46 | 42,971422 | 8,14 $ | 8,35 $ | 7,71 $ | +0,002 / +0,121 | 15:55 (Glattstellen) | 8,285 $ | −6,23 $ | 0,81 $ | −7,04 $ |
