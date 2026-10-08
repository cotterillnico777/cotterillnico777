# Forschungsergebnisse (echte Daten)

Alle Werte stammen aus `python -m quantbot research` auf Binance-USDT-Perpetual-Daten
(BTC, ETH, SOL), gerechnet auf dem Rechner des Nutzers. Nichts hier ist geschätzt oder
nachträglich angepasst. Negative Ergebnisse stehen gleichberechtigt neben positiven.

- Daten: 2020-04 bis 2026-10, Prüfung `data audit` ohne FAIL (Befunde in PLAN.md, A18)
- Splits: Train 2020-04-10 – 2024-03-02, Validation – 2025-06-19, Out-of-Sample – 2026-10-06
- Kosten: Taker 0,05 %, Slippage 2 bps + 2 % der Kerzenspanne, historisches Funding
- Risiko: 0,5 % je Trade, max. Kontohebel 2, Kill Switch bei −20 %
- 17 Strategien je Zeitrahmen, je bis zu 24 Parameterkombinationen

## Übersicht

| Zeitrahmen | Code-Stand | bestanden (inkl. OOS) |
|---|---|---|
| 1d | c642921 | `volume_momentum` (knapp, 19 OOS-Trades) |
| 4h | 2ed2d15 | `ema_trend`, `squeeze_breakout`, `ensemble_equal` (beide) |
| 1h | 2ed2d15 | **keine – NO TRADE** |
| 15m | 2ed2d15 (Bericht zeigt 683cb12, nur Konfig-Unterschied) | **keine – NO TRADE** |

Der 1d-Lauf lief vor der Monte-Carlo-Korrektur (2ed2d15). Die Korrektur macht Stufe D nur
weniger pessimistisch; das 1d-Ergebnis bleibt gültig, könnte aber bei Wiederholung weitere
Kandidaten zur Out-of-Sample-Stufe zulassen.

## Kandidat im Paper Trading: 4h `ensemble_equal`

`ema_trend {fast 10, slow 200, adx_min 20, atr_mult 4}` + `squeeze_breakout {n 30,
squeeze_pct 0.2, rank_window 250, lookback 5, atr_mult 2}`, gleich gewichtet, ohne Regime-Filter.
Konfiguration: `configs/paper_ensemble_4h.yaml`, Paper-Start 2026-10-06 11:24 UTC.

| | Sharpe | Rendite | Max-DD | Profit Factor | Trades |
|---|---|---|---|---|---|
| Train | 1,42 | +43,2 % | −8,6 % | 1,63 | 651 |
| Validation | 0,73 | +6,6 % | −5,7 % | 1,26 | 267 |
| Forschung gesamt | 1,25 | +52,9 % | −8,6 % | 1,51 | 914 |
| **Out-of-Sample** | **0,66** | **+6,3 %** | **−6,8 %** | 1,24 | 262 |

- Stress: Gebühren ×3 Sharpe 0,83; Slippage ×3 0,79; Verzögerung 2 Kerzen 0,78
- Monte Carlo: Verlustwahrscheinlichkeit 0 %, Drawdown p95 −8,5 %
- Jahre: 2020 +6,2 %, 2021 +4,9 %, 2022 +0,7 %, 2023 +17,1 %, 2024 +11,5 %, 2025 +4,4 %
- Ø Kontohebel 0,11x – die Positionen sind klein; Rendite entsprechend moderat
- Risiko ×2 (1 % je Trade): Sharpe 1,27, Drawdown −16,1 % (nur Einordnung, nicht aktiv)

Einschränkungen:
- OOS-Sharpe etwa halb so hoch wie in der Forschung (übliche Abnahme; realistische Erwartung
  eher OOS als Forschung).
- 17 Strategien × 4 Zeitrahmen getestet; keine formale Korrektur für Mehrfachtests.
- `ema_trend` 4h bestand erst nach Korrektur eines Rechenfehlers in Monte Carlo (Kosten auf
  Konto statt Positionswert). Schwellen wurden nicht verändert.
- Regime-gefiltertes Ensemble (nur Bull/Bear) fiel in der Validierung durch (Sharpe −0,38).

## Negative Ergebnisse

- **Mean Reversion** (bollinger, rsi, zscore, vwap): auf allen vier Zeitrahmen bereits im
  Train negativ. Kein Hinweis auf verwertbare Rückkehr zum Mittelwert nach Kosten.
- **Trendfolge 1d/4h** (ts_momentum, adx_directional, mtf_momentum, …): im Train 2020–2023 stark
  (Sharpe bis 1,97), in der Validation 2024–2025 durchweg negativ. Die Trendphase lässt sich
  nicht fortschreiben.
- **1h und 15m**: fast alle Strategien schon im Train negativ, viele erreichen −20 % und lösen den
  Kill Switch aus. Ursache: engere ATR-Stops ergeben bei gleichem Risiko größere Positionen
  (Ø Hebel 0,3–0,6x statt 0,1–0,2x) und mehr Trades; Gebühren und Slippage übersteigen den
  Vorteil je Trade. `ema_trend` 1h bestand A–C, fiel in Monte Carlo durch (Verlust-
  wahrscheinlichkeit 30 %, p95-Drawdown −40 %) und wurde 2023 vom Kill Switch gestoppt.
- **Funding-Contrarian**: auf keinem Zeitrahmen positiv.
- **ML-Meta-Filter**: in keinem Fall ein Vorteil (Validation-AUC 0,40–0,48, also nicht besser als
  Zufall). ML wird nicht eingesetzt.
- **Mehr Hebel**: auf 4h bei `squeeze_breakout` schon ab Risiko ×2 schlechterer Sharpe; auf 1h
  führt Risiko ×2 zu −41 % Rendite.

## Nächste Prüfungen

1. Paper Trading des 4h-Ensembles mindestens 30 Tage / 20 Trades, dann `quantbot compare`
   (Signale, Slippage, Rendite gegen Backtest desselben Zeitraums) und `quantbot readiness`.
2. Optional, vorher festzulegen: Korrektur für Mehrfachtests (Deflated Sharpe Ratio).
3. LIVE bleibt deaktiviert, bis Paper und Readiness bestanden sind und der Nutzer manuell freigibt.
