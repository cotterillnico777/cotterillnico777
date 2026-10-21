import numpy as np
import pandas as pd
import pytest

from wettbot.data import parse_football_txt
from wettbot.ledger import outcome
from wettbot.markets import devig, market_probs
from wettbot.model import DixonColes, score_matrix
from wettbot.names import Resolver, key
from wettbot.value import Settings, find_value, kelly, market_fair, select_bets


@pytest.mark.parametrize("a,b", [
    ("FC Bayern München", "Bayern Munich"),
    ("FC Internazionale Milano (ITA)", "Inter"),
    ("Sporting Clube de Portugal", "Sporting CP"),
    ("Real Betis Balompié", "Real Betis"),
    ("Racing Club de Lens", "Lens"),
    ("FK Bodø/Glimt (NOR)", "Bodo/Glimt"),
    ("Club Atlético de Madrid", "Atletico Madrid"),
    ("SL Benfica (POR)", "Sport Lisboa e Benfica"),
    ("Feyenoord Rotterdam", "Feyenoord"),
    ("Paris Saint-Germain FC", "PSG"),
])
def test_name_keys_match(a, b):
    assert key(a) == key(b)


def test_resolver_fuzzy():
    r = Resolver(["Manchester United FC", "Manchester City FC", "Aston Villa FC"])
    assert r.resolve("Man Utd") == "Manchester United FC"
    assert r.resolve("Aston Vila") == "Aston Villa FC"
    assert r.resolve("Real Madrid") is None


def test_devig_sums_to_one_and_removes_margin():
    p = devig([1.90, 3.60, 4.20])
    assert p.sum() == pytest.approx(1.0)
    assert np.all(p < 1 / np.array([1.90, 3.60, 4.20]))
    # Power-Methode nimmt dem Außenseiter mehr Marge weg als dem Favoriten
    prop = devig([1.90, 3.60, 4.20], "proportional")
    assert p[0] > prop[0] and p[2] < prop[2]


def test_market_probs_consistent():
    mp = market_probs(score_matrix(1.6, 1.1, -0.05))
    assert sum(mp["1X2"].values()) == pytest.approx(1.0)
    assert mp["OU2.5"]["O"] + mp["OU2.5"]["U"] == pytest.approx(1.0)
    assert mp["OU1.5"]["O"] > mp["OU2.5"]["O"] > mp["OU3.5"]["O"]
    assert mp["1X2"]["H"] > mp["1X2"]["A"]


def test_kelly():
    assert kelly(0.5, 2.0) == 0.0
    assert kelly(0.55, 2.0) == pytest.approx(0.10)
    assert kelly(0.3, 2.0) == 0.0


@pytest.mark.parametrize("m,s,hg,ag,exp", [
    ("1X2", "H", 2, 1, True), ("1X2", "D", 1, 1, True), ("1X2", "A", 2, 1, False),
    ("OU2.5", "O", 2, 1, True), ("OU2.5", "U", 2, 1, False), ("OU3.5", "U", 2, 1, True),
    ("BTTS", "Y", 1, 0, False), ("BTTS", "N", 0, 0, True),
])
def test_outcome(m, s, hg, ag, exp):
    assert outcome(m, s, hg, ag) is exp


def test_parse_football_txt_uses_90_minute_score():
    txt = """
▪ Finals, Semifinals
  Tue Apr 29 2025
    21:00  Arsenal FC (ENG)        v Paris Saint-Germain FC (FRA)  0-1 (0-1)
           Juventus FC (ITA)       v Galatasaray SK (TUR)     3-2 a.e.t. (3-0, 1-0)
▪ Finals, Final
  Sat May 31
    18:00  Paris Saint-Germain FC (FRA) v Arsenal FC (ENG)         4-3 pen. 1-1 a.e.t. (1-1, 0-1)
"""
    rows = parse_football_txt(txt, "2024-25", "UCL")
    assert rows[0][:5] == ("2025-04-29", "Arsenal FC (ENG)", "Paris Saint-Germain FC (FRA)", 0, 1)
    assert rows[1][3:5] == (3, 0)
    assert rows[2][0] == "2025-05-31" and rows[2][3:5] == (1, 1)
    assert rows[2][6] is True and rows[0][6] is False  # Finale = neutral
    assert rows[0][7] == "X-ENG"


def _synthetic(seed=0, n_rounds=12):
    """Zwei Ligen + Europapokal mit bekannten Stärken."""
    rng = np.random.default_rng(seed)
    strength = {"A1": 0.5, "A2": 0.2, "A3": 0.0, "A4": -0.2, "B1": 0.1, "B2": -0.2, "B3": -0.4, "B4": -0.6}
    rows, d = [], pd.Timestamp("2026-01-01")
    for r in range(n_rounds):
        for lg in "AB":
            teams = [t for t in strength if t[0] == lg]
            for h in teams:
                for a in teams:
                    if h != a:
                        lh = np.exp(0.2 + 0.25 + strength[h] - strength[a] / 2)
                        la = np.exp(0.2 + strength[a] - strength[h] / 2)
                        rows.append((d, h, a, rng.poisson(lh), rng.poisson(la), lg, False, lg, lg))
        for h, a in [("A1", "B1"), ("B2", "A2"), ("A3", "B3"), ("B4", "A4")]:
            lh = np.exp(0.2 + 0.25 + strength[h] - strength[a] / 2)
            la = np.exp(0.2 + strength[a] - strength[h] / 2)
            rows.append((d, h, a, rng.poisson(lh), rng.poisson(la), "UCL", False,
                         f"X-{h[0]}", f"X-{a[0]}"))
        d += pd.Timedelta(days=7)
    df = pd.DataFrame(rows, columns=["date", "home", "away", "hg", "ag", "comp", "neutral",
                                     "home_grp", "away_grp"])
    df["home_key"], df["away_key"] = df["home"].map(key), df["away"].map(key)
    return df


def test_model_recovers_ordering_and_league_gap():
    m = DixonColes(half_life_days=1000).fit(_synthetic())
    r = m.ranking().set_index("team")["rating"]
    assert r["a1"] > r["a2"] > r["a3"] > r["a4"]
    assert r["b1"] > r["b4"]
    # Liga A ist im Schnitt stärker – muss über die Europapokalspiele erkannt werden
    assert r[["a1", "a2", "a3", "a4"]].mean() > r[["b1", "b2", "b3", "b4"]].mean()
    assert 0.0 < m.params["home"] < 0.6


def _odds(rows):
    return pd.DataFrame(rows, columns=["date", "kickoff", "home", "away", "market", "selection",
                                       "odds", "bookmaker"])


def test_market_fair_prefers_complete_books():
    o = _odds([("d", "k", "X", "Y", "1X2", s, q, "b1") for s, q in zip("HDA", (2.0, 3.5, 4.0))]
              + [("d", "k", "X", "Y", "1X2", "H", 2.3, "b2")])
    fair, src = market_fair(o, "1X2")
    assert src == "1 Buchm."
    assert fair["H"] + fair["D"] + fair["A"] == pytest.approx(1.0)
    fair, src = market_fair(o[o.selection != "D"], "1X2")
    assert fair is None


def test_select_bets_limits_and_one_per_market():
    m = DixonColes(half_life_days=1000).fit(_synthetic())
    # Großzügige Quoten auf alles -> viele Kandidaten
    rows = []
    for h, a in [("A1", "B4"), ("A2", "B3"), ("B1", "A4")]:
        mp = market_probs(m.score_matrix(key(h), key(a)))["1X2"]
        for s in "HDA":
            rows.append(("2026-05-01", "21:00", h, a, "1X2", s, round(0.97 / mp[s], 2), "fair"))
            rows.append(("2026-05-01", "21:00", h, a, "1X2", s, round(1.12 / mp[s], 2), "soft"))
    cfg = Settings(bankroll=1000, max_disagreement=1.0, max_odds=50)
    cands = find_value(m, _odds(rows), ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4"], cfg)
    bets = select_bets(cands, cfg)
    assert len(bets) >= 2
    assert not bets.duplicated(["spiel", "markt"]).any()  # max. eine Wette pro Spiel/Markt
    assert (bets["einsatz"] <= 1000 * cfg.max_stake_pct + 1e-9).all()
    assert bets["einsatz"].sum() <= 1000 * cfg.max_day_pct + 1e-9
    assert (bets["ev"] >= cfg.min_edge).all()


def test_roi_rules_filter_outlier_prices_and_veto():
    from wettbot.roi import apply_rules, summary
    base = dict(date=pd.Timestamp("2025-01-01"), liga="ENG1", heim="X", gast="Y", markt="1X2",
                marge=0.05, abweichung=0.05, gewonnen=True)
    c = pd.DataFrame([
        base | dict(tipp="H", quote=2.20, ref_quote=2.05, p_modell=0.50, p_markt=0.48),  # +5,6 % EV
        base | dict(gast="Z", tipp="H", quote=2.60, ref_quote=2.05, p_modell=0.50, p_markt=0.48),  # Ausreißer
        base | dict(gast="W", tipp="H", quote=2.20, ref_quote=2.05, p_modell=0.40, p_markt=0.48),  # Modell-Veto
    ])
    b = apply_rules(c, Settings())
    assert list(b["gast"]) == ["Y"]
    assert summary(b)["roi_flat"] == pytest.approx(1.2)


def test_softmax_learns_signal_and_ignores_noise():
    from wettbot.analyse import _fit_softmax, _predict_softmax
    rng = np.random.default_rng(1)
    X = rng.normal(size=(4000, 2))           # Spalte 0 = Signal, Spalte 1 = Rauschen
    logits = np.c_[1.5 * X[:, 0], np.zeros(4000), -1.5 * X[:, 0]]
    p = np.exp(logits) / np.exp(logits).sum(1, keepdims=True)
    y = np.array([rng.choice(3, p=pi) for pi in p])
    W = _fit_softmax(X, y, 3)
    assert abs(W[1, 0]) > 5 * abs(W[2, 0])   # Signal-Gewicht >> Rausch-Gewicht
    P = _predict_softmax(W, X)
    assert np.allclose(P.sum(1), 1)


def test_profiles_never_use_match_day_or_later():
    from wettbot.stats import Profiles, _split, team_log_results
    df = pd.DataFrame(dict(date=pd.to_datetime(["2026-01-01", "2026-01-08", "2026-01-15"]),
                           home_key=["a", "a", "a"], away_key=["b", "c", "d"], hg=[1, 2, 5],
                           ag=[0, 2, 0], hht=[0, 1, 2], aht=[0, 0, 0], comp="X"))
    P = Profiles(_split(team_log_results(df)), {}, {}, {})
    f = P.form("a", "2026-01-15")
    assert f["serie"] == "SU"                 # Spiel vom 15.01. selbst zählt nicht
    g = P.goals("a", "2026-01-15")
    assert g["gf"] == pytest.approx(1.5)
    assert g["anteil_2hz"] == pytest.approx((5 - 1) / 5)  # 5 Tore, 1 davon vor der Pause


def test_half_model_shrinks_to_global_share():
    from wettbot.analyse import HalfModel
    hm = HalfModel(s_global=0.55, k=10)
    t = pd.DataFrame(dict(h_anteil2hz=[1.0, np.nan], h_nhz=[10, 0], a_anteil2hz=[0.55, 0.55], a_nhz=[10, 10]))
    s = hm.share(t)
    assert 0.55 < s[0] < 1.0
    assert s[1] == pytest.approx(0.55)


def test_corner_model_recovers_team_effect():
    from wettbot.analyse import CornerModel
    rng = np.random.default_rng(2)
    n = 3000
    cf_h, ca_a = rng.uniform(3, 8, n), rng.uniform(3, 8, n)
    mu_h = 0.6 * cf_h + 0.4 * ca_a
    t = pd.DataFrame(dict(h_co_f=cf_h, a_co_a=ca_a, a_co_f=rng.uniform(3, 8, n),
                          h_co_a=rng.uniform(3, 8, n), lh=1.4, la=1.1))
    t["hco"] = rng.poisson(mu_h)
    t["aco"] = rng.poisson(0.5 * t.a_co_f + 0.5 * t.h_co_a)
    cm = CornerModel.fit(t)
    mh, ma = cm.expected(t)
    assert np.corrcoef(mh, mu_h)[0, 1] > 0.95
    assert 0 < cm.p_over(10.0, 9.5) < 1
