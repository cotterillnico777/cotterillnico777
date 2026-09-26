# Strategien, Regime und ML

Jede Strategie liefert pro abgeschlossener Kerze ein Signal in [-1, 1] (Richtung × Stärke),
einen Stop-Abstand (meist k × ATR) und optional einen Take-Profit-Abstand. **Die Strategie
bestimmt keine Positionsgröße und keinen Hebel** – das macht ausschließlich die Risk Engine.

Kein Parameter in dieser Liste ist ein Forschungsergebnis. Welche Strategie mit welchen
Parametern handelt, entscheidet allein die Pipeline in [BACKTESTING.md](BACKTESTING.md)
auf echten Daten.

| Klasse | Name | Idee |
|---|---|---|
| Trend | `ema_trend` | schnelle über/unter langsamer EMA, optional ADX-Filter |
| Trend | `donchian_breakout` | Ausbruch über n-Kerzen-Hoch/-Tief, Ausstieg über m Kerzen |
| Trend | `ts_momentum` | Vorzeichen der Rendite über drei Horizonte (Stärke 1/3 … 1) |
| Trend | `adx_directional` | +DI/−DI-Richtung nur bei hohem ADX |
| Mean Reversion | `rsi_reversion` | RSI-Extrem, optional nur mit dem Tagestrend |
| Mean Reversion | `bollinger_reversion` | Schluss außerhalb Bollinger, Ausstieg an der Mitte |
| Mean Reversion | `zscore_reversion` | Z-Score des Preises |
| Mean Reversion | `vwap_reversion` | Abweichung vom rollierenden VWAP in ATR |
| Momentum | `relative_strength` | Querschnitt: stärkstes Asset long, schwächstes short |
| Momentum | `volume_momentum` | Ausbruch mit Volumenbestätigung |
| Market Structure | `breakout_retest` | Ausbruch, dann Rücksetzer ans Niveau |
| MTF | `mtf_momentum` | Momentum auf Tages- und eigenem Zeitrahmen stimmt überein |
| Market Structure | `swing_structure` | höhere Hochs/Tiefs (mit Bestätigungsverzögerung) |
| MTF | `mtf_pullback` | Tagestrend + Rücksetzer (RSI) im eigenen Zeitrahmen |
| Volatilität | `squeeze_breakout` | Bandbreite im unteren Perzentil, dann Ausbruch |
| Volatilität | `keltner_breakout` | Schluss außerhalb EMA ± k×ATR |
| Derivate | `funding_contrarian` | extremes Funding = überfüllte Seite |

Jede Strategie hat ein kleines `param_grid`; die Pipeline zieht daraus höchstens
`research.max_grid` Kombinationen (reproduzierbar per Seed).

## Nicht verwendet (bewusst)

- **Open Interest und Liquidationen:** Bei Binance nur ca. 30 Tage Historie über die API.
  Ein Backtest darüber wäre nicht belastbar (Annahme A4 in PLAN.md). Der Adapter kann die
  Daten später sammeln; eine Strategie darauf wird erst nach ausreichend eigener Historie getestet.
- **Makro/On-Chain:** keine frei verfügbare, zeitstempelgenaue (point-in-time) Historie in
  der Umgebung; Revisionen würden Lookahead erzeugen.

## Regime-Erkennung

Aus **abgeschlossenen Tageskerzen** (sichtbar erst ab dem Folgetag):

- Trend: Schluss über/unter SMA(100 Tage) und Steigung über 20 Tage; |Steigung| < 2 % = seitwärts
- Volatilität: 30-Tage-Vola als Perzentil des Vorjahres; > 70 % hoch, < 30 % niedrig

Eine Strategie kann per `regimes: [bull, bear]` o. ä. auf Regime beschränkt werden. Ob das
hilft, prüft die Pipeline (Ensemble „regime-gated" gegen „gleichgewichtet") und die
Aufschlüsselung je Regime im Bericht.

## Machine Learning

`quantbot/research/ml.py` prüft pro Kandidat einen **Meta-Filter**: logistische Regression
(numpy, L2) schätzt aus Merkmalen beim Einstieg (Strategie-Features, Signalstärke,
Richtung, Regime) die Gewinnwahrscheinlichkeit eines Trades. Ein Trade würde nur
genommen, wenn `p × Ø Gewinn − (1 − p) × Ø Verlust > 0` (Ø-Werte aus Train).

- Training nur auf Train-Trades, Bewertung nur auf Validation (zeitlich getrennt).
- Vergleich gegen (a) keinen Filter und (b) die einfache Regel „nur starke Signale".
- ML gilt nur als nützlich, wenn Validation-AUC ≥ 0,55, Erwartung/Trade ≥ 1,2 × Basis,
  höherer Netto-PnL als die Basis, besser als die einfache Regel und ≥ 10 Trades bleiben.
- Das Ergebnis steht im Bericht („ML wird NICHT eingesetzt" ist der erwartete Normalfall).
  Der Live-Pfad nutzt den Filter derzeit **nicht**; erst wenn er auf echten Daten
  wiederholt besteht, wird er eingebaut und separat im Walk-Forward getestet.
