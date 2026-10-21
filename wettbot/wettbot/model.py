"""Hierarchisches Dixon-Coles-Modell.

Torerwartung:
    log λ_heim = μ + Heimvorteil + (A_liga(h) + a_h) − (D_liga(g) + d_g)
    log λ_gast = μ             + (A_liga(g) + a_g) − (D_liga(h) + d_h)

* Jede Mannschaft hat Angriff a / Abwehr d *relativ zu ihrer Liga*.
* Jede Liga hat einen Stärke-Offset A/D. Der wird über Europapokalspiele
  bestimmt – nur so lassen sich z. B. Premier League und Eredivisie vergleichen.
* Ältere Spiele zählen weniger (exponentielle Gewichtung, Halbwertszeit).
* L2-Regularisierung zieht Teams mit wenig Daten zum Ligamittel.
* Dixon-Coles-ρ korrigiert die Häufigkeit von 0:0, 1:0, 0:1, 1:1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import poisson

MAX_GOALS = 10


@dataclass
class DixonColes:
    half_life_days: float = 240.0
    ridge_team: float = 0.5
    ridge_group: float = 0.05
    # Länder ohne Ligadaten (Norwegen, Ukraine, …) kennt das Modell nur über 1–3 Klubs.
    # Ihr Offset wird stark zu einem gemeinsamen "Kleinligen"-Mittel gezogen, sonst
    # erbt z. B. Viking die Stärke von Bodø/Glimt.
    ridge_minor: float = 8.0
    euro_weight: float = 1.5  # Europapokalspiele verknüpfen die Ligen -> etwas mehr Gewicht

    teams: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    params: dict = field(default_factory=dict)
    fitted_at: pd.Timestamp | None = None

    # ------------------------------------------------------------- Training
    @staticmethod
    def _team_groups(df: pd.DataFrame) -> dict[str, str]:
        """Ligagruppe je Team: letzte nationale Liga, sonst Land aus dem Europapokal."""
        grp: dict[str, str] = {}
        dom = df[~df["home_grp"].str.startswith("X-")]
        for _, r in dom.iterrows():  # chronologisch -> letzte Liga gewinnt
            grp[r.home_key] = r.home_grp
            grp[r.away_key] = r.away_grp
        for _, r in df[df["home_grp"].str.startswith("X-")].iterrows():
            grp.setdefault(r.home_key, r.home_grp)
            grp.setdefault(r.away_key, r.away_grp)
        return grp

    def fit(self, df: pd.DataFrame, as_of=None) -> "DixonColes":
        as_of = pd.Timestamp(as_of) if as_of is not None else df["date"].max() + pd.Timedelta(days=1)
        df = df[df["date"] < as_of]
        age = (as_of - df["date"]).dt.days.to_numpy()
        w = np.exp(-np.log(2) * age / self.half_life_days)
        w = w * np.where(df["home_grp"].str.startswith("X-"), self.euro_weight, 1.0)
        keep = w > 0.02
        df, w = df[keep], w[keep]

        grp = self._team_groups(df)
        self.teams = sorted(set(df.home_key) | set(df.away_key))
        self.groups = sorted(set(grp.values()))
        ti = {t: i for i, t in enumerate(self.teams)}
        gi = {g: i for i, g in enumerate(self.groups)}
        T, G = len(self.teams), len(self.groups)

        h = df["home_key"].map(ti).to_numpy()
        a = df["away_key"].map(ti).to_numpy()
        gh = np.array([gi[grp[self.teams[i]]] for i in h])
        ga = np.array([gi[grp[self.teams[i]]] for i in a])
        nh = 1.0 - df["neutral"].astype(float).to_numpy()
        eu = df["home_grp"].str.startswith("X-").to_numpy(float)  # eigenes Torniveau im Europapokal
        yh = df["hg"].to_numpy(float)
        ya = df["ag"].to_numpy(float)

        # Regularisierung je Gruppe: echte Ligen frei, Kleinländer zum Mittel (MA, MD)
        minor = np.array([g.startswith("X-") for g in self.groups], float)
        rg = np.where(minor > 0, self.ridge_minor, self.ridge_group)

        # Parametervektor: μ, Heim, MA, MD, Euro, a[T], d[T], A[G], D[G]
        o = 5

        def unpack(x):
            return (x[0], x[1], x[2], x[3], x[4], x[o:o + T], x[o + T:o + 2 * T],
                    x[o + 2 * T:o + 2 * T + G], x[o + 2 * T + G:])

        def nll(x):
            mu, home, MA, MD, ec, at, de, A, D = unpack(x)
            lh = mu + ec * eu + home * nh + A[gh] + at[h] - D[ga] - de[a]
            la = mu + ec * eu + A[ga] + at[a] - D[gh] - de[h]
            eh, ea = np.exp(lh), np.exp(la)
            cA, cD = A - MA * minor, D - MD * minor
            f = np.sum(w * (eh - yh * lh)) + np.sum(w * (ea - ya * la))
            f += self.ridge_team * (at @ at + de @ de) + rg @ (cA * cA + cD * cD)
            rh, ra = w * (eh - yh), w * (ea - ya)  # d/dlogλ
            g = np.empty_like(x)
            g[0] = rh.sum() + ra.sum()
            g[4] = ((rh + ra) * eu).sum()
            g[1] = (rh * nh).sum()
            g[2] = -2 * np.sum(rg * cA * minor)
            g[3] = -2 * np.sum(rg * cD * minor)
            g[o:o + T] = np.bincount(h, rh, T) + np.bincount(a, ra, T) + 2 * self.ridge_team * at
            g[o + T:o + 2 * T] = -np.bincount(a, rh, T) - np.bincount(h, ra, T) + 2 * self.ridge_team * de
            g[o + 2 * T:o + 2 * T + G] = np.bincount(gh, rh, G) + np.bincount(ga, ra, G) + 2 * rg * cA
            g[o + 2 * T + G:] = -np.bincount(ga, rh, G) - np.bincount(gh, ra, G) + 2 * rg * cD
            return f, g

        x0 = np.zeros(o + 2 * T + 2 * G)
        x0[0], x0[1] = np.log(1.3), 0.2
        res = minimize(nll, x0, jac=True, method="L-BFGS-B", options={"maxiter": 5000})
        mu, home, _, _, ec, at, de, A, D = unpack(res.x)

        # Dixon-Coles ρ auf den gefitteten λ schätzen
        lh = np.exp(mu + ec * eu + home * nh + A[gh] + at[h] - D[ga] - de[a])
        la = np.exp(mu + ec * eu + A[ga] + at[a] - D[gh] - de[h])

        def rho_nll(r):
            t = _tau(yh, ya, lh, la, r)
            return -np.sum(w * np.log(np.clip(t, 1e-10, None)))

        rho = minimize_scalar(rho_nll, bounds=(-0.2, 0.2), method="bounded").x

        self.params = dict(mu=mu, home=home, rho=rho, euro=ec,
                           att={t: at[i] for t, i in ti.items()},
                           dfn={t: de[i] for t, i in ti.items()},
                           A={g: A[i] for g, i in gi.items()},
                           D={g: D[i] for g, i in gi.items()},
                           grp=grp)
        self.fitted_at = as_of
        return self

    # ------------------------------------------------------------ Vorhersage
    def strength(self, team_key: str) -> tuple[float, float]:
        p = self.params
        g = p["grp"][team_key]
        return p["A"][g] + p["att"][team_key], p["D"][g] + p["dfn"][team_key]

    def expected_goals(self, home_key: str, away_key: str, neutral: bool = False,
                       euro: bool = True):
        """Torerwartung; euro=True nutzt das Europapokal-Torniveau (Standard: CL)."""
        p = self.params
        ah, dh = self.strength(home_key)
        aa, da = self.strength(away_key)
        base = p["mu"] + (p["euro"] if euro else 0.0)
        lh = np.exp(base + (0 if neutral else p["home"]) + ah - da)
        la = np.exp(base + aa - dh)
        return float(lh), float(la)

    def score_matrix(self, home_key: str, away_key: str, neutral: bool = False,
                     euro: bool = True) -> np.ndarray:
        lh, la = self.expected_goals(home_key, away_key, neutral, euro)
        return score_matrix(lh, la, self.params["rho"])

    def ranking(self) -> pd.DataFrame:
        rows = []
        for t in self.teams:
            a, d = self.strength(t)
            rows.append((t, self.params["grp"][t], a, d, a + d))
        return (pd.DataFrame(rows, columns=["team", "liga", "angriff", "abwehr", "rating"])
                .sort_values("rating", ascending=False).reset_index(drop=True))


def _tau(x, y, lh, la, rho):
    x, y = np.asarray(x), np.asarray(y)
    t = np.ones(np.broadcast(x, y, lh, la).shape)
    t = np.where((x == 0) & (y == 0), 1 - lh * la * rho, t)
    t = np.where((x == 0) & (y == 1), 1 + lh * rho, t)
    t = np.where((x == 1) & (y == 0), 1 + la * rho, t)
    t = np.where((x == 1) & (y == 1), 1 - rho, t)
    return t


def score_matrix(lh: float, la: float, rho: float = 0.0) -> np.ndarray:
    g = np.arange(MAX_GOALS + 1)
    m = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
    m[:2, :2] *= _tau(*np.meshgrid(g[:2], g[:2], indexing="ij"), lh, la, rho)
    return m / m.sum()
