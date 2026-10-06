"""Ausführliche Datenprüfung vor der Forschung (python -m quantbot data audit).

Ändert keine Daten. Listet jede auffällige Kerze mit Ursache und vergibt je Symbol und
Zeitrahmen PASS / WARN / FAIL:

  FAIL  echte Integritätsverletzung: doppelte/unsortierte Zeitstempel, OHLC inkonsistent,
        Preis <= 0, fehlende Werte, negatives Volumen, Volumen 0 trotz Preisbewegung,
        Kerze beim Speichern noch nicht abgeschlossen, Widerspruch zwischen Zeitrahmen
  WARN  verwendbar, aber zu beachten: Lücken, Kerzen ohne Handel, nicht bestätigte Ausreißer,
        Auffälligkeiten in der Funding-Historie
  PASS  keine Befunde (bestätigte echte Extrembewegungen sind nur Information)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.timeframes import tf_delta, tf_seconds
from .resample import resample_ohlcv
from .store import DataStore
from .validate import outlier_mask, validate_ohlcv

PRICE_TOL = 1e-9  # relative Toleranz beim Zeitrahmen-Abgleich
VOLUME_TOL = 1e-3


@dataclass
class SeriesAudit:
    symbol: str
    timeframe: str
    grade: str = "PASS"
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    summary: str = ""
    last_candle: str = ""
    last_candle_close: str = ""
    stored_at: str = ""
    outliers: pd.DataFrame = field(default_factory=pd.DataFrame)
    zero_volume: pd.DataFrame = field(default_factory=pd.DataFrame)
    ohlc_bad: pd.DataFrame = field(default_factory=pd.DataFrame)
    gaps: pd.DataFrame = field(default_factory=pd.DataFrame)
    duplicates: list[str] = field(default_factory=list)
    crosstf: pd.DataFrame = field(default_factory=pd.DataFrame)

    def fail(self, why: str) -> None:
        self.grade = "FAIL"
        self.reasons.append(why)

    def warn(self, why: str) -> None:
        if self.grade == "PASS":
            self.grade = "WARN"
        self.reasons.append(why)


def ohlc_violations(df: pd.DataFrame) -> pd.DataFrame:
    checks = {
        "high<low": df["high"] < df["low"],
        "open>high": df["open"] > df["high"] + 1e-12,
        "open<low": df["open"] < df["low"] - 1e-12,
        "close>high": df["close"] > df["high"] + 1e-12,
        "close<low": df["close"] < df["low"] - 1e-12,
        "preis<=0": (df[["open", "high", "low", "close"]] <= 0).any(axis=1),
        "nan": df[["open", "high", "low", "close", "volume"]].isna().any(axis=1),
        "volumen<0": df["volume"] < 0,
    }
    bad = pd.DataFrame(checks)
    rows = df[bad.any(axis=1)].copy()
    rows["problem"] = bad[bad.any(axis=1)].apply(lambda r: ",".join(k for k, v in r.items() if v), axis=1)
    return rows


def crosstf_mismatch(low: pd.DataFrame, low_tf: str, high: pd.DataFrame, high_tf: str) -> tuple[pd.DataFrame, int]:
    """Höheren Zeitrahmen aus dem niedrigeren nachbauen und mit dem geladenen vergleichen.
    Beide Reihen kommen aus getrennten Downloads -> unabhängige Bestätigung."""
    rebuilt = resample_ohlcv(low[~low.index.duplicated()].sort_index(), low_tf, high_tf)
    common = rebuilt.index.intersection(high.index)
    if not len(common):
        return pd.DataFrame(), 0
    a, b = rebuilt.loc[common], high.loc[common]
    price_bad = pd.Series(False, index=common)
    for c in ("open", "high", "low", "close"):
        price_bad |= ((a[c] - b[c]).abs() / b[c].abs().clip(lower=1e-12)) > PRICE_TOL
    vol_bad = ((a["volume"] - b["volume"]).abs() / b["volume"].abs().clip(lower=1e-9)) > VOLUME_TOL
    bad = price_bad | vol_bad
    out = pd.concat([b[bad].add_prefix(f"{high_tf}_"), a[bad].add_prefix(f"aus_{low_tf}_")], axis=1)
    out["nur_volumen"] = (~price_bad & vol_bad)[bad]
    dev = pd.concat([((a[c] - b[c]).abs() / b[c].abs().clip(lower=1e-12)) for c in ("open", "high", "low", "close")],
                    axis=1).max(axis=1)
    out["max_preisabweichung_pct"] = (dev[bad] * 100).astype(float)
    out["volumenabweichung_pct"] = (((a["volume"] - b["volume"]) / b["volume"].abs().clip(lower=1e-9)) * 100)[bad]
    return out, len(common)


def classify_mismatches(mm: pd.DataFrame, tf: str, base: pd.DataFrame, base_tf: str,
                        stored_base: pd.Timestamp | None, stored_tf: pd.Timestamp | None,
                        other_symbols_ts: set | None = None) -> pd.Series:
    """Ursache je abweichender Kerze (nur Diagnose, die Daten bleiben unverändert).

    wartung   : im Zeitraum der Kerze (± 1 Basis-Kerze) gibt es Basis-Kerzen ohne Handel ->
                die Börse hat die Zeitrahmen um einen Ausfall herum unterschiedlich gebildet
    datenende : Kerze liegt am Ende der Daten; vermutlich direkt nach Kerzenschluss geladen, bevor
                die Börse sie final hatte -> erneuter Download (überlappt 2 Tage) ersetzt sie
    börsenweit: dieselbe Kerze weicht auch bei mindestens einem anderen Symbol ab -> Ereignis auf
                Seiten der Börse (z. B. Störung mit nachträglich unterschiedlich gebildeten Kerzen),
                kein Fehler einer einzelnen Datei
    ungeklärt : keine dieser Ursachen -> echte Integritätsverletzung
    """
    step, bstep = tf_delta(tf), tf_delta(base_tf)
    idle = base.index[(base["volume"] == 0) & ((base["high"] - base["low"]).abs() <= 1e-12)]
    stamps = [t for t in (stored_base, stored_tf) if t is not None]
    end = min(stamps) if stamps else None
    out = {}
    for ts in mm.index:
        if len(idle) and ((idle >= ts - bstep) & (idle < ts + step + bstep)).any():
            out[ts] = "wartung"
        elif end is not None and ts + step > end - 2 * step:
            out[ts] = "datenende"
        elif other_symbols_ts and ts in other_symbols_ts:
            out[ts] = "börsenweit"
        else:
            out[ts] = "ungeklärt"
    return pd.Series(out, dtype=object)


def classify_outliers(df: pd.DataFrame, others: dict[str, pd.DataFrame], confirmed_ts: set | None) -> tuple[pd.DataFrame, float]:
    mask, r, thr = outlier_mask(df["close"])
    if not mask.any():
        return pd.DataFrame(), thr
    prev_close = df["close"].shift(1)
    next_r = r.shift(-1)
    med_vol = df["volume"].median()
    other_r = {sym: np.log(o["close"]).diff() for sym, o in others.items()}
    rows = []
    for ts in mask[mask].index:
        row = df.loc[ts]
        gap = float(np.log(row["open"] / prev_close[ts]))
        rev = float(-next_r.get(ts, np.nan) / r[ts]) if r[ts] else np.nan
        same_time = []
        for sym, ro in other_r.items():
            if ts in ro.index and np.sign(ro[ts]) == np.sign(r[ts]) and abs(ro[ts]) > abs(r[ts]) * 0.3:
                same_time.append(sym)
        suspicious = []
        if abs(gap) > thr / 2:
            suspicious.append("Kurssprung zwischen Kerzen (Open weit vom vorigen Close)")
        if rev == rev and rev >= 0.8 and row["volume"] < med_vol:
            suspicious.append("sofortige Umkehr bei unterdurchschnittlichem Volumen")
        if confirmed_ts is not None and ts not in confirmed_ts:
            suspicious.append("nicht durch anderen Zeitrahmen bestätigt")
        rows.append({
            "timestamp": ts, "log_rendite": float(r[ts]), "rendite_pct": float(np.expm1(r[ts]) * 100),
            "schwelle_log": thr, "prev_close": float(prev_close[ts]), "open": row["open"], "high": row["high"],
            "low": row["low"], "close": row["close"], "volume": row["volume"],
            "volumen_vs_median": float(row["volume"] / med_vol) if med_vol else np.nan,
            "open_gap_log": gap, "umkehr_naechste_kerze": rev,
            "gleichzeitig_bei": ",".join(same_time),
            "bewertung": "verdächtig: " + "; ".join(suspicious) if suspicious else "echt (konsistent)",
        })
    return pd.DataFrame(rows).set_index("timestamp"), thr


def zero_volume_rows(df: pd.DataFrame, others: dict[str, pd.DataFrame]) -> pd.DataFrame:
    z = df[df["volume"] == 0]
    if z.empty:
        return pd.DataFrame()
    prev_close = df["close"].shift(1)
    out = z.copy()
    out["prev_close"] = prev_close.loc[z.index]
    out["flach"] = (z["high"] - z["low"]).abs() <= 1e-12
    out["preis_wie_vorher"] = (z["close"] - out["prev_close"]).abs() <= 1e-12
    out["auch_ohne_volumen_bei"] = [
        ",".join(s for s, o in others.items() if ts in o.index and o.loc[ts, "volume"] == 0) for ts in z.index
    ]
    out["ursache"] = np.where(
        ~out["flach"], "INKONSISTENT: Preisbewegung ohne Volumen",
        np.where(out["auch_ohne_volumen_bei"] != "",
                 "kein Handel, gleichzeitig bei anderen Symbolen -> Börsenwartung/-ausfall wahrscheinlich",
                 "kein Handel (nur dieses Symbol) -> Handelspause/geringe Liquidität"))
    return out


def audit_funding(f: pd.DataFrame | None, stored_at: str | None) -> tuple[str, list[str], dict]:
    if f is None or f.empty:
        return "WARN", ["keine Funding-Historie (Backtest nutzt konservative Ersatzrate)"], {}
    reasons, grade = [], "PASS"
    idx = f.index
    info = {"eintraege": len(f), "von": str(idx.min()), "bis": str(idx.max())}
    dup = int(idx.duplicated().sum())
    if dup:
        grade, reasons = "FAIL", reasons + [f"{dup} doppelte Funding-Zeitstempel"]
    if not idx.is_monotonic_increasing:
        grade, reasons = "FAIL", reasons + ["Funding-Zeitstempel nicht aufsteigend"]
    if f["rate"].isna().any():
        grade, reasons = "FAIL", reasons + [f"{int(f['rate'].isna().sum())} Funding-Raten fehlen"]
    offset_ms = (idx - idx.floor("h")).total_seconds() * 1000
    info["nicht_zur_vollen_stunde"] = int((offset_ms > 0).sum())
    info["max_versatz_ms"] = float(offset_ms.max()) if len(idx) else 0.0
    if info["max_versatz_ms"] > 60_000:
        grade = "WARN" if grade == "PASS" else grade
        reasons.append(f"Funding-Zeitpunkte bis {info['max_versatz_ms'] / 1000:.0f}s nach der vollen Stunde")
    hours = pd.Series(idx.floor("h")).diff().dt.total_seconds().div(3600).dropna()
    info["intervalle_h"] = {str(k): int(v) for k, v in hours.round(2).value_counts().sort_index().items()}
    irregular = hours[~hours.isin([1.0, 2.0, 4.0, 8.0])]
    if len(irregular):
        grade = "WARN" if grade == "PASS" else grade
        reasons.append(f"{len(irregular)} Funding-Abstände außerhalb 1/2/4/8 h (Lücken), größter {irregular.max():.0f} h")
    extreme = f["rate"].abs() > 0.003
    info["extreme_raten_ueber_0.3pct"] = int(extreme.sum())
    info["max_abs_rate"] = float(f["rate"].abs().max())
    if stored_at:
        future = idx > pd.Timestamp(stored_at)
        if future.any():
            grade, reasons = "FAIL", reasons + [f"{int(future.sum())} Funding-Einträge nach dem Speicherzeitpunkt"]
    return grade, reasons, info


def audit_all(store: DataStore, exchange: str, symbols: list[str], timeframes: list[str],
              now: pd.Timestamp | None = None) -> dict:
    now = now or pd.Timestamp.now(tz="UTC")
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    for tf in timeframes:
        for s in symbols:
            try:
                frames[(s, tf)] = store.load("ohlcv", exchange, s, tf)
            except FileNotFoundError:
                pass
    base_tf = min(timeframes, key=tf_seconds)
    crosstf = {}
    for tf in timeframes:
        for s in symbols:
            if tf != base_tf and (s, tf) in frames and (s, base_tf) in frames:
                crosstf[(s, tf)] = crosstf_mismatch(frames[(s, base_tf)], base_tf, frames[(s, tf)], tf)
    incidents: list[dict] = []
    results: list[SeriesAudit] = []
    for tf in timeframes:
        for s in symbols:
            a = SeriesAudit(s, tf)
            results.append(a)
            if (s, tf) not in frames:
                a.fail("keine Daten vorhanden")
                continue
            df = frames[(s, tf)]
            info = store.info("ohlcv", exchange, s, tf)
            a.stored_at = info.get("updated_at", "")
            stored = pd.Timestamp(a.stored_at) if a.stored_at else now
            rep = validate_ohlcv(df, tf, now=stored)
            a.summary = rep.summary()
            for e in rep.errors:
                a.fail(e)
            # laufende Kerze: war die letzte Kerze beim Speichern abgeschlossen?
            last = df.index.max()
            a.last_candle, a.last_candle_close = str(last), str(last + tf_delta(tf))
            a.notes.append(f"letzte Kerze {last} endet {last + tf_delta(tf)}, gespeichert {a.stored_at or 'unbekannt'}"
                           f" -> {'abgeschlossen' if last + tf_delta(tf) <= stored else 'NICHT abgeschlossen'}")
            a.duplicates = [str(t) for t in df.index[df.index.duplicated()]]
            a.ohlc_bad = ohlc_violations(df)
            if rep.gaps:
                a.gaps = pd.DataFrame(rep.gaps, columns=["von", "bis", "fehlende_kerzen"])
                a.warn(f"{rep.missing_bars} fehlende Kerzen in {len(rep.gaps)} Lücken")
            others = {o: frames[(o, tf)] for o in symbols if o != s and (o, tf) in frames}
            a.zero_volume = zero_volume_rows(df, others)
            if len(a.zero_volume):
                n_flat = int(a.zero_volume["flach"].sum())
                if n_flat:
                    a.warn(f"{n_flat} Kerzen ohne Handel (Volumen 0, O=H=L=C); Backtest führt dort nichts aus")
            # Zeitrahmen-Abgleich: gegen den kleinsten vorhandenen Zeitrahmen
            confirmed = None
            if tf != base_tf and (s, base_tf) in frames:
                mm, n_common = crosstf[(s, tf)]
                if len(mm):
                    b_at = store.info("ohlcv", exchange, s, base_tf).get("updated_at")
                    other_ts = set().union(*[set(crosstf[(o, tf)][0].index) for o in symbols
                                             if o != s and (o, tf) in crosstf] or [set()])
                    mm["ursache"] = classify_mismatches(mm, tf, frames[(s, base_tf)], base_tf,
                                                        pd.Timestamp(b_at) if b_at else None,
                                                        pd.Timestamp(a.stored_at) if a.stored_at else None,
                                                        other_ts)
                    for ts, r in mm[~mm["nur_volumen"] & mm["ursache"].isin(["wartung", "börsenweit"])].iterrows():
                        incidents.append({"start": str(ts), "end": str(ts + tf_delta(tf)), "timeframe": tf,
                                          "symbol": s, "cause": r["ursache"],
                                          "max_price_dev_pct": float(r["max_preisabweichung_pct"])})
                a.crosstf = mm
                if len(mm):
                    price = mm[~mm["nur_volumen"]]
                    for cause, group in price.groupby("ursache"):
                        what = f"{len(group)} von {n_common} Kerzen widersprechen im Preis dem aus {base_tf} nachgebauten Wert"
                        if cause == "wartung":
                            a.warn(f"{what} – alle im Umfeld von Kerzen ohne Handel (Börsenwartung)")
                        elif cause == "börsenweit":
                            a.warn(f"{what} – gleichzeitig bei anderen Symbolen (Ereignis der Börse); "
                                   "Backtest handelt in diesem Zeitfenster nicht")
                        elif cause == "datenende":
                            a.fail(f"{what} – am Datenende, vermutlich vor der Finalisierung geladen; "
                                   "erneut 'data download' ausführen")
                        else:
                            a.fail(f"{what} – Ursache ungeklärt (Integritätsverletzung)")
                    if len(mm) - len(price):
                        vol = mm[mm["nur_volumen"]]
                        causes = ", ".join(f"{c}: {n}" for c, n in vol["ursache"].value_counts().items())
                        a.warn(f"{len(vol)} Kerzen mit Volumenabweichung > {VOLUME_TOL:.1%} zu {base_tf} ({causes})")
                a.notes.append(f"Abgleich mit {base_tf}: {n_common} Kerzen verglichen, {len(mm)} Abweichungen")
                confirmed = set(df.index.difference(mm.index)) & set(
                    resample_ohlcv(frames[(s, base_tf)][~frames[(s, base_tf)].index.duplicated()].sort_index(),
                                   base_tf, tf).index)
            elif tf == base_tf:
                # Basis-Zeitrahmen: Kerze bestätigt, wenn die sie enthaltende Kerze des nächsthöheren
                # Zeitrahmens exakt aus den Basis-Kerzen nachgebaut werden kann
                higher = [t for t in timeframes if tf_seconds(t) > tf_seconds(tf) and (s, t) in frames]
                if higher:
                    h = min(higher, key=tf_seconds)
                    mm, _ = crosstf_mismatch(df, tf, frames[(s, h)], h)
                    ok_parents = frames[(s, h)].index.difference(mm.index)
                    parent = df.index.floor(pd.Timedelta(seconds=tf_seconds(h))) if h[-1] in "mh" else df.index.floor("D")
                    confirmed = set(df.index[parent.isin(ok_parents)])
            a.outliers, thr = classify_outliers(df, others, confirmed)
            if len(a.outliers):
                sus = a.outliers[a.outliers["bewertung"].str.startswith("verdächtig")]
                a.notes.append(f"{len(a.outliers)} extreme Bewegungen (|Log-Rendite| > {thr:.4f} = "
                               f"{np.expm1(thr) * 100:.2f} %), davon {len(sus)} verdächtig")
                if len(sus):
                    a.warn(f"{len(sus)} nicht bestätigte extreme Bewegungen")
    funding = {}
    for s in symbols:
        try:
            f = store.load("funding", exchange, s)
            stored = store.info("funding", exchange, s).get("updated_at")
        except FileNotFoundError:
            f, stored = None, None
        funding[s] = audit_funding(f, stored)
    return {"series": results, "funding": funding, "now": str(now), "incidents": incidents}


INCIDENTS_FILE = "incidents.json"


def save_incidents(store: DataStore, incidents: list[dict]) -> Path:
    """Zeitfenster, in denen die Börse widersprüchliche Kerzen liefert. Nur Metadaten: die
    Kursdateien bleiben unverändert; der Backtest führt in diesen Fenstern nichts aus."""
    import json

    path = store.root / INCIDENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(incidents, key=lambda x: x["start"]), indent=2), encoding="utf-8")
    return path


def load_incident_windows(root: str | Path) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    import json

    path = Path(root) / INCIDENTS_FILE
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return sorted({(pd.Timestamp(x["start"]), pd.Timestamp(x["end"])) for x in rows})


def write_audit(result: dict, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    series: list[SeriesAudit] = result["series"]
    tfs = list(dict.fromkeys(a.timeframe for a in series))
    syms = list(dict.fromkeys(a.symbol for a in series))
    grid = {(a.symbol, a.timeframe): a.grade for a in series}
    lines = ["# Datenprüfung", "", f"Erstellt {result['now']}. Es wurden keine Daten verändert.", "",
             "| Symbol | " + " | ".join(tfs) + " | Funding |", "|---" * (len(tfs) + 2) + "|"]
    for s in syms:
        lines.append(f"| {s} | " + " | ".join(grid.get((s, t), "-") for t in tfs) + f" | {result['funding'][s][0]} |")
    lines += ["", "FAIL = Integritätsverletzung (Research gesperrt), WARN = verwendbar mit Hinweis, PASS = ohne Befund.", ""]
    lines += ["## Funding und Lookahead", "",
              "Regeln im Code: Eine Funding-Rate mit Zeitstempel T wird erst ab der Kerze, die bei oder nach T "
              "beginnt, sichtbar; die Entscheidung fällt am Schluss dieser Kerze, ausgeführt wird zum nächsten Open. "
              "Im Backtest wird die Zahlung in der Kerze gebucht, die T enthält, für die zu T gehaltene Position. "
              "Die Präfix-Tests (tests/v2) prüfen das für funding_contrarian.", ""]
    for s, (grade, reasons, info) in result["funding"].items():
        lines.append(f"- **{s}: {grade}** {info} {'; '.join(reasons)}")
    for a in series:
        lines += ["", f"## {a.symbol} {a.timeframe}: {a.grade}", ""]
        lines += [f"- {r}" for r in a.reasons] + [f"- {n}" for n in a.notes]
        lines += ["", "```", a.summary, "```"]
        key = f"{a.symbol.replace('/', '').replace(':', '_')}_{a.timeframe}"
        for name, df in (("outliers", a.outliers), ("zero_volume", a.zero_volume), ("ohlc_bad", a.ohlc_bad),
                         ("gaps", a.gaps), ("crosstf", a.crosstf)):
            if len(df):
                df.to_csv(out / f"{key}_{name}.csv")
                lines.append(f"- Details: `{key}_{name}.csv` ({len(df)} Zeilen)")
        if len(a.outliers):
            lines += ["", "| Zeit | Rendite | Open-Gap | Volumen/Median | gleichzeitig bei | Bewertung |", "|---|---|---|---|---|---|"]
            for ts, r in a.outliers.head(20).iterrows():
                lines.append(f"| {ts} | {r['rendite_pct']:+.2f} % | {r['open_gap_log'] * 100:+.2f} % | "
                             f"{r['volumen_vs_median']:.1f} | {r['gleichzeitig_bei'] or '-'} | {r['bewertung']} |")
            if len(a.outliers) > 20:
                lines.append(f"| … | {len(a.outliers) - 20} weitere in der CSV-Datei | | | | |")
        if len(a.zero_volume):
            lines += ["", "| Zeit | Open | High | Low | Close | Volumen | Ursache |", "|---|---|---|---|---|---|---|"]
            for ts, r in a.zero_volume.head(20).iterrows():
                lines.append(f"| {ts} | {r['open']} | {r['high']} | {r['low']} | {r['close']} | {r['volume']} | {r['ursache']} |")
    path = out / "DATA_AUDIT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
