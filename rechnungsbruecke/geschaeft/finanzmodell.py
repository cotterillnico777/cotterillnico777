#!/usr/bin/env python3
"""Monatliches 36-Monats-Finanzmodell für die Rechnungsbrücke.

Liest annahmen.json und schreibt für jedes Szenario eine CSV mit Monatswerten sowie
ergebnisse/zusammenfassung.md (Jahreswerte, Break-even, Kapitalbedarf, Unit Economics).

Usage: python3 finanzmodell.py [pfad/zu/annahmen.json]
"""
import copy
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "ergebnisse"


def stufe(tabelle, x):
    """Wert einer Stufenfunktion [[ab_x, wert], ...] an der Stelle x."""
    wert = tabelle[0][1]
    for ab, w in tabelle:
        if x >= ab:
            wert = w
    return wert


def szenario_annahmen(basis, name):
    a = copy.deepcopy(basis)
    for pfad, wert in basis["szenarien"][name].items():
        gruppe, key = pfad.split(".")
        a[gruppe][key] = wert
    return a


def monatsname(start: str, m: int) -> str:
    jahr, monat = map(int, start.split("-"))
    idx = jahr * 12 + monat - 1 + m - 1
    return f"{idx // 12}-{idx % 12 + 1:02d}"


def arpa(conv) -> float:
    """Durchschnittlicher Monatsumsatz je zahlendem Kunden (nach Jahreszahlungsrabatt)."""
    brutto = sum(conv["tarifmix"][t] * conv["preise"][t] for t in conv["tarifmix"])
    return brutto * (1 - conv["rabatt_jahreszahlung_effektiv"])


def simuliere(a):
    n, conv, par, ein, k = a["nachfrage"], a["conversion"], a["partner"], a["einrichtung"], a["kosten"]
    umsatz_je_kunde = arpa(conv)
    anteil_business_plus = conv["tarifmix"]["business"] + conv["tarifmix"]["unternehmen"]

    free_pool = direkt = partnerkunden = kasse = 0.0
    zeilen = []
    for m in range(1, a["monate"] + 1):
        faktor = stufe(n["stichtag_faktor"], m)
        organisch = min(n["organisch_free_start"] * (1 + n["organisch_wachstum_mtl"]) ** (m - 1),
                        n["organisch_free_max"]) * faktor
        werbung = stufe(n["werbebudget"], m)
        bezahlt_free = werbung / n["kosten_je_free_installation"]
        neue_free = organisch + bezahlt_free

        # Free-Pool: Installationen, die (noch) nicht zahlen; ein Teil konvertiert, ein Teil springt ab
        neu_direkt = free_pool * conv["free_pool_zu_bezahlt_mtl"]
        free_pool = free_pool * (1 - conv["free_pool_zu_bezahlt_mtl"] - conv["free_pool_abgang_mtl"]) + neue_free
        neu_partner = stufe(par["neukunden_mtl"], m) if m >= par["start_monat"] else 0.0
        direkt = direkt * (1 - conv["churn_bezahlt_mtl"]) + neu_direkt
        partnerkunden = partnerkunden * (1 - conv["churn_bezahlt_mtl"]) + neu_partner
        kunden = direkt + partnerkunden

        umsatz_lizenzen = kunden * umsatz_je_kunde
        umsatz_einrichtung = (neu_direkt + neu_partner) * anteil_business_plus * ein["anteil_neukunden_business_plus"] \
            * ein["preis"]
        umsatz = umsatz_lizenzen + umsatz_einrichtung
        provision = partnerkunden * umsatz_je_kunde * par["provision"]
        gebuehren = umsatz * k["zahlungsgebuehren"]
        support = kunden * k["support_je_kunde_mtl"]

        fix = (
            (k["einmalig_monat_1"] if m == 1 else 0.0)
            + k["website_hosting_tools"] + k["steuerberatung"] + k["versicherung_it_haftpflicht"]
            + stufe(k["freelancer_entwicklung"], m) + stufe(k["support_teilzeit"], m) + werbung
        )
        ergebnis_vor_lohn = umsatz - provision - gebuehren - support - fix
        lohn = stufe(k["unternehmerlohn"], m)
        ergebnis = ergebnis_vor_lohn - lohn
        kasse += ergebnis
        zeilen.append({
            "monat": m, "kalendermonat": monatsname(a["startmonat"], m),
            "neue_free_installationen": neue_free, "free_pool": free_pool,
            "neukunden": neu_direkt + neu_partner, "kunden": kunden, "davon_partner": partnerkunden,
            "mrr": umsatz_lizenzen, "umsatz_einrichtung": umsatz_einrichtung, "umsatz_gesamt": umsatz,
            "provision_partner": provision, "zahlungsgebuehren": gebuehren, "support_variabel": support,
            "fixkosten": fix,
            "davon_werbung": werbung, "ergebnis_vor_unternehmerlohn": ergebnis_vor_lohn,
            "unternehmerlohn": lohn, "ergebnis": ergebnis, "kasse_kumuliert": kasse,
        })
    return zeilen


def unit_economics(a):
    n, conv = a["nachfrage"], a["conversion"]
    umsatz = arpa(conv)
    deckung = umsatz * (1 - a["kosten"]["zahlungsgebuehren"]) - a["kosten"]["support_je_kunde_mtl"]
    lebensdauer = 1 / conv["churn_bezahlt_mtl"]
    ltv = deckung * lebensdauer
    p, ab = conv["free_pool_zu_bezahlt_mtl"], conv["free_pool_abgang_mtl"]
    anteil_konvertiert = p / (p + ab)
    cac = n["kosten_je_free_installation"] / anteil_konvertiert
    return {"arpa": umsatz, "lebensdauer": lebensdauer, "ltv": ltv, "anteil_free_zu_bezahlt": anteil_konvertiert,
            "cac": cac, "ltv_cac": ltv / cac, "amortisation_monate": cac / deckung}


def kennzahlen(zeilen):
    jahre = []
    for j in range(len(zeilen) // 12):
        b = zeilen[j * 12:(j + 1) * 12]
        jahre.append({
            "jahr": j + 1,
            "umsatz": sum(z["umsatz_gesamt"] for z in b),
            "ergebnis_vor_lohn": sum(z["ergebnis_vor_unternehmerlohn"] for z in b),
            "unternehmerlohn": sum(z["unternehmerlohn"] for z in b),
            "ergebnis": sum(z["ergebnis"] for z in b),
            "kunden_ende": b[-1]["kunden"], "mrr_ende": b[-1]["mrr"],
        })
    break_even = next((zeilen[i]["monat"] for i in range(len(zeilen))
                       if all(z["ergebnis"] >= 0 for z in zeilen[i:])), None)
    return {"jahre": jahre, "break_even_monat": break_even,
            "kapitalbedarf": max(0.0, -min(z["kasse_kumuliert"] for z in zeilen)),
            "kasse_ende": zeilen[-1]["kasse_kumuliert"]}


def eur(x):
    return f"{x:,.0f} €".replace(",", ".")


def zahl(x):
    return f"{x:,.0f}".replace(",", ".")


def zusammenfassung(ergebnisse, ue, a):
    out = ["# Rechnungsbrücke – Ergebnisse des Finanzmodells", "",
           "_Automatisch erzeugt von `finanzmodell.py` aus `annahmen.json`. Nicht von Hand bearbeiten._", "",
           f"Monat 1 = {a['startmonat']}. Jahr 1 = Monate 1–12 (Nov 2026 – Okt 2027).", "",
           "## Szenarienvergleich", "", "| Kennzahl | " + " | ".join(ergebnisse) + " |",
           "|---|" + "---:|" * len(ergebnisse)]

    def zeile(label, fn):
        out.append(f"| {label} | " + " | ".join(fn(r) for r in ergebnisse.values()) + " |")

    for j in range(3):
        zeile(f"Umsatz Jahr {j + 1}", lambda r, j=j: eur(r["kpi"]["jahre"][j]["umsatz"]))
    for j in range(3):
        zeile(f"Ergebnis Jahr {j + 1} (nach Unternehmerlohn)", lambda r, j=j: eur(r["kpi"]["jahre"][j]["ergebnis"]))
    zeile("Unternehmerlohn 36 Monate", lambda r: eur(sum(y["unternehmerlohn"] for y in r["kpi"]["jahre"])))
    zeile("Zahlende Kunden Monat 36", lambda r: zahl(r["kpi"]["jahre"][2]["kunden_ende"]))
    zeile("Monatlich wiederkehrender Umsatz (MRR) Monat 36", lambda r: eur(r["kpi"]["jahre"][2]["mrr_ende"]))
    zeile("Break-even (Monat, dauerhaft)", lambda r: str(r["kpi"]["break_even_monat"] or "nicht erreicht"))
    zeile("Max. Kapitalbedarf", lambda r: eur(r["kpi"]["kapitalbedarf"]))
    zeile("Kasse nach 36 Monaten (vor Steuern)", lambda r: eur(r["kpi"]["kasse_ende"]))
    out += ["", "## Unit Economics (Basis)", "",
            f"- Ø Umsatz je Kunde und Monat (ARPA, nach Jahresrabatt): **{ue['arpa']:.2f} €**",
            f"- Ø Kundenlebensdauer: **{ue['lebensdauer']:.0f} Monate**",
            f"- Customer Lifetime Value (LTV): **{eur(ue['ltv'])}**",
            f"- Anteil Free-Installationen, die zahlende Kunden werden: **{ue['anteil_free_zu_bezahlt']:.0%}**",
            f"- Werbekosten je zahlendem Kunden (CAC): **{eur(ue['cac'])}**",
            f"- LTV/CAC: **{ue['ltv_cac']:.1f}** · Amortisation der Werbekosten: **{ue['amortisation_monate']:.1f} Monate**",
            ""]
    return "\n".join(out)


def main():
    pfad = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "annahmen.json"
    basis = json.loads(pfad.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(exist_ok=True)
    ergebnisse = {}
    for name in basis["szenarien"]:
        zeilen = simuliere(szenario_annahmen(basis, name))
        with open(OUT_DIR / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(zeilen[0]), delimiter=";")
            w.writeheader()
            w.writerows({k: round(v, 2) if isinstance(v, float) else v for k, v in z.items()} for z in zeilen)
        ergebnisse[name] = {"zeilen": zeilen, "kpi": kennzahlen(zeilen)}
    text = zusammenfassung(ergebnisse, unit_economics(szenario_annahmen(basis, "basis")), basis)
    (OUT_DIR / "zusammenfassung.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
