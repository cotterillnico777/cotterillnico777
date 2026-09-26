"""Kennzahlen. Rendite allein ist nie das Kriterium."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..core.timeframes import periods_per_year, tf_seconds


def drawdown_stats(equity: pd.Series) -> dict:
    peak = equity.cummax()
    dd = equity / peak - 1
    max_dd = float(dd.min()) if len(dd) else 0.0
    # Längste Phase unter Höchststand und Erholungszeit des tiefsten Drawdowns
    underwater = dd < 0
    longest = cur = 0
    for u in underwater.values:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    trough = dd.idxmin() if len(dd) else None
    recovery_bars = None
    if trough is not None and max_dd < 0:
        after = equity[equity.index >= trough]
        peak_before = peak[trough]
        rec = after[after >= peak_before]
        if len(rec):
            recovery_bars = int(equity.index.get_loc(rec.index[0]) - equity.index.get_loc(trough))
    return {"max_drawdown": max_dd, "longest_underwater_bars": longest, "recovery_bars": recovery_bars}


def longest_losing_streak(pnl: pd.Series) -> int:
    longest = cur = 0
    for v in pnl.values:
        cur = cur + 1 if v < 0 else 0
        longest = max(longest, cur)
    return longest


def compute_metrics(
    equity: pd.Series,
    trades: pd.DataFrame,
    exposure: pd.DataFrame,
    timeframe: str,
    initial: float,
    fills: pd.DataFrame | None = None,
) -> dict:
    ppy = periods_per_year(timeframe)
    bars_per_day = 86400 / tf_seconds(timeframe)
    years = len(equity) / ppy
    final = float(equity.iloc[-1])
    total_return = final / initial - 1
    cagr = (final / initial) ** (1 / years) - 1 if years > 0 and final > 0 else -1.0

    rets = equity.pct_change().dropna()
    std = rets.std()
    sharpe = rets.mean() / std * math.sqrt(ppy) if std and std > 0 else 0.0
    downside = rets[rets < 0]
    dstd = math.sqrt((downside**2).sum() / len(rets)) if len(rets) else 0.0
    sortino = rets.mean() / dstd * math.sqrt(ppy) if dstd > 0 else 0.0
    dd = drawdown_stats(equity)
    calmar = cagr / abs(dd["max_drawdown"]) if dd["max_drawdown"] < 0 else 0.0

    # Tagesrenditen für VaR / Expected Shortfall
    daily = equity.resample("1D").last().pct_change().dropna()
    var95 = float(-np.quantile(daily, 0.05)) if len(daily) > 20 else float("nan")
    es95 = float(-daily[daily <= -var95].mean()) if len(daily) > 20 and (daily <= -var95).any() else float("nan")

    m = {
        "start": str(equity.index[0]),
        "end": str(equity.index[-1]),
        "years": years,
        "initial": initial,
        "final": final,
        "total_return": total_return,
        "cagr": cagr,
        "volatility": float(std * math.sqrt(ppy)) if std == std else 0.0,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "calmar": float(calmar),
        "max_drawdown": dd["max_drawdown"],
        "longest_underwater_days": dd["longest_underwater_bars"] / bars_per_day,
        "recovery_days": dd["recovery_bars"] / bars_per_day if dd["recovery_bars"] is not None else None,
        "var_95_daily": var95,
        "es_95_daily": es95,
        "avg_gross_exposure": float(exposure["gross"].mean()) if len(exposure) else 0.0,
        "max_gross_exposure": float(exposure["gross"].max()) if len(exposure) else 0.0,
        "time_in_market": float((exposure["gross"] > 1e-9).mean()) if len(exposure) else 0.0,
    }

    n = len(trades)
    m["trades"] = n
    m["trades_per_year"] = n / years if years > 0 else 0.0
    if n:
        pnl = trades["net_pnl"]
        wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
        gross_win, gross_loss = wins.sum(), -losses.sum()
        m.update(
            win_rate=len(wins) / n,
            avg_win=float(wins.mean()) if len(wins) else 0.0,
            avg_loss=float(losses.mean()) if len(losses) else 0.0,
            payoff_ratio=float(wins.mean() / -losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else float("nan"),
            profit_factor=float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
            expectancy=float(pnl.mean()),
            expectancy_r=float(trades["r_multiple"].mean()) if "r_multiple" in trades and trades["r_multiple"].notna().any() else float("nan"),
            longest_losing_streak=longest_losing_streak(pnl),
            fees=float(trades["fees"].sum()),
            funding=float(trades["funding"].sum()),
            slippage_cost=float(trades["slippage_cost"].sum()),
            avg_bars_held=float(trades["bars"].mean()),
            avg_leverage_at_entry=float(trades["leverage"].replace(np.inf, np.nan).mean()),
            max_leverage_at_entry=float(trades["leverage"].replace(np.inf, np.nan).max()),
        )
    else:
        m.update(win_rate=0.0, avg_win=0.0, avg_loss=0.0, payoff_ratio=float("nan"), profit_factor=float("nan"),
                 expectancy=0.0, expectancy_r=float("nan"), longest_losing_streak=0, fees=0.0, funding=0.0,
                 slippage_cost=0.0, avg_bars_held=0.0, avg_leverage_at_entry=0.0, max_leverage_at_entry=0.0)
    if fills is not None and len(fills):
        traded = float((fills["qty"].abs() * fills["price"]).sum())
        avg_eq = float(equity.mean())
        m["turnover_per_year"] = traded / avg_eq / years if years > 0 and avg_eq > 0 else 0.0
    else:
        m["turnover_per_year"] = 0.0
    return m


def format_metrics(m: dict) -> str:
    def pct(x):
        return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:+.2f} %"

    def num(x, d=2):
        return "n/a" if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else f"{x:.{d}f}"

    lines = [
        f"Zeitraum            {m['start'][:10]} bis {m['end'][:10]} ({m['years']:.2f} J.)",
        f"Gesamtrendite       {pct(m['total_return'])}   CAGR {pct(m['cagr'])}",
        f"Max. Drawdown       {pct(m['max_drawdown'])}   längste Unterwasserphase {num(m['longest_underwater_days'], 0)} Tage, Erholung {num(m['recovery_days'], 0)} Tage",
        f"Sharpe {num(m['sharpe'])}  Sortino {num(m['sortino'])}  Calmar {num(m['calmar'])}  Vola {pct(m['volatility'])}",
        f"VaR95/Tag {pct(m['var_95_daily'])}  ES95/Tag {pct(m['es_95_daily'])}",
        f"Trades {m['trades']} ({num(m['trades_per_year'], 1)}/J.)  Trefferquote {pct(m['win_rate'])}  Profit Factor {num(m['profit_factor'])}  Payoff {num(m['payoff_ratio'])}",
        f"Erwartung/Trade {num(m['expectancy'])} ({num(m['expectancy_r'])} R)  längste Verlustserie {m['longest_losing_streak']}",
        f"Kosten: Gebühren {num(m['fees'])}  Funding {num(m['funding'])}  Slippage {num(m['slippage_cost'])}  Turnover {num(m['turnover_per_year'], 1)}x/J.",
        f"Exposure Ø {num(m['avg_gross_exposure'])}x (max {num(m['max_gross_exposure'])}x), im Markt {pct(m['time_in_market'])}, Hebel bei Einstieg Ø {num(m['avg_leverage_at_entry'])}x",
    ]
    if m.get("liquidations"):
        lines.append(f"LIQUIDATIONEN: {m['liquidations']}")
    if m.get("funding_fallback_symbols"):
        lines.append(f"Hinweis: Funding geschätzt (keine Historie) für {', '.join(m['funding_fallback_symbols'])}")
    return "\n".join(lines)
