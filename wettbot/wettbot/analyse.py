"""Analyse-Tool: Wahrscheinlichkeiten für alle gängigen Ergebnisse eines Spiels.

Mehrere Informationsquellen werden zu einer Prognose kombiniert:

  Torprognose-Modell (Dixon-Coles)   Elo-Stärke (ClubElo)    Form (letzte 5)
  Tordifferenz (letzte 10)           Torschüsse für/gegen     Ecken für/gegen
  Torverteilung auf die Halbzeiten   Quote "über 2,5"/"beide treffen" der Teams

Der "beste Mittelwert" ist keine feste Gewichtung, sondern wird gelernt:
logistische Regressionen auf ~16 000 vergangenen Spielen, deren Gewichte die
Vorhersagefehler (Log-Loss) minimieren. Jede Kennzahl muss sich im Test auf
ungesehenen Spielen bewähren (siehe `evaluate`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import nbinom, poisson

from .data import DATA
from .markets import market_probs
from .model import DixonColes, score_matrix

PARAMS = DATA / "analyse_params.json"
TRAINING = DATA / "raw" / "analyse_training.csv"


# ---------------------------------------------------------------- Merkmale

def features(P, home: str, away: str, as_of) -> dict:
    """Alle Kennzahlen beider Teams, Stand vor dem Spiel."""
    f = {}
    for side, t in (("h", home), ("a", away)):
        fo, go, sc = P.form(t, as_of), P.goals(t, as_of), P.shots_corners(t, as_of)
        f |= {f"{side}_ppg5": fo["ppg"], f"{side}_serie": fo["serie"],
              f"{side}_gf10": go["gf"], f"{side}_ga10": go["ga"],
              f"{side}_anteil2hz": go["anteil_2hz"], f"{side}_nhz": go["n_hz"],
              f"{side}_btts10": go["btts"], f"{side}_o25_10": go["over25"],
              f"{side}_elo": P.elo_at(t, as_of), f"{side}_nstat": sc["n"]}
        f |= {f"{side}_{c}": sc[c] for c in ("sh_f", "sh_a", "sot_f", "sot_a", "co_f", "co_a", "ye_f")}
    return f


def build_training(df: pd.DataFrame, xg: pd.DataFrame, P, xg_to_key: dict,
                   start: str = "2024-10-01", verbose: bool = True) -> pd.DataFrame:
    """Walk-Forward: je Woche Modell nur mit Vergangenheit trainieren, dann
    Prognose + Kennzahlen + tatsächlicher Ausgang je Spiel speichern."""
    dom = xg[xg.date >= start]
    dom = dom.assign(hk=[xg_to_key.get((g, n)) for g, n in zip(dom.grp, dom.HomeTeam)],
                     ak=[xg_to_key.get((g, n)) for g, n in zip(dom.grp, dom.AwayTeam)])
    dom = dom.dropna(subset=["hk", "ak"])
    dom = pd.DataFrame(dict(date=dom.date, hk=dom.hk, ak=dom.ak, comp=dom.grp, euro=False,
                            neutral=False, hg=dom.FTHome, ag=dom.FTAway, hht=dom.HTHome,
                            aht=dom.HTAway, hco=dom.HomeCorners, aco=dom.AwayCorners))
    cl = df[(df.comp == "UCL") & (df.date >= start)]
    cl = pd.DataFrame(dict(date=cl.date, hk=cl.home_key, ak=cl.away_key, comp="UCL", euro=True,
                           neutral=cl.neutral, hg=cl.hg, ag=cl.ag,
                           hht=pd.to_numeric(cl.hht, errors="coerce"),
                           aht=pd.to_numeric(cl.aht, errors="coerce"), hco=np.nan, aco=np.nan))
    target = pd.concat([dom, cl], ignore_index=True).sort_values("date")
    rows = []
    weeks = target.groupby(target.date.dt.to_period("W"))
    for i, (_, chunk) in enumerate(weeks):
        model = DixonColes().fit(df, as_of=chunk.date.min())
        grp = model.params["grp"]
        for r in chunk.itertuples():
            if r.hk not in grp or r.ak not in grp:
                continue
            lh, la = model.expected_goals(r.hk, r.ak, bool(r.neutral), bool(r.euro))
            rows.append(dict(date=r.date, comp=r.comp, heim=r.hk, gast=r.ak, lh=lh, la=la,
                             rho=model.params["rho"], hg=r.hg, ag=r.ag, hht=r.hht, aht=r.aht,
                             hco=r.hco, aco=r.aco, **features(P, r.hk, r.ak, r.date)))
        if verbose and i % 10 == 0:
            print(f"  Woche {i + 1}/{len(weeks)}", flush=True)
    return pd.DataFrame(rows)


# ------------------------------------------------- Merkmalsmatrizen je Markt

def _dc(t: pd.DataFrame):
    probs = [market_probs(score_matrix(lh, la, rho)) for lh, la, rho in zip(t.lh, t.la, t.rho)]
    return pd.DataFrame(dict(
        pH=[p["1X2"]["H"] for p in probs], pD=[p["1X2"]["D"] for p in probs],
        pA=[p["1X2"]["A"] for p in probs], pO25=[p["OU2.5"]["O"] for p in probs],
        pBTTS=[p["BTTS"]["Y"] for p in probs]), index=t.index)


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _fill(x, default=0.0):
    x = pd.to_numeric(x, errors="coerce")
    return x.fillna(default).to_numpy(float), x.isna().to_numpy(float)


# Merkmale je Markt: Name -> Funktion(t, dc) -> Spalte. Fehlende Werte = 0 + Kennzeichen.
def _x_1x2(t, dc):
    elo, elo_na = _fill((t.h_elo - t.a_elo) / 100)
    sot, sot_na = _fill((t.h_sot_f - t.h_sot_a) - (t.a_sot_f - t.a_sot_a))
    return {
        "Torprognose (Heim vs. Gast)": np.log(dc.pH / dc.pA).to_numpy(),
        "Torprognose (Remis)": _logit(dc.pD).to_numpy(),
        "Elo-Differenz": elo, "Elo fehlt": elo_na,
        "Form (Punkte/Spiel, letzte 5)": _fill(t.h_ppg5 - t.a_ppg5)[0],
        "Tordifferenz (letzte 10)": _fill((t.h_gf10 - t.h_ga10) - (t.a_gf10 - t.a_ga10))[0],
        "Torschuss-Bilanz": sot, "Schussdaten fehlen": sot_na,
        "Ecken-Bilanz": _fill((t.h_co_f - t.h_co_a) - (t.a_co_f - t.a_co_a))[0],
    }


def _x_o25(t, dc):
    return {
        "Torprognose (über 2,5)": _logit(dc.pO25).to_numpy(),
        "Tore beider Teams (letzte 10)": _fill(t.h_gf10 + t.h_ga10 + t.a_gf10 + t.a_ga10, 5.2)[0] - 5.2,
        "Anteil Spiele über 2,5": _fill(t.h_o25_10 + t.a_o25_10, 1.0)[0] - 1.0,
        "Torschüsse gesamt": _fill(t.h_sot_f + t.h_sot_a + t.a_sot_f + t.a_sot_a, 17.0)[0] - 17.0,
    }


def _x_btts(t, dc):
    return {
        "Torprognose (beide treffen)": _logit(dc.pBTTS).to_numpy(),
        "Anteil Spiele beide treffen": _fill(t.h_btts10 + t.a_btts10, 1.0)[0] - 1.0,
        "Tore beider Teams (letzte 10)": _fill(t.h_gf10 + t.h_ga10 + t.a_gf10 + t.a_ga10, 5.2)[0] - 5.2,
    }


X_FUNCS = {"1X2": _x_1x2, "OU2.5": _x_o25, "BTTS": _x_btts}


def _y(t, market):
    if market == "1X2":
        return np.select([t.hg > t.ag, t.hg == t.ag], [0, 1], 2)
    if market == "OU2.5":
        return ((t.hg + t.ag) > 2.5).astype(int).to_numpy()
    return ((t.hg > 0) & (t.ag > 0)).astype(int).to_numpy()


# ------------------------------------------------- logistische Regression

def _fit_softmax(X, y, k, l2=1.0):
    n, d = X.shape
    Y = np.eye(k)[y]

    def f(w):
        W = w.reshape(d + 1, k - 1)
        Z = np.c_[np.ones(n), X] @ W
        Z = np.c_[Z, np.zeros(n)]
        Z -= Z.max(axis=1, keepdims=True)
        P = np.exp(Z)
        P /= P.sum(axis=1, keepdims=True)
        loss = -np.sum(Y * np.log(P + 1e-12)) + l2 * np.sum(W[1:] ** 2)
        G = np.c_[np.ones(n), X].T @ (P - Y)[:, : k - 1]
        G[1:] += 2 * l2 * W[1:]
        return loss, G.ravel()

    res = minimize(f, np.zeros((d + 1) * (k - 1)), jac=True, method="L-BFGS-B")
    return res.x.reshape(d + 1, k - 1)


def _predict_softmax(W, X):
    Z = np.c_[np.ones(len(X)), X] @ W
    Z = np.c_[Z, np.zeros(len(X))]
    Z -= Z.max(axis=1, keepdims=True)
    P = np.exp(Z)
    return P / P.sum(axis=1, keepdims=True)


@dataclass
class MarketModel:
    market: str
    names: list
    mean: np.ndarray
    std: np.ndarray
    W: np.ndarray
    k: int

    @classmethod
    def fit(cls, t, dc, market, use=None):
        cols = X_FUNCS[market](t, dc)
        names = [c for c in cols if use is None or c in use]
        X = np.column_stack([cols[c] for c in names])
        mean, std = X.mean(axis=0), X.std(axis=0) + 1e-9
        k = 3 if market == "1X2" else 2
        y = _y(t, market)
        if k == 2:
            y = 1 - y  # Klasse 0 = "ja", Referenz = "nein"
        W = _fit_softmax((X - mean) / std, y, k)
        return cls(market, names, mean, std, W, k)

    def predict(self, t, dc) -> np.ndarray:
        cols = X_FUNCS[self.market](t, dc)
        X = np.column_stack([cols[c] for c in self.names])
        P = _predict_softmax(self.W, (X - self.mean) / self.std)
        return P if self.k == 3 else P[:, 0]

    def weights(self) -> dict:
        """Standardisierte Gewichte (für Klasse Heimsieg bzw. 'ja')."""
        return {n: round(float(w), 3) for n, w in zip(self.names, self.W[1:, 0])}

    def to_json(self):
        return dict(market=self.market, names=self.names, mean=self.mean.tolist(),
                    std=self.std.tolist(), W=self.W.tolist(), k=self.k)

    @classmethod
    def from_json(cls, d):
        return cls(d["market"], d["names"], np.array(d["mean"]), np.array(d["std"]),
                   np.array(d["W"]), d["k"])


# ------------------------------------------------------------- Ecken

@dataclass
class CornerModel:
    """log μ_heim = b0 + b1·log(Ecken Heim für) + b2·log(Ecken Gast gegen) + b3·log λ_heim
    (analog Gast); Verteilung: negative Binomialverteilung (Ecken streuen stärker als Poisson)."""
    bh: np.ndarray
    ba: np.ndarray
    disp: float  # r-Parameter der NegBin für die Gesamtzahl

    @staticmethod
    def _X(cf, ca, lam):
        cf = np.log(np.clip(pd.to_numeric(cf, errors="coerce").fillna(5.0).to_numpy(float), 1, None))
        ca = np.log(np.clip(pd.to_numeric(ca, errors="coerce").fillna(5.0).to_numpy(float), 1, None))
        return np.c_[np.ones(len(cf)), cf, ca, np.log(np.asarray(lam, float))]

    @staticmethod
    def _poisson_fit(X, y):
        def f(b):
            eta = X @ b
            mu = np.exp(eta)
            return np.sum(mu - y * eta), X.T @ (mu - y)
        b0 = np.zeros(X.shape[1])
        b0[0] = np.log(max(y.mean(), 0.1))
        return minimize(f, b0, jac=True, method="L-BFGS-B").x

    @classmethod
    def fit(cls, t):
        t = t.dropna(subset=["hco", "aco"])
        Xh = cls._X(t.h_co_f, t.a_co_a, t.lh)
        Xa = cls._X(t.a_co_f, t.h_co_a, t.la)
        bh = cls._poisson_fit(Xh, t.hco.to_numpy(float))
        ba = cls._poisson_fit(Xa, t.aco.to_numpy(float))
        mu = np.exp(Xh @ bh) + np.exp(Xa @ ba)
        y = (t.hco + t.aco).to_numpy(float)

        def nll(log_r):
            r = np.exp(log_r)
            p = r / (r + mu)
            return -np.sum(gammaln(y + r) - gammaln(r) - gammaln(y + 1) + r * np.log(p) + y * np.log(1 - p))

        r = float(np.exp(minimize(lambda v: nll(v[0]), [3.0], method="L-BFGS-B").x[0]))
        return cls(bh, ba, r)

    def expected(self, t):
        mh = np.exp(self._X(t.h_co_f, t.a_co_a, t.lh) @ self.bh)
        ma = np.exp(self._X(t.a_co_f, t.h_co_a, t.la) @ self.ba)
        return mh, ma

    def p_over(self, mu_total, line):
        p = self.disp / (self.disp + mu_total)
        return 1 - nbinom.cdf(np.floor(line), self.disp, p)


# ------------------------------------------------------------- Halbzeiten

@dataclass
class HalfModel:
    """Anteil der Tore nach der Pause: Teamwert, zum Gesamtmittel geschrumpft
    (k = Pseudo-Spiele). λ_1.HZ = λ·(1 − s), λ_2.HZ = λ·s."""
    s_global: float
    k: float

    def share(self, t):
        def team(sh, n):
            sh = pd.to_numeric(sh, errors="coerce").fillna(self.s_global).to_numpy(float)
            n = pd.to_numeric(n, errors="coerce").fillna(0).to_numpy(float)
            return (n * sh + self.k * self.s_global) / (n + self.k)
        return (team(t.h_anteil2hz, t.h_nhz) + team(t.a_anteil2hz, t.a_nhz)) / 2

    @classmethod
    def fit(cls, t):
        t = t.dropna(subset=["hht", "aht"])
        g1 = (t.hht + t.aht).to_numpy(float)
        g = (t.hg + t.ag).to_numpy(float)
        s_global = 1 - g1.sum() / g.sum()
        lam = (t.lh + t.la).to_numpy(float)
        best = None
        for k in (2, 5, 10, 20, 50, 1e9):
            m = cls(s_global, k)
            s = m.share(t)
            ll = poisson.logpmf(g1, lam * (1 - s)).sum() + poisson.logpmf(g - g1, lam * s).sum()
            if best is None or ll > best[0]:
                best = (ll, k)
        return cls(s_global, best[1])


# ------------------------------------------------------------- Gesamtpaket

@dataclass
class Analyzer:
    markets: dict = field(default_factory=dict)
    corners: CornerModel | None = None
    halves: HalfModel | None = None
    report: dict = field(default_factory=dict)

    @classmethod
    def fit(cls, t: pd.DataFrame, use: dict | None = None):
        dc = _dc(t)
        a = cls()
        for m in X_FUNCS:
            a.markets[m] = MarketModel.fit(t, dc, m, (use or {}).get(m))
        a.corners = CornerModel.fit(t)
        a.halves = HalfModel.fit(t)
        return a

    def save(self, path=PARAMS):
        d = dict(markets={m: mm.to_json() for m, mm in self.markets.items()},
                 corners=dict(bh=self.corners.bh.tolist(), ba=self.corners.ba.tolist(),
                              disp=self.corners.disp),
                 halves=dict(s_global=self.halves.s_global, k=self.halves.k), report=self.report)
        path.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path=PARAMS):
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls({m: MarketModel.from_json(v) for m, v in d["markets"].items()},
                   CornerModel(np.array(d["corners"]["bh"]), np.array(d["corners"]["ba"]),
                               d["corners"]["disp"]),
                   HalfModel(d["halves"]["s_global"], d["halves"]["k"]), d.get("report", {}))

    # ---- Vorhersage für ein Spiel
    def predict(self, row: pd.DataFrame) -> dict:
        """row: eine Zeile mit lh, la, rho und allen Merkmalen (wie in build_training)."""
        dc = _dc(row)
        r = row.iloc[0]
        out = {"xg": (float(r.lh), float(r.la))}
        p = self.markets["1X2"].predict(row, dc)[0]
        out["1X2"] = dict(H=p[0], D=p[1], A=p[2])
        out["DC"] = {"1X": p[0] + p[1], "X2": p[1] + p[2], "12": p[0] + p[2]}
        out["OU2.5"] = float(self.markets["OU2.5"].predict(row, dc)[0])
        out["BTTS"] = float(self.markets["BTTS"].predict(row, dc)[0])
        # Ergebnis-Matrix: Torerwartung so skalieren, dass sie zu den kalibrierten Märkten passt
        m = score_matrix(r.lh, r.la, r.rho)
        out["ergebnisse"] = _top_scores(m, 6)
        n = m.shape[0]
        tot = np.add.outer(np.arange(n), np.arange(n))
        out["OU"] = {line: float(m[tot > line].sum()) for line in (0.5, 1.5, 3.5, 4.5)}
        out["OU"][2.5] = out["OU2.5"]
        # Halbzeiten
        s = float(self.halves.share(row)[0])
        l1h, l1a = r.lh * (1 - s), r.la * (1 - s)
        m1 = score_matrix(l1h, l1a, 0.0)
        out["halbzeit"] = dict(
            anteil_2hz=s, tore_1hz=l1h + l1a, tore_2hz=(r.lh + r.la) * s,
            p_tor_1hz=1 - float(np.exp(-(l1h + l1a))),
            p_tor_2hz=1 - float(np.exp(-(r.lh + r.la) * s)),
            p_mehr_2hz=_p_more(l1h + l1a, (r.lh + r.la) * s),
            hz1_1X2=dict(H=float(np.tril(m1, -1).sum()), D=float(np.trace(m1)),
                         A=float(np.triu(m1, 1).sum())))
        # Ecken
        mh, ma = self.corners.expected(row)
        mh, ma = float(mh[0]), float(ma[0])
        out["ecken"] = dict(heim=mh, gast=ma, gesamt=mh + ma,
                            ueber={l: float(self.corners.p_over(mh + ma, l)) for l in (7.5, 8.5, 9.5, 10.5, 11.5)},
                            datenbasis=int(min(r.h_nstat, r.a_nstat)))
        return out


def _top_scores(m, n):
    idx = np.dstack(np.unravel_index(np.argsort(m.ravel())[::-1][:n], m.shape))[0]
    return [(int(i), int(j), float(m[i, j])) for i, j in idx]


def _p_more(l1, l2):
    """P(mehr Tore in der 2. als in der 1. Halbzeit)."""
    g = np.arange(15)
    return float(np.sum(np.outer(poisson.pmf(g, l1), poisson.pmf(g, l2)) * (g[None, :] > g[:, None])))


# ------------------------------------------------------------- Bewertung

def _ll(P, y):
    return float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], 1e-12, None))))


def _bll(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def evaluate(t: pd.DataFrame, split: str = "2025-07-01") -> dict:
    """Training vor `split`, Test danach. Vergleicht Kombi-Modell mit dem reinen
    Torprognose-Modell und prüft jede Kennzahl durch Weglassen (Ablation)."""
    tr, te = t[t.date < split], t[t.date >= split]
    dtr, dte = _dc(tr), _dc(te)
    out = {"spiele_training": len(tr), "spiele_test": len(te)}
    for market in X_FUNCS:
        y = _y(te, market)
        mm = MarketModel.fit(tr, dtr, market)
        P = mm.predict(te, dte)
        if market == "1X2":
            dc_only = dte[["pH", "pD", "pA"]].to_numpy()
            base = np.tile(np.bincount(_y(tr, market), minlength=3) / len(tr), (len(te), 1))
            res = dict(kombi=_ll(P, y), nur_torprognose=_ll(dc_only, y), basisrate=_ll(base, y))
            cl = (te.comp == "UCL").to_numpy()
            if cl.any():
                res["kombi_nur_CL"] = _ll(P[cl], y[cl])
                res["torprognose_nur_CL"] = _ll(dc_only[cl], y[cl])
        else:
            col = "pO25" if market == "OU2.5" else "pBTTS"
            res = dict(kombi=_bll(P, y), nur_torprognose=_bll(dte[col].to_numpy(), y),
                       basisrate=_bll(np.full(len(y), _y(tr, market).mean()), y))
        # Ablation: Verbesserung des Log-Loss durch jede Kennzahl
        abl = {}
        for name in mm.names:
            if name.startswith("Torprognose"):
                continue
            m2 = MarketModel.fit(tr, dtr, market, [n for n in mm.names if n != name])
            P2 = m2.predict(te, dte)
            l2 = _ll(P2, y) if market == "1X2" else _bll(P2, y)
            abl[name] = round(l2 - res["kombi"], 5)  # > 0: Kennzahl hilft
        res["beitrag"] = abl
        res["gewichte"] = mm.weights()
        out[market] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}

    # Ecken
    cm = CornerModel.fit(tr)
    tt = te.dropna(subset=["hco", "aco"])
    mh, ma = cm.expected(tt)
    y = (tt.hco + tt.aco).to_numpy(float)
    base_mu = float((tr.hco + tr.aco).mean())
    po = cm.p_over(mh + ma, 9.5)
    pb = cm.p_over(np.full(len(y), base_mu), 9.5)
    out["Ecken"] = dict(spiele=len(tt), mae_kombi=round(float(np.mean(np.abs(mh + ma - y))), 3),
                        mae_mittelwert=round(float(np.mean(np.abs(base_mu - y))), 3),
                        logloss_ueber95_kombi=round(_bll(po, (y > 9.5).astype(float)), 4),
                        logloss_ueber95_mittelwert=round(_bll(pb, (y > 9.5).astype(float)), 4))
    # Halbzeiten
    hm = HalfModel.fit(tr)
    th = te.dropna(subset=["hht", "aht"])
    g1 = (th.hht + th.aht).to_numpy(float)
    lam = (th.lh + th.la).to_numpy(float)
    s = hm.share(th)
    p1 = 1 - np.exp(-lam * (1 - s))
    p1b = 1 - np.exp(-lam * (1 - hm.s_global))
    out["Halbzeit"] = dict(spiele=len(th), anteil_tore_2hz=round(hm.s_global, 3), schrumpfung_k=hm.k,
                           logloss_tor_1hz_team=round(_bll(p1, (g1 > 0).astype(float)), 4),
                           logloss_tor_1hz_konstant=round(_bll(p1b, (g1 > 0).astype(float)), 4))
    return out
