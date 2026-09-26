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

Alle Strategien sind **long-only** (Spot, kein Hebel, kein Short).

### Eigene Strategie hinzufügen

1. Datei `trading_bot/strategies/meine_strategie.py` anlegen:

   ```python
   from .base import Strategy

   class MeineStrategie(Strategy):
       """Kurzbeschreibung."""
       name = "meine_strategie"
       default_params = {"period": 10}

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
| Ordergröße             | `position_fraction`, `max_order_value` | Obergrenze pro Kauf                                 |
| Stop-Loss              | `stop_loss_pct`               | Verkauf bei X % unter Einstieg                               |
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
