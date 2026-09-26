"""Forschungsbericht als Markdown + JSON. Negative Ergebnisse werden vollständig ausgewiesen."""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

from ..backtesting.metadata import git_commit
from .pipeline import CandidateReport


def _f(x, pct=False, d=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "n/a"
    return f"{x * 100:+.1f} %" if pct else f"{x:.{d}f}"


def _row(name, m):
    return (f"| {name} | {_f(m.get('sharpe'))} | {_f(m.get('total_return'), True)} | {_f(m.get('cagr'), True)} | "
            f"{_f(m.get('max_drawdown'), True)} | {_f(m.get('profit_factor'))} | {m.get('trades', 'n/a')} | "
            f"{_f(m.get('avg_leverage_at_entry'))}x | {_f(m.get('benchmark_sharpe'))} |")


HEADER = ("| | Sharpe | Rendite | CAGR | Max-DD | Profit Factor | Trades | Ø Hebel | Sharpe Buy&Hold |\n"
          "|---|---|---|---|---|---|---|---|---|")


def write_report(result: dict, data_meta: dict, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    reps: list[CandidateReport] = result["reports"] + result["ensembles"]
    synthetic = any(v.get("synthetic") for v in data_meta.values())
    lines = [f"# Forschungsbericht {result['timeframe']}", ""]
    if synthetic:
        lines += ["> **ACHTUNG: SYNTHETISCHE DATEN. Dieser Bericht ist ein Funktionstest und enthält "
                  "keinerlei Aussage über echte Märkte.**", ""]
    lines += [f"Git: `{git_commit()}`", "", "Zeiträume:", ""]
    lines += [f"- {v}" for v in result["splits"].values()]
    lines += ["", "Daten:", ""]
    for s, v in data_meta.items():
        lines.append(f"- {s}: {v['rows']} Kerzen, Hash `{v['hash']}`, Funding-Historie: {v['funding_history']}")

    finalists = [r for r in reps if r.oos is not None]
    passed = [r for r in finalists if r.passed_pre_oos and all(c.passed for c in r.checks)]
    lines += ["", "## Ergebnis", ""]
    if not passed:
        lines += ["**Keine Strategie hat alle Stufen inklusive Out-of-Sample bestanden. "
                  "NO TRADE ist das Ergebnis dieses Laufs.**", ""]
    else:
        lines += ["Alle Stufen bestanden (noch zu bestätigen im Paper Trading):", ""]
        lines += [f"- **{r.name}** {r.params if r.family != 'ensemble' else r.params.get('members')}" for r in passed]
    lines += ["", "## Übersicht aller Strategien", "",
              "| Strategie | Klasse | erste nicht bestandene Prüfung |", "|---|---|---|"]
    for r in reps:
        fail = next((c for c in r.checks if not c.passed), None)
        lines.append(f"| {r.name} | {r.family} | {('❌ ' + fail.name + ': ' + fail.detail) if fail else '✅ alle bestanden'} |")

    for r in reps:
        lines += ["", f"## {r.name} ({r.family})", "", f"Parameter: `{r.params}`", ""]
        lines += [f"- {'✅' if c.passed else '❌'} {c.name}: {c.detail}" for c in r.checks]
        table = [(k, r.stages[k]) for k in ("A_train", "B_validation", "D_research_period") if k in r.stages]
        if r.oos:
            table.append(("F_out_of_sample", r.oos))
        if table:
            lines += ["", HEADER] + [_row(k, m) for k, m in table]
        if "D_stress" in r.stages:
            lines += ["", "Stresstests (Train+Validation):", "", HEADER]
            lines += [_row(k, m) for k, m in r.stages["D_stress"].items()]
        if "C_walk_forward" in r.stages:
            wf = r.stages["C_walk_forward"]
            lines += ["", f"Walk-Forward: fest Sharpe {_f(wf['fixed']['sharpe'])} / Rendite "
                          f"{_f(wf['fixed']['total_return'], True)}; adaptiv Sharpe {_f(wf['adaptive']['sharpe'])} / "
                          f"Rendite {_f(wf['adaptive']['total_return'], True)}"]
        if "D_monte_carlo" in r.stages and r.stages["D_monte_carlo"].get("runs"):
            mc = r.stages["D_monte_carlo"]
            lines += ["", f"Monte Carlo ({mc['runs']} Läufe): Rendite p05/p50/p95 {_f(mc['return_p05'], True)} / "
                          f"{_f(mc['return_p50'], True)} / {_f(mc['return_p95'], True)}, Max-DD p50 "
                          f"{_f(mc['max_dd_p50'], True)}, p95 {_f(mc['max_dd_p95'], True)}, "
                          f"Verlustwahrscheinlichkeit {mc['prob_loss']:.0%}"]
        if "D_breakdown" in r.stages:
            bd = r.stages["D_breakdown"]
            yr = ", ".join(f"{y}: {_f(v, True)}" for y, v in bd["yearly_return"].items())
            lines += ["", f"Jahre: {yr}"]
            if bd["by_regime"]:
                lines += ["", "| Regime | Trades | Trefferquote | Ø Rendite/Trade | Netto-PnL |", "|---|---|---|---|---|"]
                for k, v in bd["by_regime"].items():
                    lines.append(f"| {k} | {v['trades']} | {v['win_rate']:.0%} | {v['mean_return_pct']:+.2f} % | {v['net_pnl']:.0f} |")
        if "A_screen" in r.stages:
            s = r.stages["A_screen"]["summary"]
            if s.get("combos"):
                lines += ["", f"Parameterraster (Train): {s['combos']} Kombinationen, {s['positive_share']:.0%} mit "
                              f"Sharpe > 0, Median {_f(s['median'])}, bester Einzelwert {_f(s['best'])}, "
                              f"robuster Wert {_f(s['robust_score'])}, Plateau {_f(s.get('plateau_ratio'))}"]
    path = out / "REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "timeframe": result["timeframe"],
        "splits": result["splits"],
        "data": data_meta,
        "git_commit": git_commit(),
        "reports": [dataclasses.asdict(r) for r in reps],
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    return path
