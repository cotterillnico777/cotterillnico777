# Changelog

## quantbot 0.1.0 (v2)

Neuaufbau als modulares System neben der bestehenden Version 1.

- Phase 1: Konfigurationsschema (unbekannte Schlüssel = Fehler), `.env`, Datenpipeline
  mit Validierung und Hash, Adapter-Abstraktion.
- Phase 2: Portfolio-Backtest für Perpetuals (Kosten, Funding, Cross Margin, Liquidation, Metriken).
- Phase 5 (vorgezogen): zentrale Risk Engine mit Kovarianz-Deckel, Loss Limits, Kill Switch.
- Phase 3: 17 Strategien in 7 Klassen, Regime-Erkennung, Präfix-Tests.
- Phase 4: Pipeline A–F (Raster/Plateau, Validation, Walk-Forward, Stress, Monte Carlo,
  Ensembles, einmaliges OOS), Markdown/JSON-Bericht.
- Phase 6: Execution Engine (idempotent, Timeouts, reduce-only, Börsen-Stops),
  simulierte Börse, Trader-Schleife, SQLite-Journal, Status, Kill Switch.
- Phase 7: Trade-Analyse, Backtest-vs-Forward-Vergleich, Risikoskalierung, ML-Meta-Filter-Prüfung.
- Phase 8: Live-Readiness-Checkliste; LIVE bleibt deaktiviert.

Offen: echte Forschungsergebnisse (Daten nur auf dem Nutzerrechner), Paper-Phase,
Forward-Vergleich mit echten Daten.

## Version 1 (`trading_bot/`)

Einfacher Einzelmarkt-Bot mit austauschbaren Strategien, Trendfilter, Vol-Targeting und
Trend-Ensemble. Unverändert.
