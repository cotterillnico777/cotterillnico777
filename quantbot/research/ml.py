"""ML-Meta-Filter (wahrscheinlichkeitsbasiert) – nur einsetzen, wenn er Out-of-Sample klar hilft.

Vorgehen (zeitlich sauber, kein Zufalls-Split):
  1. Trades der Strategie im Train-Zeitraum -> Features bei Einstieg, Label = Gewinn (net_pnl > 0)
  2. Logistische Regression (L2, standardisiert) nur auf Train
  3. Entscheidungsregel: erwarteter Vorteil = p × Ø Gewinn − (1−p) × Ø Verlust (aus Train) > 0
  4. Bewertung auf Validation gegen: (a) kein Filter, (b) einfache Regel "nur starke Signale"
Nur wenn (3) auf Validation (a) UND (b) klar schlägt, gilt ML als nützlich.

Hinweis: Das Filtern erfolgt nachträglich auf Trade-Ebene (Pfadabhängigkeit der Positionsgrößen
wird ignoriert). Das ist für die Frage "hat das Modell Vorhersagekraft?" ausreichend.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd


def _features(trades: pd.DataFrame) -> pd.DataFrame:
    t = trades
    rows = []
    for _, r in t.iterrows():
        f = json.loads(r["features"]) if isinstance(r.get("features"), str) and r["features"] else {}
        f = {k: v for k, v in f.items() if isinstance(v, (int, float)) and math.isfinite(v)}
        f["signal_strength"] = abs(float(r.get("signal_strength") or 0.0))
        f["is_long"] = 1.0 if r.get("direction") == "long" else 0.0
        reg = str(r.get("regime") or "unknown|unknown").split("|")
        for name in ("bull", "bear", "sideways"):
            f[f"trend_{name}"] = 1.0 if reg[0] == name else 0.0
        for name in ("high", "low"):
            f[f"vol_{name}"] = 1.0 if len(reg) > 1 and reg[1] == name else 0.0
        rows.append(f)
    return pd.DataFrame(rows, index=t.index).fillna(0.0)


class Logistic:
    def __init__(self, l2: float = 1.0, iters: int = 500, lr: float = 0.1) -> None:
        self.l2, self.iters, self.lr = l2, iters, lr

    def fit(self, X: np.ndarray, y: np.ndarray) -> "Logistic":
        self.mu, self.sd = X.mean(0), X.std(0)
        self.sd[self.sd == 0] = 1.0
        Z = (X - self.mu) / self.sd
        n, k = Z.shape
        self.w, self.b = np.zeros(k), float(np.log((y.mean() + 1e-6) / (1 - y.mean() + 1e-6)))
        for _ in range(self.iters):
            p = 1 / (1 + np.exp(-(Z @ self.w + self.b)))
            g = p - y
            self.w -= self.lr * (Z.T @ g / n + self.l2 * self.w / n)
            self.b -= self.lr * g.mean()
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        Z = (X - self.mu) / self.sd
        return 1 / (1 + np.exp(-(Z @ self.w + self.b)))


def auc(y: np.ndarray, p: np.ndarray) -> float:
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank().values
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def evaluate_meta_filter(train_trades: pd.DataFrame, val_trades: pd.DataFrame, min_trades: int = 30) -> dict:
    if len(train_trades) < min_trades or len(val_trades) < 10:
        return {"verdict": "zu wenige Trades für ML", "train_trades": len(train_trades),
                "val_trades": len(val_trades), "use_ml": False}
    Ftr, Fva = _features(train_trades), _features(val_trades)
    cols = sorted(set(Ftr.columns) | set(Fva.columns))
    Xtr, Xva = Ftr.reindex(columns=cols, fill_value=0.0).values, Fva.reindex(columns=cols, fill_value=0.0).values
    ytr = (train_trades["net_pnl"].values > 0).astype(float)
    yva = (val_trades["net_pnl"].values > 0).astype(float)
    model = Logistic().fit(Xtr, ytr)
    ptr, pva = model.predict(Xtr), model.predict(Xva)
    wins, losses = train_trades["net_pnl"][ytr == 1], train_trades["net_pnl"][ytr == 0]
    avg_w, avg_l = float(wins.mean()) if len(wins) else 0.0, float(-losses.mean()) if len(losses) else 0.0
    edge_va = pva * avg_w - (1 - pva) * avg_l
    take_ml = edge_va > 0
    strong = val_trades["signal_strength"].abs().values >= 0.67 if "signal_strength" in val_trades else np.ones(len(yva), bool)
    pnl = val_trades["net_pnl"].values

    def summary(mask):
        sel = pnl[mask]
        return {"trades": int(mask.sum()), "net_pnl": float(sel.sum()),
                "expectancy": float(sel.mean()) if len(sel) else 0.0,
                "win_rate": float((sel > 0).mean()) if len(sel) else 0.0}

    base, ml, rule = summary(np.ones(len(pnl), bool)), summary(take_ml), summary(strong)
    val_auc = auc(yva, pva)
    better = (ml["trades"] >= 10 and ml["expectancy"] > base["expectancy"] * 1.2 + 1e-9
              and ml["expectancy"] > rule["expectancy"] and ml["net_pnl"] > base["net_pnl"]
              and val_auc == val_auc and val_auc >= 0.55)
    importance = dict(sorted(zip(cols, np.abs(model.w)), key=lambda x: -x[1])[:10])
    return {
        "train_auc": auc(ytr, ptr), "val_auc": val_auc,
        "baseline": base, "ml_filter": ml, "simple_rule_strong_signal": rule,
        "feature_importance_abs_weight": {k: float(v) for k, v in importance.items()},
        "use_ml": bool(better),
        "verdict": ("ML-Filter verbessert die Validierung klar – im Walk-Forward und Paper weiter prüfen"
                    if better else "Kein klarer Out-of-Sample-Vorteil: ML wird NICHT eingesetzt"),
    }
