"""Wie verändert sich das Ergebnis bei mehr Risiko/Hebel? (Analyse, keine Empfehlung)"""

from __future__ import annotations

from ..config.schema import HARD_MAX_LEVERAGE
from .runner import Prepared, run
from .splits import Period


def risk_scaling(prep: Prepared, period: Period, multipliers=(0.5, 1.0, 2.0, 4.0)) -> list[dict]:
    base = prep.cfg.risk
    rows = []
    for m in multipliers:
        lev = min(max(base.max_leverage * m, 1.0), HARD_MAX_LEVERAGE)
        over = {
            "risk_per_trade": min(base.risk_per_trade * m, 0.02),
            "max_leverage": lev,
            "max_gross_exposure": min(base.max_gross_exposure * m, lev),
            "max_symbol_exposure": min(base.max_symbol_exposure * m, lev),
            "max_net_exposure": min(base.max_net_exposure * m, lev),
            "max_drawdown_limit": 0.99,  # hier bewusst ohne Kill Switch, um das Rohverhalten zu sehen
            "daily_loss_limit": 0.5, "weekly_loss_limit": 0.6,
        }
        res = run(prep, start=period.start, end=period.end, risk_overrides=over, label=f"risk_x{m}")
        mt = res.metrics
        rows.append({"risk_multiplier": m, "risk_per_trade": over["risk_per_trade"], "max_leverage": lev,
                     "total_return": mt["total_return"], "cagr": mt["cagr"], "sharpe": mt["sharpe"],
                     "max_drawdown": mt["max_drawdown"], "avg_gross_exposure": mt["avg_gross_exposure"],
                     "liquidations": mt["liquidations"]})
    return rows
