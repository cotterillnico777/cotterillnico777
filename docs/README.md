# quantbot – privater Krypto-Futures-Bot (v2)

Forschungs- und Handelssystem für BTC, ETH und SOL USDT-Perpetuals (15m, 1h, 4h, 1d).
Leitprinzip: **Robustheit, reproduzierbare Out-of-Sample-Ergebnisse und Kapitalerhalt vor
maximaler Rendite.** NO TRADE ist ein gültiges Ergebnis.

> Stand: Das System ist technisch vollständig und getestet. **Es gibt noch keine Aussage
> über echte Märkte**, weil die Cloud-Umgebung, in der es gebaut wurde, keinen Zugriff auf
> Börsendaten hat. Alle echten Ergebnisse entstehen auf deinem Rechner (Schritte unten).

## Dokumentation

| Datei | Inhalt |
|---|---|
| [PLAN.md](PLAN.md) | Bestandsaufnahme, Annahmen A1–A16, Phasen, Fortschritt |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module, Datenfluss, Lookahead-Schutz |
| [STRATEGIES.md](STRATEGIES.md) | 17 Strategien, Regime-Erkennung, ML-Prüfung |
| [RISK_MANAGEMENT.md](RISK_MANAGEMENT.md) | Positionsgröße, Hebel, Limits, Kill Switch |
| [BACKTESTING.md](BACKTESTING.md) | Kostenmodell, Pipeline A–F, Abnahmekriterien |
| [LIVE_TRADING.md](LIVE_TRADING.md) | Paper, Forward-Vergleich, Readiness, Live-Freigabe |
| [CHANGELOG.md](CHANGELOG.md) | Versionen |

## Ablauf (auf deinem Rechner)

```bash
git pull origin claude/hopeful-goldberg-w1ms4b
pip install -r requirements.txt

# 1. Daten (öffentliche Endpunkte, kein API-Schlüssel nötig)
python -m quantbot data download --timeframes 15m 1h 4h 1d
python -m quantbot data validate
python -m quantbot data audit      # PASS/WARN/FAIL je Symbol und Zeitrahmen, ändert nichts
#    -> research_output/data_audit/DATA_AUDIT.md (+ CSV mit jeder auffälligen Kerze)
#    Research startet nur, wenn kein FAIL vorliegt (bei harten Fehlern bricht research ab)

# 2. Forschung: alle Strategien, alle Stufen, OOS nur einmal am Ende
python -m quantbot research --timeframes 1d 4h 1h 15m
#    -> research_output/<zeitstempel>_<tf>/REPORT.md und results.json

# 3. Nur bestandene Kandidaten in eine Konfiguration übernehmen
cp configs/quantbot.example.yaml my.yaml   # Strategien ersetzen!

# 4. Paper Trading (mindestens 30 Tage / 20 Trades)
python -m quantbot -c my.yaml run --mode paper
python -m quantbot -c my.yaml status
python -m quantbot -c my.yaml analyze --journal state/quantbot.sqlite

# 5. Backtest vs. Paper, dann Checkliste
python -m quantbot -c my.yaml compare --journal state/quantbot.sqlite
python -m quantbot -c my.yaml readiness --research research_output/<zeitstempel>_4h/results.json \
    --journal state/quantbot.sqlite --forward research_output/forward_compare.json
```

Notbremse jederzeit: `python -m quantbot kill` oder eine Datei `STOP` im Arbeitsverzeichnis.

Tests: `python -m pytest -q tests/v2` (Funktionstests mit synthetischen Daten; diese Daten
werden nie als Performance berichtet).

Die ältere Version 1 (`trading_bot/`, `config.yaml`) bleibt unverändert lauffähig.
