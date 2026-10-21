"""Walk-Forward-Backtest: Modell wird vor jedem Spieltag nur mit Daten bis dahin
trainiert und sagt dann die Spiele dieses Spieltags voraus. Kein Blick in die Zukunft.

Ohne historische Quoten lässt sich hier nur die *Prognosegüte* messen (Log-Loss,
Brier). Rendite misst `roi_backtest` mit Quoten-CSVs (Format football-data.co.uk).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .markets import market_probs
from .model import DixonColes


def walk_forward(df: pd.DataFrame, comp: str = "UCL", start: str = "2023-09-01",
                 **model_kw) -> pd.DataFrame:
    test = df[(df["comp"] == comp) & (df["date"] >= start)].copy()
    test["week"] = test["date"].dt.to_period("W")
    rows = []
    for _, chunk in test.groupby("week"):
        model = DixonColes(**model_kw).fit(df, as_of=chunk["date"].min())
        for r in chunk.itertuples():
            if r.home_key not in model.params["grp"] or r.away_key not in model.params["grp"]:
                continue
            p = market_probs(model.score_matrix(r.home_key, r.away_key, r.neutral))
            res = "H" if r.hg > r.ag else "D" if r.hg == r.ag else "A"
            rows.append(dict(date=r.date, home=r.home, away=r.away, hg=r.hg, ag=r.ag, res=res,
                             pH=p["1X2"]["H"], pD=p["1X2"]["D"], pA=p["1X2"]["A"],
                             pO25=p["OU2.5"]["O"], pBTTS=p["BTTS"]["Y"]))
    return pd.DataFrame(rows)


def scores(pred: pd.DataFrame) -> dict[str, float]:
    P = pred[["pH", "pD", "pA"]].to_numpy()
    Y = np.stack([(pred.res == s).to_numpy(float) for s in "HDA"], axis=1)
    o25 = ((pred.hg + pred.ag) > 2.5).to_numpy(float)
    btts = ((pred.hg > 0) & (pred.ag > 0)).to_numpy(float)
    base = Y.mean(axis=0)
    ll = lambda p, y: float(-np.mean(np.log(np.clip((p * y).sum(axis=1), 1e-12, None))))
    bll = lambda p, y: float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    return {
        "spiele": len(pred),
        "logloss_1x2": ll(P, Y),
        "logloss_1x2_basis": ll(np.tile(base, (len(Y), 1)), Y),
        "brier_1x2": float(np.mean(np.sum((P - Y) ** 2, axis=1))),
        "logloss_ou25": bll(pred.pO25.to_numpy(), o25),
        "logloss_ou25_basis": bll(np.full(len(o25), o25.mean()), o25),
        "logloss_btts": bll(pred.pBTTS.to_numpy(), btts),
        "logloss_btts_basis": bll(np.full(len(btts), btts.mean()), btts),
    }


def calibration(pred: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    """Vorhergesagte vs. tatsächliche Häufigkeit über alle 1X2-Selektionen."""
    p = np.concatenate([pred.pH, pred.pD, pred.pA])
    y = np.concatenate([(pred.res == s).astype(float) for s in "HDA"])
    b = pd.cut(p, np.linspace(0, 1, bins + 1))
    return (pd.DataFrame({"bin": b, "p": p, "y": y}).groupby("bin", observed=True)
            .agg(n=("y", "size"), vorhergesagt=("p", "mean"), eingetreten=("y", "mean")))
