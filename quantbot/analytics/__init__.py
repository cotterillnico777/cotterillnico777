"""Auswertungen über Trades und Kapitalkurven (Backtest, Paper oder Live)."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd


def _group_stats(g: pd.DataFrame) -> dict:
    pnl = g["net_pnl"]
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl <= 0].sum()
    out = {
        "trades": int(len(g)),
        "net_pnl": float(pnl.sum()),
        "win_rate": float((pnl > 0).mean()),
        "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
        "avg_pnl": float(pnl.mean()),
    }
    if "r_multiple" in g and g["r_multiple"].notna().any():
        out["avg_r"] = float(g["r_multiple"].mean())
    return out


def breakdown(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    if trades.empty or by not in trades:
        return pd.DataFrame()
    rows = {str(k): _group_stats(g) for k, g in trades.groupby(by, dropna=False)}
    return pd.DataFrame(rows).T.sort_values("net_pnl", ascending=False)


def enrich(trades: pd.DataFrame) -> pd.DataFrame:
    """Abgeleitete Spalten: Stunde, Richtung, Regime-Teile, Stärke-/Hebel-Klassen, Features."""
    t = trades.copy()
    if t.empty:
        return t
    t["entry_time"] = pd.to_datetime(t["entry_time"], utc=True, errors="coerce")
    t["entry_hour_utc"] = t["entry_time"].dt.hour
    t["weekday"] = t["entry_time"].dt.day_name()
    if "regime" in t:
        parts = t["regime"].fillna("unknown|unknown").astype(str).str.split("|")
        t["trend_regime"] = parts.str[0]
        t["vol_regime"] = parts.str[1]
    if "signal_strength" in t:
        s = t["signal_strength"].abs()
        t["strength_bucket"] = pd.cut(s, [0, 0.34, 0.67, 1.01], labels=["schwach", "mittel", "stark"])
    if "leverage" in t:
        t["leverage_bucket"] = pd.cut(t["leverage"].astype(float), [0, 0.5, 1, 1.5, 2, 5, np.inf],
                                      labels=["<0.5x", "0.5-1x", "1-1.5x", "1.5-2x", "2-5x", ">5x"])
    if "features" in t:
        feats = t["features"].apply(lambda x: json.loads(x) if isinstance(x, str) and x else {})
        f = pd.DataFrame(list(feats.values), index=t.index).add_prefix("feat_")
        t = pd.concat([t, f], axis=1)
    return t


def winner_loser_profile(trades: pd.DataFrame) -> pd.DataFrame:
    """Numerische Merkmale: Mittel bei Gewinnern vs. Verlierern + standardisierte Differenz."""
    t = trades
    if t.empty:
        return pd.DataFrame()
    num = [c for c in t.columns if pd.api.types.is_numeric_dtype(t[c]) and c not in
           ("net_pnl", "gross_pnl", "return_pct", "r_multiple", "exit_price", "fees", "slippage_cost")]
    win = t["net_pnl"] > 0
    rows = {}
    for c in num:
        a, b = t.loc[win, c].astype(float), t.loc[~win, c].astype(float)
        if a.notna().sum() < 3 or b.notna().sum() < 3:
            continue
        sd = t[c].astype(float).std()
        rows[c] = {"gewinner": a.mean(), "verlierer": b.mean(),
                   "std_diff": (a.mean() - b.mean()) / sd if sd and sd > 0 else np.nan}
    df = pd.DataFrame(rows).T
    return df.reindex(df["std_diff"].abs().sort_values(ascending=False).index) if len(df) else df


def drawdown_episodes(equity: pd.Series, top: int = 5) -> pd.DataFrame:
    eq = equity.dropna()
    peak = eq.cummax()
    dd = eq / peak - 1
    episodes = []
    in_dd, start = False, None
    for ts, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, ts
        elif v >= 0 and in_dd:
            seg = dd[start:ts]
            episodes.append((start, seg.idxmin(), ts, float(seg.min())))
            in_dd = False
    if in_dd:
        seg = dd[start:]
        episodes.append((start, seg.idxmin(), None, float(seg.min())))
    df = pd.DataFrame(episodes, columns=["start", "tiefpunkt", "erholt", "tiefe"])
    return df.sort_values("tiefe").head(top).reset_index(drop=True)


def drawdown_contributors(trades: pd.DataFrame, start, end) -> pd.DataFrame:
    """Welche Symbole/Strategien haben in einem Drawdown-Zeitraum verloren?"""
    if trades.empty:
        return pd.DataFrame()
    t = trades.copy()
    t["exit_time"] = pd.to_datetime(t["exit_time"], utc=True, errors="coerce")
    sel = t[(t["exit_time"] >= start) & ((t["exit_time"] <= end) if end is not None else True)]
    if sel.empty:
        return pd.DataFrame()
    return sel.groupby(["symbol", "strategy"], dropna=False)["net_pnl"].sum().sort_values().to_frame()


def full_report(trades: pd.DataFrame, equity: pd.Series | None = None) -> str:
    t = enrich(trades)
    lines = ["# Trade-Analyse", ""]
    if t.empty:
        return "\n".join(lines + ["Keine Trades vorhanden."])
    lines += [f"{len(t)} Trades, Netto-PnL {t['net_pnl'].sum():+.2f}", ""]
    for by, title in [("strategy", "Strategie"), ("symbol", "Asset"), ("direction", "Richtung"),
                      ("trend_regime", "Trend-Regime"), ("vol_regime", "Vola-Regime"),
                      ("entry_hour_utc", "Einstiegsstunde (UTC)"), ("weekday", "Wochentag"),
                      ("strength_bucket", "Signalstärke"), ("leverage_bucket", "Hebel bei Einstieg"),
                      ("exit_reason", "Ausstiegsgrund")]:
        b = breakdown(t, by)
        if len(b):
            lines += [f"## Nach {title}", "", _md(b), ""]
    prof = winner_loser_profile(t)
    if len(prof):
        lines += ["## Was unterscheidet Gewinner von Verlierern?", "",
                  "Standardisierte Differenz (|x| > 0.3 = deutlicher Unterschied; Korrelation ist keine Kausalität):",
                  "", _md(prof.head(15)), ""]
    if equity is not None and len(equity) > 2:
        eps = drawdown_episodes(equity)
        lines += ["## Größte Drawdowns", "", _md(eps), ""]
        for _, e in eps.head(3).iterrows():
            c = drawdown_contributors(trades, e["start"], e["erholt"])
            if len(c):
                lines += [f"Beiträge im Drawdown ab {e['start']}:", "", _md(c.head(8)), ""]
    return "\n".join(lines)


def _md(df: pd.DataFrame) -> str:
    def fmt(v):
        if isinstance(v, float):
            if math.isnan(v):
                return "n/a"
            if math.isinf(v):
                return "∞"
            return str(int(v)) if v.is_integer() and abs(v) < 1e9 else f"{v:.3f}"
        return str(v)

    cols = list(df.columns)
    out = ["| | " + " | ".join(map(str, cols)) + " |", "|---" * (len(cols) + 1) + "|"]
    for idx, row in df.iterrows():
        out.append(f"| {idx} | " + " | ".join(fmt(row[c]) for c in cols) + " |")
    return "\n".join(out)


def journal_trades(journal) -> pd.DataFrame:
    rows = journal.query("SELECT * FROM trades ORDER BY id")
    return pd.DataFrame([dict(r) for r in rows])


def journal_equity(journal) -> pd.Series:
    rows = journal.query("SELECT ts, equity FROM equity ORDER BY rowid")
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series([r["equity"] for r in rows], index=pd.to_datetime([r["ts"] for r in rows], utc=True))
    return s[~s.index.duplicated(keep="last")]
