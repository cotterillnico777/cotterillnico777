# Technischer Plan: quantbot

Stand: 2026-09-26. Dieses Dokument wird bei jeder Phase fortgeschrieben.

## 1. Bestandsaufnahme (Repository-Analyse)

| Bestand | Bewertung | Entscheidung |
|---|---|---|
| `trading_bot/` (v1) | Spot, nur long, ein Markt, eine Position. Solide getestet (50 Tests), inkl. Walk-Forward, Vol-Targeting, Trendfilter | Bleibt unverändert als **v1** lauffähig. Nicht umbauen, sondern ablösen |
| Erkenntnisse aus v1 mit echten Daten (vom Nutzer ausgeführt) | 1h verliert durch Kosten; 4h/1d Trendfolge auf ungesehenen Daten positiv; laufendes Nachoptimieren verschlechtert eher; Trailing-Stops nicht robust | Fließen als Hypothesen in v2 ein, werden dort **erneut** und strenger geprüft |
| `briefings/`, `scripts/` | fremde Inhalte (Finanz-Briefings) | nicht anfassen |

v1 kann nicht sinnvoll erweitert werden: Short, Hebel, Margin, Funding, Liquidation
und mehrere gleichzeitige Märkte verändern das Kernmodell (Konto statt Einzelposition).
Deshalb entsteht ein neues Paket `quantbot/` neben v1.

## 2. Architektur (Kurzfassung, Details in ARCHITECTURE.md)

```
quantbot/
  config/       Laden/Prüfen der Konfiguration, Betriebsmodi
  data/         Download (ccxt), Validierung, Speicher, Manifest (Hash), Resampling
  indicators/   reine Funktionen, vektorisiert, ohne Zukunftsdaten
  strategies/   Signalgeneratoren: Richtung + Stärke + Stop-Abstand, sonst nichts
  regimes/      Marktregime je Kerze (Trend × Volatilität)
  risk/         zentrale Risk Engine: Größe, Hebel, Limits, Kill Switch
  portfolio/    Konto, Positionen, Margin, Liquidation, Korrelation
  backtesting/  Ereignisschleife, Kosten- und Ausführungsmodelle, Metriken
  research/     Splits, Walk-Forward, Sensitivität, Stress, Monte Carlo, Scorecard
  execution/    Order-State-Machine, idempotente Orders, Retries, Abgleich
  exchanges/    ExchangeAdapter + ccxt-Futures-Adapter + simulierte Börse (Paper)
  analytics/    Auswertungen nach Strategie, Asset, Regime, Uhrzeit, Signalstärke
  monitoring/   Status, Health Checks, Journal (SQLite)
  cli.py        ein Einstiegspunkt für alle Modi
```

Trennung: Strategien kennen weder Kontostand noch Börse. Die Risk Engine entscheidet
über Größe und Hebel. Die Execution Engine setzt Zielpositionen in Orders um. Backtest,
Paper und Live benutzen **dieselbe** Strategy- und Risk Engine. Paper und Live benutzen
zusätzlich dieselbe Execution Engine, nur mit unterschiedlichem Adapter.

## 3. Annahmen (explizit, prüfbar)

### Daten
- A1: Primärquelle sind Binance-USDⓈ-M-Perpetuals über ccxt (`BTC/USDT:USDT` usw.).
  Andere Börsen sind über den Adapter austauschbar.
- A2: Kerzenzeitstempel = Kerzenbeginn (UTC). Eine Kerze ist erst nach
  `timestamp + timeframe` bekannt.
- A3: Funding-Historie ist über `fetch_funding_rate_history` vollständig abrufbar (Binance
  ab Kontraktstart). Fehlt sie, wird im Backtest eine konservative Konstante verwendet
  und das im Bericht ausgewiesen. Nie stillschweigend 0.
- A4: Open Interest, Liquidationen und Long/Short-Ratio sind bei Binance historisch nur
  ca. 30 Tage abrufbar. Das reicht **nicht** für belastbare Backtests. Diese Daten werden
  deshalb vorerst **nicht** als Signal verwendet (Regel: keine Variablen mit
  unzuverlässiger Historie). Funding wird als Kosten und als Kandidat-Signal verwendet.
- A5: Survivorship Bias: BTC/ETH/SOL existieren über den ganzen Testzeitraum. Bei
  Erweiterung um weitere Assets muss die Asset-Auswahl zeitpunktgenau erfolgen.

### Ausführung und Kosten
- A6: Signal wird mit dem Schluss von Kerze t berechnet, ausgeführt frühestens zum
  Eröffnungskurs von t+1 (+ optionale Verzögerung in Kerzen).
- A7: Taker-Gebühr 0,05 %, Maker 0,02 % (Binance Futures Standard). Alle Marktorders
  zahlen Taker. Stress-Tests mit ×2 und ×3.
- A8: Slippage = feste Basis (2 bps) + Anteil der Kerzenspanne. Stress ×2, ×3.
- A9: Stops werden innerhalb der Kerze mit Hoch/Tief geprüft. Öffnet die Kerze jenseits
  des Stops (Gap), wird zum Eröffnungskurs gefüllt. Treffen Stop und Take-Profit in
  derselben Kerze, gilt **zuerst der Stop** (konservativ).
- A10: Margin-Modell: Cross-Margin auf Kontoebene. Liquidation, sobald
  Kontowert ≤ Summe der Maintenance Margins. Geprüft wird mit dem ungünstigsten
  Kurs der Kerze (Tief für Longs, Hoch für Shorts) gleichzeitig für alle Positionen.
  Maintenance Margin Rate 0,5 % (BTC/ETH-Basisstufe; SOL konservativ 1 %), plus
  Liquidationsgebühr.
- A11: Funding alle 8 h (00/08/16 UTC) auf den Positionswert: Long zahlt bei positiver Rate.

### Risiko
- A12: Hebel ist nie Parameter einer Strategie. Er ergibt sich aus
  Positionsgröße = zulässiges Risiko / Stop-Abstand und wird danach durch
  `max_leverage` (Standard 2, harte Obergrenze 5) und durch den Liquidationsabstand begrenzt:
  Der Stop muss mit Sicherheitsfaktor vor dem Liquidationspreis liegen.
- A13: BTC, ETH und SOL sind hoch korreliert. Portfolio-Risiko wird über die rollierende
  Kovarianz geschätzt, nicht als Summe unabhängiger Risiken.

### Forschung
- A14: Zeitliche Aufteilung: Train (60 %) → Validation (20 %) → Out-of-Sample (20 %).
  Der OOS-Teil wird für **keine** Auswahlentscheidung benutzt, nur einmal am Ende.
- A15: Parameter werden als Bereiche bewertet (Nachbarschaftsstabilität), nicht als Punkt.
- A16: Ergebnisse aus synthetischen Daten sind ausschließlich Funktionstests und werden
  nie als Performance berichtet.

## 4. Phasen und Abnahmekriterien

| Phase | Inhalt | Abnahme |
|---|---|---|
| 1 | Architektur, Konfiguration, Datenmodelle, Datenpipeline, Adapter-Abstraktion | Tests grün; Datenvalidierung findet Lücken/Duplikate/Ausreißer |
| 2 | Backtest-Engine mit Kosten, Funding, Margin, Liquidation, Metriken | Handgerechnete Referenzfälle stimmen; Präfix-Test (kein Lookahead) |
| 3 | Strategieklassen + Regime | Jede Strategie besteht den Präfix-Test; Research-Runner erzeugt Vergleich |
| 4 | Splits, Walk-Forward, Sensitivität, Stress, Monte Carlo, Scorecard | Scorecard prüft Definition of Done automatisch |
| 5 | Risk Engine produktionsreif | Grenzfall-Tests für jede Regel |
| 6 | Execution Engine, Paper Trading, Journal, Monitoring | Order-State-Tests, Idempotenz, Fehlerfälle; Paper nutzt dieselben Engines |
| 7 | Vergleich Backtest vs. Forward | Bericht zu Slippage-Gap, Signal-Decay, Drift |
| 8 | Live-Readiness (nur technisch) | Checkliste; LIVE bleibt aus |

## 5. Was diese Umgebung nicht kann

Alle Börsen-APIs sind aus der Cloud-Umgebung gesperrt. Echte Forschungsergebnisse
entstehen daher nur auf dem Rechner des Nutzers über `python -m quantbot research ...`.
Die Berichte werden dort erzeugt und hier ausgewertet.

## 6. Fortschritt und Abweichungen

- Phase 1 und 2 abgeschlossen.
- **Reihenfolge geändert:** Die Risk Engine (Phase 5) wurde vor der Strategie-Forschung
  (Phase 3) gebaut. Grund: Jedes Forschungsergebnis hängt von Positionsgröße, Hebel und
  Limits ab. Forschung mit einer provisorischen Größenlogik hätte später komplett
  wiederholt werden müssen.
