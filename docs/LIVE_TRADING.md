# Paper, Forward-Vergleich und Live

## Modi

| Modus | Wie | Geld |
|---|---|---|
| BACKTEST | `quantbot backtest` / `research` | keins |
| PAPER (Standard) | `quantbot run` | simuliertes Konto, echte Kurse |
| LIVE | nur mit **allen drei**: `live.enabled: true` in der YAML, `TRADING_MODE=live` und `QUANTBOT_LIVE_CONFIRM=I_ACCEPT_REAL_MONEY_RISK` | echt |

LIVE wird von keinem Befehl und keiner Prüfung automatisch aktiviert – auch nicht von
`readiness`, wenn alles grün ist.

## API-Schlüssel

- Nur in `.env` (liegt in `.gitignore`), Vorlage: `.env.example`:
  `QUANTBOT_API_KEY`, `QUANTBOT_API_SECRET`, ggf. `QUANTBOT_API_PASSWORD`.
- Rechte: **nur Futures-Handel. Keine Auszahlungen.** IP-Beschränkung empfohlen.
- Schlüssel werden nie geloggt (Log-Filter ersetzt Werte aus der Umgebung) und nicht angezeigt.
- Für Daten und Paper sind keine Schlüssel nötig.

## Paper Trading

`python -m quantbot -c my.yaml run --mode paper` pollt alle 30 s, handelt nur auf
abgeschlossenen Kerzen und schreibt alles ins SQLite-Journal (Signale, Orders, Fills,
Trades, Equity, Positionen, Ereignisse, Heartbeat). Neustart setzt den Zustand fort.

Empfohlen: mindestens 30 Tage und 20 Trades. `status` zeigt den aktuellen Zustand,
`analyze --journal ...` die Auswertung.

## Backtest vs. Forward

`quantbot compare --journal state/quantbot.sqlite` rechnet einen Backtest über exakt den
Paper-Zeitraum und vergleicht:

- **Signal-Drift:** Anteil identischer Signale (Ziel ≥ 95 %; Abweichung = Daten- oder Codefehler)
- **Trades:** Anzahl Paper vs. Backtest, zugeordnete Paare
- **Slippage-Lücke:** Einstiegspreis Paper vs. Backtest in bps (Ziel ≤ 15 bps)
- **Rendite und Gebühren:** Differenz (Ziel ≤ ±5 Prozentpunkte)

## Live-Readiness

`quantbot readiness --research .../results.json --journal ... --forward ...` prüft:
Forschung bestanden (gleiche Parameter, echte Daten), Paper-Dauer und -Trades, keine
kritischen Ereignisse, Kill Switch nicht ausgelöst, Heartbeat, Forward-Abweichungen,
konservative Risikoeinstellungen, Schlüssel gesetzt. Manuell: Schlüssel ohne
Auszahlungsrecht, verkraftbares Startkapital.

## Übergang zu Live (manuell)

1. Readiness vollständig grün, manuelle Punkte erledigt.
2. Kleines Kapital; `risk_per_trade` zunächst halbieren.
3. Die drei Freigaben setzen, `quantbot run --mode live`.
4. Erste Wochen täglich `status` und `compare` gegen den Backtest.
5. Notbremse: `quantbot kill` oder Datei `STOP`.
