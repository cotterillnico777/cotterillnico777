# Risikomanagement

Alle Entscheidungen über Größe und Hebel trifft die zentrale Risk Engine
(`quantbot/risk/engine.py`). Strategien liefern nur Richtung, Stärke und Stop-Abstand.

## Positionsgröße und Hebel

- `sizing: risk` (Standard): Größe = Konto × `risk_per_trade` × Signalstärke / Stop-Abstand.
  Ein Stop-Treffer kostet also ca. 0,5 % des Kontos (plus Kosten).
- `sizing: vol_target`: Größe so, dass die Position ca. `target_vol_per_position`
  annualisierte Vola beiträgt.
- **Hebel ist ein Ergebnis**, keine Eingabe: Brutto-Exposure / Equity. Enger Stop oder
  niedrige Vola -> größere Position -> höherer Hebel, begrenzt durch die Grenzen unten.

## Grenzen (in dieser Reihenfolge angewandt)

| Regel | Standard |
|---|---|
| Stop enger als 0,2 % wird abgelehnt | `min_stop_distance_frac` |
| Kosten > 0,15 R (Gebühren + Slippage hin und zurück) -> kein Trade | `max_cost_in_r` |
| Positionswert je Symbol ≤ 1 × Equity | `max_symbol_exposure` |
| Brutto ≤ 2 ×, netto ≤ 1,5 × Equity | `max_gross_exposure`, `max_net_exposure` |
| Kontohebel ≤ 2 (technisch hart ≤ 5, nicht konfigurierbar) | `max_leverage`, `HARD_MAX_LEVERAGE` |
| Portfolio-Vola aus 60-Tage-Kovarianz ≤ 30 % p. a. (korrelierte Positionen werden gemeinsam gekürzt) | `target_portfolio_vol` |
| Liquidationsabstand ≥ 3 × Stop-Abstand | `liquidation_buffer` |
| Nachjustieren erst bei ≥ 25 % Abweichung | `rebalance_threshold` |

## Verlustbegrenzung

| Regel | Wirkung |
|---|---|
| Tagesverlust ≥ 3 % | keine neuen Positionen bis Tageswechsel (UTC) |
| Wochenverlust ≥ 6 % | keine neuen Positionen bis Wochenwechsel |
| 5 Verluste in Folge oder Einzelverlust ≥ 2 % | Cooldown 12 Kerzen |
| Drawdown ≥ 20 % vom Höchststand | **Kill Switch**: alles schließen, nichts Neues, manuelle Freigabe |
| Datei `STOP` / `quantbot kill` | Kill Switch manuell |
| Wiederholte Order-Ablehnungen, alte Daten, Kurssprünge > 15 % | Handelsstopp |

Stops liegen zusätzlich als reduce-only Stop-Market-Order auf der Börse, damit ein
Ausfall des Bots nicht zu ungeschützten Positionen führt.

## Liquidation

Das Kontomodell (Cross Margin) rechnet Maintenance Margin je Symbol (BTC 0,4 %,
ETH 0,5 %, SOL 1 %) und prüft jede Kerze mit den **gleichzeitig ungünstigsten** Preisen
aller Positionen. Liquidation kostet zusätzlich 1,25 % des Positionswerts. Mit den
Standardgrenzen ist eine Liquidation praktisch ausgeschlossen; der Bericht zeigt in der
Tabelle „Mehr Risiko/Hebel", ab welchem Risikofaktor sie auftreten würde.

## Mehr Hebel?

Der Bericht enthält für jeden Kandidaten Läufe mit Risiko × 0,5 / 1 / 2 / 4. Mehr Risiko
erhöht Rendite **und** Drawdown ungefähr proportional, Sharpe bleibt bestenfalls gleich und
sinkt durch Kosten und Pfadabhängigkeit. Eine Erhöhung ist nur sinnvoll, wenn der
Monte-Carlo-p95-Drawdown bei höherem Risiko noch tragbar ist.
