# Backtesting und Forschung

## Ausführungsmodell

- Entscheidung am Schluss von Kerze t, Ausführung zum Open von t+1 (+ `execution.delay_bars`).
- Kosten: Taker 0,05 %, Maker 0,02 %; Slippage 2 bps + 2 % der Kerzenspanne; Stops als
  Taker. Lücken über den Stop werden zum Open gefüllt (nicht zum Stop-Preis).
- Innerhalb einer Kerze wird bei Stop und Take-Profit **zuerst der Stop** angenommen.
- Funding: historische 8h-Raten; fehlen sie, gilt eine konservative Ersatzrate
  (0,01 % je 8 h gegen die Position), im Bericht ausgewiesen.
- Cross-Margin-Konto mit Maintenance Margin und Liquidation (siehe RISK_MANAGEMENT.md).
- Je Trade gespeichert: Asset, Richtung, Einstieg, Ausstieg, Größe, Hebel, Stop, Ziel,
  PnL, Gebühren, Funding, Slippage, Regime, Strategie, Version, Signalstärke,
  Ein-/Ausstiegsgrund, MFE, MAE, R-Multiple, Merkmale beim Einstieg.

## Datenprüfung (`python -m quantbot data audit`)

Vor der Forschung: je Symbol und Zeitrahmen PASS / WARN / FAIL, ohne Daten zu verändern.

- **FAIL:** doppelte/unsortierte Zeitstempel, High < Low, Open/Close außerhalb High/Low,
  Preis ≤ 0, fehlende Werte, negatives Volumen, Volumen 0 trotz Preisbewegung, beim Speichern
  noch laufende Kerze, Widerspruch zwischen Zeitrahmen (höherer Zeitrahmen wird aus 15m
  nachgebaut und mit dem getrennt geladenen verglichen).
- **WARN:** Lücken, Kerzen ohne Handel (flach, Volumen 0), nicht bestätigte Extrembewegungen,
  Auffälligkeiten bei Funding-Zeitpunkten.
- Zeitrahmen-Widerspruch: Ursache wird je Kerze bestimmt. *wartung* (im Umfeld von 15m-Kerzen
  ohne Handel; die Börse bildet die Zeitrahmen um Ausfälle unterschiedlich) = WARN;
  *börsenweit* (dieselbe Kerze weicht bei mehreren Symbolen ab -> Ereignis der Börse) = WARN;
  *datenende* (vor Finalisierung geladen, erneuter Download ersetzt sie) und *ungeklärt* = FAIL.
  Für *wartung* und *börsenweit* schreibt `data audit` die Zeitfenster nach
  `market_data/incidents.json`; der Backtest führt dort in allen Zeitrahmen weder Orders noch
  Stops aus. Die Kursdateien bleiben unverändert.
  Neue Kerzen werden erst 2 Minuten nach Schluss übernommen.
- Extrembewegung: |Log-Rendite − Median| > 12 × robuste Streuung (MAD × 1,4826) des jeweiligen
  Zeitrahmens. Sie gilt als echt, wenn OHLC konsistent ist, der andere Zeitrahmen sie bestätigt,
  kein Kurssprung zwischen Kerzen vorliegt und keine sofortige Umkehr bei schwachem Volumen folgt.
  Gleichzeitige Bewegungen bei anderen Symbolen werden mit ausgewiesen.

## Metriken

Rendite, CAGR, Max-Drawdown, Sharpe, Sortino, Calmar, Profit Factor, Expectancy,
Trefferquote, Payoff Ratio, Trades, Gebühren, Funding, Ø Exposure, Ø Hebel, längste
Verlustserie, längste Erholungszeit, Buy-&-Hold-Vergleich.

## Pipeline (`python -m quantbot research`)

Daten werden chronologisch geteilt: 60 % Train, 20 % Validation, 20 % Out-of-Sample.

| Stufe | Inhalt | Kriterium (Standard) |
|---|---|---|
| A | Parameterraster auf Train; gewählt wird der Wert mit der besten **Nachbarschaft**, nicht der beste Einzelwert | Sharpe > 0 und Profit Factor > 1; ≥ 50 % der Kombinationen Sharpe > 0; Plateau-Verhältnis ≥ 0,5 |
| B | Validation mit festen Parametern | Sharpe > 0 und Profit Factor > 1 |
| C | Walk-Forward (365 Tage Train / 90 Tage Test), fest und adaptiv | fest: Sharpe > 0 und ≥ 50 % der Fenster profitabel |
| D | Train+Validation gesamt: Stress (Gebühren ×2, Slippage ×2, Verzögerung 1 Kerze; ×3 und 2 Kerzen nur berichtet), Monte Carlo (1000), Jahre, Regime, Risikoskalierung, ML-Prüfung | ≥ 30 Trades; Max-DD ≤ 25 %; keine Liquidation; Stress-Sharpe > 0; MC-p95-Drawdown ≤ 35 %; Verlustwahrscheinlichkeit ≤ 25 %; in ≥ 2 Trend-Regimen gehandelt und nicht in allen verlustreich |
| E | Ensembles bestandener Kandidaten (gleichgewichtet und regime-gefiltert) | wie oben |
| F | **Out-of-Sample einmalig** | Sharpe > 0 und Rendite > 0 |

Besteht nichts, lautet das Ergebnis **NO TRADE** – das ist ein gültiges Ergebnis und wird
genauso dokumentiert wie ein positives.

## Was geprüft wurde (Funktionstests, keine Performance)

- Präfix-Tests gegen Lookahead für alle Strategien, Regime und Engine.
- Handgerechnete Referenzfälle für Gebühren, Funding, Stops, Lücken, Liquidation.
- Auf **Zufallspfaden** besteht keine Strategie (die Pipeline erzeugt NO TRADE).
- Auf synthetischen Trenddaten bestehen Trendstrategien, Mean Reversion fällt durch –
  die Pipeline unterscheidet also, statt alles durchzuwinken.
- Laufzeit: 5 Jahre 15m × 3 Märkte ca. 4 s je Backtest.

## Grenzen / bekannte Schwächen

- Keine Orderbuch-Simulation; Slippage ist ein Modell, im Paper-Vergleich zu prüfen.
- Die ML-Prüfung filtert auf Trade-Ebene nachträglich (Positionsgrößen-Pfad ignoriert).
- Walk-Forward adaptiv wählt je Fenster aus demselben Raster – bei großem Raster steigt
  das Risiko der Überanpassung; deshalb ist das Raster klein gehalten.
- **Echte Ergebnisse fehlen noch** (siehe README): alle Börsen-Hosts sind in der
  Entwicklungsumgebung gesperrt.
