# Architektur

```
quantbot/
  core/         Zeitrahmen, Typen (Order, Fill, Intent, Position ...)
  config/       Schema mit konservativen Defaults, YAML + .env, Modus-Auflösung (LIVE-Sperre)
  data/         Download (nur abgeschlossene Kerzen), Validierung, Speicher mit Hash, Resampling
  indicators/   ATR, RSI, ADX, Donchian (Vorperiode), Bollinger, Z-Score, VWAP, Vola, Perzentil
  strategies/   17 Strategien, alle mit gleicher Schnittstelle (signal, stop_distance, take_profit)
  regimes/      Bull/Bear/Seitwärts × hohe/normale/niedrige Vola aus abgeschlossenen Tageskerzen
  risk/         zentrale Risk Engine (Größe, Hebel, Limits, Kill Switch, Korrelation)
  portfolio/    Konto (Cross Margin, Liquidation), Kovarianz, Strategie-Allokation
  backtesting/  Ereignis-Engine, Kostenmodell, Metriken, Metadaten
  research/     Splits, Walk-Forward, Sensitivität, Stress, Monte Carlo, ML-Prüfung, Bericht, Forward-Vergleich
  execution/    Execution Engine (idempotent), Trade-Ledger, Trader-Schleife (Paper/Live)
  exchanges/    Adapter-Interface, ccxt-Futures-Adapter, simulierte Börse (Paper)
  analytics/    Auswertungen nach Strategie/Asset/Regime/Stunde/Hebel, Drawdown-Analyse
  monitoring/   JSON-Logs mit Geheimnis-Filter, SQLite-Journal, Status, Readiness
  cli.py        python -m quantbot ...
tests/v2/       Tests je Phase
```

## Datenfluss

```
Daten -> Strategien (Signal + Stop-Abstand je Kerze) -> Regime-Filter -> Allokation
      -> Risk Engine (Zielpositionen) -> Backtest-Engine  |  Execution Engine -> Börse/Paper
                                                         -> Journal -> Analytics / Forward-Vergleich
```

Backtest, Paper und Live verwenden **dieselben** Strategie-, Regime-, Allokations- und
Risk-Klassen sowie dasselbe Kontomodell. Paper unterscheidet sich nur durch den Adapter
(`SimulatedExchange`); dadurch misst der Forward-Vergleich echte Abweichungen und nicht
Unterschiede im Code.

## Schutz vor Lookahead und Leakage

- Signal auf Kerze t wird frühestens zum Open von t+1 (+ optional Verzögerung) ausgeführt.
- Indikatoren nutzen nur Vergangenheit (z. B. Donchian über die Vorperiode).
- Höhere Zeitrahmen (MTF, Regime aus Tageskerzen) werden erst nach Abschluss der Kerze sichtbar.
- Funding wird über seine Ereignis-Zeitstempel ausgerichtet, nicht über Kerzen-Indizes.
- **Präfix-Test** für jede Strategie, das Regime-Modul und die Engine: Ergebnis auf den
  ersten n Kerzen muss identisch sein, egal ob Daten danach existieren.
- Stop vor Take-Profit innerhalb einer Kerze; Lücken werden zum Open gefüllt.
- Out-of-Sample wird genau einmal am Ende ausgewertet und für keine Auswahl genutzt.
- Das ML-Modell wird nur auf dem Train-Zeitraum geschätzt und auf Validation bewertet.

## Ausfallsicherheit

- Client-Order-IDs deterministisch; bei Timeout wird zuerst nachgesehen, dann erst neu gesendet.
- Wiederholte Ablehnungen -> Handelsstopp; Datenalter/Kurssprung-Prüfung vor jeder Entscheidung.
- Schutz-Stops liegen auf der Börse (reduce-only) und werden bei Größenänderung ersetzt.
- Zustand (Risk-State, Paper-Konto) wird im Journal gespeichert und beim Neustart geladen.
