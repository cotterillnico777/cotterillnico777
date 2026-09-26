# Krypto-Trading-Bot

Spot-Trading-Bot für Kryptowährungen über [ccxt](https://github.com/ccxt/ccxt)
(Binance, Kraken, Bybit, Coinbase und über 100 weitere Börsen). Er hat
austauschbare Strategien, einen Backtester, einen Paper-Modus mit Spielgeld
und einen Live-Modus mit Sicherheitsgrenzen.

> **Wichtig:** Trading mit Echtgeld kann zum Totalverlust des eingesetzten
> Kapitals führen. Die mitgelieferten Strategien sind einfache Lehrbeispiele und
> keine Gewinngarantie. Immer erst backtesten, dann mehrere Wochen Paper-Trading,
> erst dann mit kleinen Beträgen live gehen.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Befehle

```bash
python -m trading_bot strategies                      # Strategien und Parameter anzeigen
python -m trading_bot backtest                        # Strategie aus config.yaml testen
python -m trading_bot backtest --all --days 730       # alle Strategien vergleichen
python -m trading_bot backtest -s rsi_reversion --trades
python -m trading_bot backtest --csv kerzen.csv       # eigene Daten (timestamp,open,high,low,close,volume)
python -m trading_bot optimize --all --days 730       # Walk-Forward-Optimierung (siehe unten)
python -m trading_bot backtest --all --compare-filter   # mit und ohne Trendfilter
python -m trading_bot run                             # Paper-Trading (Spielgeld)
python -m trading_bot status                          # Position, PnL, letzte Trades
python -m trading_bot -c andere.yaml run              # andere Konfigurationsdatei
```

Alle Einstellungen stehen in `config.yaml`.

## Strategien

| Name                 | Idee                                                           |
|----------------------|----------------------------------------------------------------|
| `ma_crossover`       | Trendfolge: long, solange EMA(fast) > EMA(slow)                |
| `rsi_reversion`      | Mean Reversion: Kauf bei RSI < 30, Verkauf bei RSI > 70        |
| `bollinger_breakout` | Ausbruch über das obere Bollinger-Band, Ausstieg an Mittellinie |
| `trend_ensemble`     | Drei Donchian-Trendsysteme (kurz/mittel/lang), Signal 0, ⅓, ⅔ oder 1 |

Alle Strategien sind **long-only** (Spot, kein Hebel, kein Short). Warum: siehe
Recherche im Chatverlauf. Short-Seite verliert in Krypto durch Kurssprünge, Hebel
vervielfacht die ohnehin großen Drawdowns, und für Privatanleger in der EU sind
Krypto-Derivate auf 2:1 begrenzt.

### `trend_ensemble` (Teilpositionen)

Drei unabhängige Trendsysteme mit den Zeiträumen `short`, `mid` und `long` (in Kerzen):
Einstieg bei Schluss über dem höchsten Hoch der letzten N Kerzen, Ausstieg bei Schluss
unter dem tiefsten Tief der letzten N × `exit_ratio` Kerzen. Das Signal ist der Anteil
der Systeme im Trend. Der Bot steigt also schrittweise ein und aus. Mit `kind: sma`
gilt stattdessen "Schluss über SMA(N)".

Die Voreinstellung 20/55/100 ist für **Tageskerzen** gedacht. Für 4h-Kerzen etwa × 6:

```yaml
strategy:
  name: trend_ensemble
  params: {short: 120, mid: 330, long: 600, exit_ratio: 0.5, kind: donchian}
```

### Eigene Strategie hinzufügen

1. Datei `trading_bot/strategies/meine_strategie.py` anlegen:

   ```python
   from .base import Strategy

   class MeineStrategie(Strategy):
       """Kurzbeschreibung."""
       name = "meine_strategie"
       default_params = {"period": 10}
       param_grid = {"period": [5, 10, 20, 40]}   # für `optimize`

       @property
       def warmup(self) -> int:
           return self.params["period"]

       def generate_signals(self, df):
           # 1 = investiert sein, 0 = flat. Nur Daten bis zur jeweiligen Kerze nutzen!
           return (df["close"] > df["close"].rolling(self.params["period"]).max().shift(1)).astype(int)
   ```

2. In `trading_bot/strategies/__init__.py` zur Liste in `STRATEGIES` hinzufügen.
3. `pytest` ausführen. Der Test `test_strategies_have_no_lookahead` prüft
   automatisch, dass die Strategie nicht in die Zukunft schaut.

## Stop-Loss und Positionsgröße

| Einstellung                | Wirkung                                                                 |
|----------------------------|-------------------------------------------------------------------------|
| `stop_mode: pct`           | Stop fest `stop_loss_pct` unter dem Einstieg                            |
| `stop_mode: atr`           | Stop `atr_multiplier` × ATR unter dem Einstieg. Die ATR ist die typische Schwankung einer Kerze: in unruhigen Phasen weiter weg, in ruhigen enger |
| `trailing_stop: true`      | Der Stop zieht mit dem höchsten Kurs seit Einstieg nach oben (nie nach unten) und sichert so Gewinne |
| `sizing: vol_target`       | Positionsgröße = Guthaben × `target_vol` / gemessene Volatilität (max. 100 %, kein Hebel). Bei 60 % Marktschwankung und 25 % Ziel sind rund 42 % investiert. Nachjustiert wird ab `rebalance_threshold` Abweichung |
| `sizing: risk`             | Positionsgröße so, dass ein Stop-Treffer `risk_per_trade` (z. B. 1 %) des Guthabens kostet. Bei hoher Volatilität kleinere Position, bei niedriger größere |

`position_fraction` und `max_order_value` gelten immer als Obergrenze.

Welche Variante zu einer Strategie passt, zeigt der Vergleich:

```bash
python -m trading_bot backtest --all --compare-stops --full-stake
python -m trading_bot backtest -s trend_ensemble -t 1d --compare-sizing --days 2000
```

`--compare-sizing` vergleicht feste Größe, Volatility Targeting (20/30/40/60 %) und
risikobasierte Größe, jeweils mit bis zu 100 % Einsatz, und zeigt Buy & Hold als
Vergleichszeile mit Sharpe und Drawdown.

Faustregel: Trendfolge (`ma_crossover`, `bollinger_breakout`) profitiert oft von
einem ATR-Trailing-Stop. Mean Reversion (`rsi_reversion`) kauft bewusst in fallende
Kurse, dort schaden enge Stops oft. Stops erzeugen allein keinen Gewinn. Sie
begrenzen Verluste und machen das Risiko pro Trade planbar. Die gewählte Variante
danach mit `optimize` auf ungesehenen Daten prüfen.

Im Live-Betrieb wird der Trailing-Stop wie im Backtest bei jeder abgeschlossenen
Kerze nachgezogen. Geprüft wird der Stop bei jedem Durchlauf (`poll_seconds`).

## Trendfilter

Der Filter funktioniert mit jeder Strategie. Gekauft wird nur, wenn der
**höhere Zeitrahmen** im Aufwärtstrend ist, standardmäßig also wenn der
Tagesschluss über dem 200-Tage-Durchschnitt liegt. So vermeidet der Bot
Käufe in längeren Abwärtsphasen, in denen die meisten Long-Strategien Geld verlieren.

```yaml
trend_filter:
  enabled: true
  timeframe: 1d     # z. B. 4h, 1d, 1w
  period: 200
  kind: sma         # sma | ema
  mode: entry       # entry = nur Käufe filtern | exit = auch verkaufen, wenn der Trend kippt
```

```bash
python -m trading_bot backtest --all --compare-filter --full-stake --days 900
python -m trading_bot optimize --all --days 900 --trend-filter on
python -m trading_bot optimize --all --days 900 --trend-filter off
```

- Es zählen nur **abgeschlossene** Kerzen des höheren Zeitrahmens. Die Tageskerze
  von heute wirkt erst ab der letzten Stundenkerze des Tages.
- Der Filter braucht Vorlauf, bei `period: 200` auf `1d` also 200 Tage. Davor kauft
  der Bot nicht. `--compare-filter` vergleicht deshalb nur den Zeitraum danach.
  Wähle `--days` groß genug, z. B. 900.
- Im Live-Betrieb lädt der Bot die Tageskerzen direkt von der Börse. Ein Test
  stellt sicher, dass Live und Backtest zur gleichen Entscheidung kommen.

## Parameter optimieren (Walk-Forward)

Ein normaler Backtest mit den „besten“ Parametern ist fast immer zu optimistisch:
Die Parameter wurden ja genau auf diesen Daten ausgesucht. `optimize` prüft
deshalb ehrlich:

1. **Rollierende Fenster:** Parameter werden auf `train_days` ausgewählt und auf den
   folgenden `test_days` getestet, die der Optimierer nie gesehen hat. Dann rückt das
   Fenster weiter. Nur diese Testergebnisse (Out-of-Sample, **OOS**) zählen.
2. **Robuste Auswahl:** Gewählt wird nicht der einzelne Spitzenwert, sondern die
   Kombination, deren Nachbarn im Raster ebenfalls gut sind (z. B. `fast=20` nur,
   wenn auch `fast=10` und `fast=30` gut abschneiden).
3. **Mehrere Märkte:** Mit `optimize.symbols` oder `--symbols BTC/USDT,ETH/USDT,SOL/USDT`
   läuft alles pro Markt. Am Ende steht eine Parameter-Empfehlung, die über alle
   Märkte im Schnitt am robustesten ist.

```bash
python -m trading_bot optimize -s ma_crossover --days 730
python -m trading_bot optimize --all --days 730 --symbols BTC/USDT,ETH/USDT,SOL/USDT
python -m trading_bot optimize --all --full-stake       # 100 % Einsatz, fair gegen Buy & Hold
python -m trading_bot optimize --all --out ergebnisse/  # Fenster und Kapitalkurven als CSV
```

**So liest du das Ergebnis:**

| Spalte          | Bedeutung                                                              |
|-----------------|------------------------------------------------------------------------|
| `OOS %`         | Rendite nur auf ungesehenen Daten, **die wichtigste Zahl**             |
| `Standard %`    | Dieselben Testfenster mit den Standardparametern ohne Optimierung      |
| `Buy&Hold %`    | Einfach kaufen und halten im selben Zeitraum                           |
| `Fenster +`     | Anteil der Testfenster mit Gewinn, je höher, desto stabiler            |
| `Score Train → Test` | Großer Abstand bedeutet Overfitting                               |

Eine Strategie ist erst interessant, wenn `OOS %` auf **mehreren Märkten** positiv
ist und über `Standard %` liegt. Ist das nicht der Fall, ist Nichtstun (oder Buy &
Hold) die bessere Wahl, und das ist ein wertvolles Ergebnis.

Das Suchraster jeder Strategie steht in `param_grid` in der Strategie-Datei und kann
in `config.yaml` unter `optimize.grids` überschrieben werden.

## Wie der Bot handelt

- Alle `poll_seconds` holt der Bot den aktuellen Preis und prüft den **Stop-Loss**.
- Sobald eine Kerze **abgeschlossen** ist, wertet er die Strategie aus
  (laufende Kerzen werden ignoriert, wie im Backtest).
- Signal 1 und keine Position: Kauf für `min(position_fraction × freies Guthaben, max_order_value)`.
- Signal 0 und Position offen: alles verkaufen, was der Bot selbst gekauft hat.
- Nach einem Stop-Loss kauft er erst wieder, wenn das Signal zwischendurch auf 0 war.
- Der Zustand (Position, PnL, Trades) liegt in `state/`, ein Neustart macht dort weiter.

## Live-Trading mit Echtgeld

1. Bei der Börse einen API-Schlüssel **nur mit Handelsrecht** anlegen.
   **Auszahlungen (Withdrawals) nicht erlauben.** Wenn möglich, den Schlüssel
   auf die IP-Adresse des Servers beschränken.
2. `.env.example` nach `.env` kopieren und Schlüssel eintragen. `.env` wird
   von git ignoriert, also niemals committen.
3. Optional zuerst mit `exchange.sandbox: true` im Testnet der Börse testen.
4. In `config.yaml` die Werte unter `runtime.mode: live` und `risk` anpassen.
5. Starten:

   ```bash
   python -m trading_bot run --live
   ```

   Der Bot zeigt Börse, Guthaben und Limits an und startet erst, wenn du
   `ECHTGELD` eintippst. Für den Betrieb als Dienst (systemd, Docker) gibt es
   `--yes`, das diese Bestätigung überspringt.

### Sicherheitsmechanismen

| Mechanismus            | Einstellung                   | Wirkung                                                      |
|------------------------|-------------------------------|--------------------------------------------------------------|
| Doppelte Freigabe      | `mode: live` + `--live`       | Ohne beides kein Echtgeld                                    |
| Ordergröße             | `position_fraction`, `max_order_value`, `sizing` | Obergrenze pro Kauf, optional risikobasiert |
| Stop-Loss              | `stop_mode`, `stop_loss_pct`, `trailing_stop` | Verkauf unter festem, ATR- oder Trailing-Stop |
| Tagesverlustlimit      | `max_daily_loss`              | Keine neuen Käufe mehr an diesem Tag (UTC)                   |
| Not-Aus                | Datei `STOP` anlegen          | Sofort keine neuen Käufe (`touch STOP`, zum Lösen `rm STOP`) |
| Fremde Bestände        | automatisch                   | Der Bot verkauft nur, was er selbst gekauft hat              |
| Fehlerserie            | automatisch                   | Nach 10 Fehlern in Folge beendet sich der Bot                |

**Grenzen, die du kennen solltest:**

- Der Stop-Loss wird **vom Bot** überwacht, nicht als Order bei der Börse
  hinterlegt. Läuft der Bot nicht (Server aus, Internet weg), greift er nicht.
- Der Backtest berücksichtigt Gebühren, Slippage und Stop-Loss, aber kein
  Tagesverlustlimit und keine Börsen-Mindestmengen. Live-Ergebnisse weichen ab.
- Gewinne aus Krypto-Trading sind je nach Land steuerpflichtig. Die Trade-Historie
  steht in `state/bot_state.json` und im Log `state/bot.log`.

## Tests

```bash
pytest
```
