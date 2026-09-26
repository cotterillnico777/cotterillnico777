"""Phase 8: Live-Readiness-Checkliste. Rein technisch – aktiviert LIVE niemals selbst."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Item:
    name: str
    ok: bool | None  # None = manuell zu prüfen
    detail: str


def readiness(cfg, research_results: str | None, journal=None, forward: dict | None = None,
              min_paper_days: int = 30, min_paper_trades: int = 20, max_return_gap: float = 0.05,
              max_slippage_gap_bps: float = 15.0) -> list[Item]:
    items: list[Item] = []

    # 1. Forschung: jede konfigurierte Strategie muss alle Stufen inkl. OOS bestanden haben
    if research_results and Path(research_results).exists():
        data = json.loads(Path(research_results).read_text(encoding="utf-8"))
        passed = {}
        for r in data["reports"]:
            ok = r.get("oos") is not None and all(c["passed"] for c in r["checks"])
            passed[r["name"]] = (ok, r.get("params"))
        for slot in cfg.strategies:
            ok, params = passed.get(slot.name, (False, None))
            same = params is not None and all(params.get(k) == v for k, v in slot.params.items())
            items.append(Item(f"Forschung bestanden: {slot.name}", ok and same,
                              "alle Stufen inkl. OOS bestanden, gleiche Parameter" if ok and same else
                              "nicht bestanden oder andere Parameter als im Research"))
        if data.get("data") and any(v.get("synthetic") for v in data["data"].values()):
            items.append(Item("Forschung auf echten Daten", False, "Bericht basiert auf synthetischen Daten"))
    else:
        items.append(Item("Forschungsbericht vorhanden", False, "kein results.json angegeben/gefunden"))

    # 2. Paper-Phase
    if journal is not None:
        eq = journal.query("SELECT MIN(ts) AS a, MAX(ts) AS b FROM equity")
        days = 0.0
        if eq and eq[0]["a"]:
            days = (datetime.fromisoformat(eq[0]["b"]) - datetime.fromisoformat(eq[0]["a"])).total_seconds() / 86400
        n = journal.query("SELECT COUNT(*) AS n FROM trades")[0]["n"]
        items.append(Item("Paper-Dauer", days >= min_paper_days, f"{days:.0f} Tage (min. {min_paper_days})"))
        items.append(Item("Paper-Trades", n >= min_paper_trades, f"{n} Trades (min. {min_paper_trades})"))
        crit = journal.query("SELECT COUNT(*) AS n FROM events WHERE level='CRITICAL'")[0]["n"]
        items.append(Item("Keine kritischen Ereignisse im Paper-Betrieb", crit == 0, f"{crit} CRITICAL-Ereignisse"))
        risk = journal.get("risk_state", {}) or {}
        items.append(Item("Kill Switch nicht ausgelöst", not risk.get("killed"), risk.get("kill_reason") or "ok"))
        hb = journal.query("SELECT ts FROM heartbeat ORDER BY ts DESC LIMIT 1")
        if hb:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(hb[0]["ts"])).total_seconds() / 60
            items.append(Item("Paper-Bot läuft stabil (Heartbeat)", age < 30, f"letzter Heartbeat vor {age:.0f} min"))
    else:
        items.append(Item("Paper-Journal vorhanden", False, "kein Journal angegeben"))

    # 3. Backtest vs. Forward
    if forward is not None:
        gap = abs(forward["return"]["gap"])
        items.append(Item("Rendite Paper ≈ Backtest", gap <= max_return_gap,
                          f"Differenz {forward['return']['gap']:+.2%} (max. ±{max_return_gap:.0%})"))
        sg = forward["entry_slippage_gap_bps"]["mean"]
        items.append(Item("Slippage-Lücke klein", sg == sg and sg <= max_slippage_gap_bps,
                          f"Ø {sg:.1f} bps (max. {max_slippage_gap_bps})"))
        sd = forward["signal_drift"]["share_identical"]
        items.append(Item("Signale identisch zum Backtest", sd == sd and sd >= 0.95, f"{sd:.0%} identisch"))
    else:
        items.append(Item("Backtest-vs-Forward-Vergleich", False, "nicht durchgeführt (quantbot compare)"))

    # 4. Konfiguration und Sicherheit
    r = cfg.risk
    items.append(Item("Konservativer Hebel", r.max_leverage <= 2.0, f"max_leverage {r.max_leverage}"))
    items.append(Item("Risiko pro Trade ≤ 1 %", r.risk_per_trade <= 0.01, f"{r.risk_per_trade:.2%}"))
    items.append(Item("Max-Drawdown-Kill-Switch ≤ 25 %", r.max_drawdown_limit <= 0.25, f"{r.max_drawdown_limit:.0%}"))
    items.append(Item("API-Schlüssel gesetzt (Wert wird nicht angezeigt)",
                      bool(os.environ.get("QUANTBOT_API_KEY") and os.environ.get("QUANTBOT_API_SECRET")),
                      "QUANTBOT_API_KEY / QUANTBOT_API_SECRET"))
    items.append(Item("API-Schlüssel ohne Auszahlungsrecht", None,
                      "bei der Börse manuell prüfen: nur 'Futures Trading', KEIN 'Withdrawals'; IP-Beschränkung empfohlen"))
    items.append(Item("Kleines Startkapital, dessen Verlust verkraftbar ist", None, "manuell"))
    items.append(Item("LIVE bleibt aus, bis alles oben erfüllt ist", not cfg.live.enabled,
                      "live.enabled ist " + str(cfg.live.enabled)))
    return items


def format_readiness(items: list[Item]) -> str:
    auto = [i for i in items if i.ok is not None]
    ready = all(i.ok for i in auto)
    lines = ["# Live-Readiness", "",
             f"**Ergebnis: {'TECHNISCH BEREIT (manuelle Punkte prüfen)' if ready else 'NICHT BEREIT'}**", "",
             "LIVE wird hierdurch nicht aktiviert. Aktivierung nur manuell: live.enabled: true + "
             "TRADING_MODE=live + QUANTBOT_LIVE_CONFIRM.", ""]
    for i in items:
        mark = "☐" if i.ok is None else ("✅" if i.ok else "❌")
        lines.append(f"- {mark} {i.name}: {i.detail}")
    return "\n".join(lines)
