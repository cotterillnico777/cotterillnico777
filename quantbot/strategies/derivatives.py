"""Derivate-Daten. Nur Funding: dessen Historie ist vollständig verfügbar.

Open Interest, Liquidationen und Long/Short-Ratio sind bei Binance nur ca. 30 Tage
historisch abrufbar und werden deshalb bewusst NICHT verwendet (siehe docs/PLAN.md, A4).
"""

from __future__ import annotations

import pandas as pd

from .. import indicators as ind
from .base import Strategy


class FundingContrarian(Strategy):
    """Extremes Funding = überfüllte Seite. Z-Score > entry -> short, < -entry -> long."""

    name, family = "funding_contrarian", "derivatives"
    default_params = {"n_periods": 90, "entry": 2.0, "exit": 0.5, "atr_mult": 3.0, "allow_short": True}
    param_grid = {"n_periods": [30, 90, 180], "entry": [1.5, 2.0, 2.5], "atr_mult": [2.0, 3.0]}

    @property
    def warmup(self):
        return 50

    def compute(self, df, ctx):
        p = self.params
        if ctx.funding is None:
            raise ValueError("funding_contrarian braucht Funding-Historie")
        f = ctx.funding.dropna()  # je Funding-Zeitpunkt T, bekannt ab T
        # Z-Score über Funding-Perioden; sichtbar ab der Kerze, die bei T beginnt (Entscheidung
        # erst zu deren Schluss) -> keine Zukunftsdaten
        z = ind.zscore(f, p["n_periods"])
        z = z.reindex(df.index.union(z.index)).ffill().reindex(df.index)
        rate = f.reindex(df.index.union(f.index)).ffill().reindex(df.index)
        short = p["allow_short"]
        sig = ind.hold_state(z < -p["entry"], z > -p["exit"],
                             (z > p["entry"]) if short else None, (z < p["exit"]) if short else None)
        return self.output(sig, p["atr_mult"] * ind.atr(df, 14), funding_z=z, funding=rate)
