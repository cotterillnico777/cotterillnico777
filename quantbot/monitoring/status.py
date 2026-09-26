"""Statusübersicht aus dem Journal (für Terminal und spätere Dashboards)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .journal import Journal


def status_report(journal: Journal, kill_switch_file: str) -> dict:
    hb = journal.query("SELECT * FROM heartbeat ORDER BY ts DESC LIMIT 1")
    run = journal.query("SELECT id, mode, started_at, git_commit FROM runs ORDER BY started_at DESC LIMIT 1")
    eq = journal.query("SELECT * FROM equity ORDER BY rowid DESC LIMIT 1")
    peak = journal.query("SELECT MAX(equity) AS p FROM equity")
    last_ts = eq[0]["ts"] if eq else None
    positions = journal.query("SELECT * FROM positions WHERE ts=?", (last_ts,)) if last_ts else []
    trade = journal.query("SELECT * FROM trades ORDER BY id DESC LIMIT 1")
    stats = journal.query("SELECT COUNT(*) AS n, SUM(net_pnl) AS pnl, SUM(fees) AS fees, "
                          "SUM(funding) AS funding, AVG(net_pnl > 0) AS win FROM trades")
    errors = journal.query("SELECT ts, level, type, message FROM events WHERE level IN ('ERROR','CRITICAL') "
                           "ORDER BY rowid DESC LIMIT 5")
    risk = journal.get("risk_state", {}) or {}
    age = None
    if hb:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(hb[0]["ts"])).total_seconds()
    return {
        "run": dict(run[0]) if run else None,
        "heartbeat": dict(hb[0]) if hb else None,
        "heartbeat_age_s": age,
        "equity": dict(eq[0]) if eq else None,
        "peak_equity": peak[0]["p"] if peak else None,
        "positions": [dict(p) for p in positions],
        "last_trade": dict(trade[0]) if trade else None,
        "trade_stats": dict(stats[0]) if stats else {},
        "recent_errors": [dict(e) for e in errors],
        "risk": {"killed": risk.get("killed"), "kill_reason": risk.get("kill_reason"),
                 "cooldown_until": risk.get("cooldown_until"), "blocks": risk.get("blocks"),
                 "consecutive_losses": risk.get("consecutive_losses")},
        "kill_switch_file": Path(kill_switch_file).exists(),
    }


def format_status(st: dict) -> str:
    lines = []
    if st["run"]:
        lines.append(f"Lauf {st['run']['id']} ({st['run']['mode'].upper()}), gestartet {st['run']['started_at']}")
    hb = st["heartbeat"]
    if hb:
        warn = "  <-- ALT!" if st["heartbeat_age_s"] and st["heartbeat_age_s"] > 600 else ""
        lines.append(f"Heartbeat: {hb['status']} vor {st['heartbeat_age_s']:.0f}s ({hb['detail']}){warn}")
    else:
        lines.append("Kein Heartbeat: Bot lief noch nie mit diesem Journal")
    if st["equity"]:
        e = st["equity"]
        lines.append(f"Equity {e['equity']:.2f} (Höchststand {st['peak_equity']:.2f}, Drawdown {e['drawdown']:.2%}), "
                     f"Exposure brutto {e['gross_exposure']:.2f}x netto {e['net_exposure']:+.2f}x")
    for p in st["positions"]:
        lines.append(f"  {p['symbol']}: {p['qty']:+.6f} @ {p['entry_price']:.4f}, Stop {p['stop']}, "
                     f"TP {p['take_profit']}, unrealisiert {p['unrealized']:+.2f}")
    ts = st["trade_stats"]
    if ts and ts.get("n"):
        lines.append(f"Trades {ts['n']}, Netto-PnL {ts['pnl']:+.2f}, Gebühren {ts['fees']:.2f}, "
                     f"Funding {ts['funding'] or 0:.2f}, Trefferquote {ts['win']:.0%}")
    if st["last_trade"]:
        t = st["last_trade"]
        lines.append(f"Letzter Trade: {t['symbol']} {t['direction']} {t['net_pnl']:+.2f} ({t['exit_reason']}, "
                     f"{t['strategy']}, Regime {t['regime']})")
    r = st["risk"]
    lines.append(f"Risiko: Kill Switch {'AKTIV: ' + str(r['kill_reason']) if r['killed'] else 'aus'}, "
                 f"Verlustserie {r['consecutive_losses']}, Eingriffe {r['blocks']}")
    if st["kill_switch_file"]:
        lines.append("STOP-Datei vorhanden: keine neuen Positionen")
    for e in st["recent_errors"]:
        lines.append(f"  {e['ts']} {e['level']} {e['type']}: {e['message']}")
    return "\n".join(lines)
