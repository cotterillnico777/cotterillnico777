#!/usr/bin/env python3
"""Monatliches 36-Monats-Finanzmodell für Finlyra.

Liest annahmen.json, simuliert Publikum, Umsätze und Kosten pro Monat für die
Szenarien pessimistisch/basis/optimistisch und schreibt:
  ergebnisse/<szenario>.csv     Monatswerte
  ergebnisse/zusammenfassung.md Jahreswerte, Break-even, Kapitalbedarf, Unit Economics

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


def simuliere(a):
    netto = 1 + a["ust_satz"]
    pub, plus, dig, spo, b2b, k = (
        a["publikum"], a["plus_abo"], a["digitale_produkte"],
        a["sponsoring"], a["b2b"], a["kosten"],
    )

    free = plus_monat = plus_jahr = 0.0
    b2b_kunden = 0.0
    kasse = 0.0
    zeilen = []

    for m in range(1, a["monate"] + 1):
        # --- Publikum ---
        organisch = min(pub["organisch_neu_start"] * (1 + pub["organisch_wachstum_mtl"]) ** (m - 1),
                        pub["organisch_neu_max"])
        werbung = stufe(pub["werbebudget_mtl"], m) if m >= pub["werbebudget_start_monat"] else 0.0
        bezahlt_neu = werbung / pub["cac_free_abonnent"]
        neu_free = organisch + bezahlt_neu
        free = free * (1 - pub["free_churn_mtl"]) + neu_free

        # --- Plus-Abo ---
        if m >= plus["start_monat"]:
            neu_plus = free * plus["conversion_free_zu_plus_mtl"]
            plus_monat = plus_monat * (1 - plus["churn_mtl"]) + neu_plus * (1 - plus["anteil_jahresabo"])
            plus_jahr = plus_jahr * (1 - plus["churn_mtl"]) + neu_plus * plus["anteil_jahresabo"]
        plus_gesamt = plus_monat + plus_jahr
        # Umsatz monatlich realisiert (Jahresabo anteilig), Gebühren je Zahlung
        preis_m = plus["preis_monat_brutto"]
        preis_j = plus["preis_jahr_brutto"]
        umsatz_plus = plus_monat * preis_m / netto + plus_jahr * preis_j / 12 / netto
        gebuehren_plus = (plus_monat * (preis_m * plus["stripe_prozent"] + plus["stripe_fix"])
                          + plus_jahr * (preis_j * plus["stripe_prozent"] + plus["stripe_fix"]) / 12)

        # --- Digitale Produkte ---
        ebooks = neu_free * dig["ebook_conversion_neue_free"] if m >= dig["ebook_start_monat"] else 0.0
        kurse = ((free * dig["kurs_conversion_free_list_mtl"] + plus_gesamt * dig["kurs_conversion_plus_mtl"])
                 if m >= dig["kurs_start_monat"] else 0.0)
        umsatz_produkte = ebooks * dig["ebook_preis_brutto"] / netto + kurse * dig["kurs_preis_brutto"] / netto
        gebuehren_produkte = (ebooks * (dig["ebook_preis_brutto"] * plus["stripe_prozent"] + plus["stripe_fix"])
                              + kurse * (dig["kurs_preis_brutto"] * plus["stripe_prozent"] + plus["stripe_fix"]))

        # --- Sponsoring ---
        umsatz_sponsoring = 0.0
        if free >= spo["ab_free_abonnenten"]:
            umsatz_sponsoring = (free / 1000 * spo["cpm_eur"] * spo["ausgaben_pro_monat"]
                                 * stufe(spo["auslastung"], m))

        # --- B2B ---
        umsatz_b2b = workshop_kosten = 0.0
        if m >= b2b["start_monat"]:
            b2b_kunden = b2b_kunden * (1 - b2b["kunden_churn_mtl"]) + stufe(b2b["neukunden_mtl"], m)
            workshops = stufe(b2b["workshops_mtl"], m)
            umsatz_b2b = b2b_kunden * b2b["lizenz_jahreswert"] / 12 + workshops * b2b["workshop_preis"]
            workshop_kosten = workshops * b2b["workshop_direktkosten"]

        umsatz = umsatz_plus + umsatz_produkte + umsatz_sponsoring + umsatz_b2b
        variable_kosten = gebuehren_plus + gebuehren_produkte + workshop_kosten
        rohertrag = umsatz - variable_kosten

        # --- Fixkosten ---
        fix = {
            "einmalig": k["einmalig_monat_1"] if m == 1 else 0.0,
            "software": stufe(k["newsletter_software"], free),
            "ki_daten": k["ki_und_daten"],
            "hosting": k["hosting_domain_tools"],
            "steuerberatung": k["steuerberatung"],
            "versicherung": k["versicherung"],
            "freelancer": stufe(k["freelancer_design_video"], m),
            "redaktion": stufe(k["teilzeit_redaktion"], m),
            "werbung": werbung,
        }
        fixkosten = sum(fix.values())
        ebitda_vor_lohn = rohertrag - fixkosten
        lohn = stufe(k["unternehmerlohn"], m)
        ergebnis = ebitda_vor_lohn - lohn
        kasse += ergebnis

        zeilen.append({
            "monat": m,
            "free_abonnenten": free,
            "neu_free": neu_free,
            "plus_mitglieder": plus_gesamt,
            "b2b_kunden": b2b_kunden,
            "umsatz_plus": umsatz_plus,
            "umsatz_produkte": umsatz_produkte,
            "umsatz_sponsoring": umsatz_sponsoring,
            "umsatz_b2b": umsatz_b2b,
            "umsatz_gesamt": umsatz,
            "variable_kosten": variable_kosten,
            "fixkosten": fixkosten,
            "davon_werbung": werbung,
            "ergebnis_vor_unternehmerlohn": ebitda_vor_lohn,
            "unternehmerlohn": lohn,
            "ergebnis": ergebnis,
            "kasse_kumuliert": kasse,
        })
    return zeilen


def unit_economics(a):
    plus, pub = a["plus_abo"], a["publikum"]
    netto = 1 + a["ust_satz"]
    j = plus["anteil_jahresabo"]
    arpu = ((1 - j) * (plus["preis_monat_brutto"] / netto
                       - plus["preis_monat_brutto"] * plus["stripe_prozent"] - plus["stripe_fix"])
            + j * (plus["preis_jahr_brutto"] / netto
                   - plus["preis_jahr_brutto"] * plus["stripe_prozent"] - plus["stripe_fix"]) / 12)
    lebensdauer = 1 / plus["churn_mtl"]
    ltv = arpu * lebensdauer
    # CAC je zahlendem Mitglied, wenn Free-Abonnenten über die Lebensdauer im Free-Status konvertieren
    conv = plus["conversion_free_zu_plus_mtl"]
    lebenszeit_conversion = conv / (conv + pub["free_churn_mtl"])
    cac_plus = pub["cac_free_abonnent"] / lebenszeit_conversion
    return {
        "arpu_netto_nach_gebuehren": arpu,
        "lebensdauer_monate": lebensdauer,
        "ltv_plus": ltv,
        "lebenszeit_conversion_free_zu_plus": lebenszeit_conversion,
        "cac_je_plus_mitglied": cac_plus,
        "ltv_cac": ltv / cac_plus,
    }


def kennzahlen(zeilen):
    jahre = []
    for j in range(len(zeilen) // 12):
        block = zeilen[j * 12:(j + 1) * 12]
        jahre.append({
            "jahr": j + 1,
            "umsatz": sum(z["umsatz_gesamt"] for z in block),
            "umsatz_plus": sum(z["umsatz_plus"] for z in block),
            "umsatz_produkte": sum(z["umsatz_produkte"] for z in block),
            "umsatz_sponsoring": sum(z["umsatz_sponsoring"] for z in block),
            "umsatz_b2b": sum(z["umsatz_b2b"] for z in block),
            "kosten": sum(z["variable_kosten"] + z["fixkosten"] for z in block),
            "ergebnis_vor_lohn": sum(z["ergebnis_vor_unternehmerlohn"] for z in block),
            "unternehmerlohn": sum(z["unternehmerlohn"] for z in block),
            "ergebnis": sum(z["ergebnis"] for z in block),
            "free_ende": block[-1]["free_abonnenten"],
            "plus_ende": block[-1]["plus_mitglieder"],
            "b2b_ende": block[-1]["b2b_kunden"],
        })
    # Break-even: erster Monat, ab dem das Monatsergebnis (nach Unternehmerlohn) dauerhaft >= 0 ist
    break_even = None
    for i in range(len(zeilen)):
        if all(z["ergebnis"] >= 0 for z in zeilen[i:]):
            break_even = zeilen[i]["monat"]
            break
    tiefster_kassenstand = min(z["kasse_kumuliert"] for z in zeilen)
    return {
        "jahre": jahre,
        "break_even_monat": break_even,
        "kapitalbedarf": max(0.0, -tiefster_kassenstand),
        "kasse_ende": zeilen[-1]["kasse_kumuliert"],
        "mrr_ende": zeilen[-1]["umsatz_gesamt"],
    }


def eur(x):
    return f"{x:,.0f} €".replace(",", ".")


def zahl(x):
    return f"{x:,.0f}".replace(",", ".")


def schreibe_csv(pfad, zeilen):
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()), delimiter=";")
        w.writeheader()
        for z in zeilen:
            w.writerow({k: (round(v, 2) if isinstance(v, float) else v) for k, v in z.items()})


def zusammenfassung(ergebnisse, ue, steuer_satz):
    out = ["# Finlyra – Ergebnisse des Finanzmodells", "",
           "_Automatisch erzeugt von `finanzmodell.py` aus `annahmen.json`. Nicht von Hand bearbeiten._", ""]
    out += ["## Szenarienvergleich", "",
            "| Kennzahl | " + " | ".join(ergebnisse) + " |",
            "|---|" + "---:|" * len(ergebnisse)]

    def zeile(label, fn):
        out.append(f"| {label} | " + " | ".join(fn(r) for r in ergebnisse.values()) + " |")

    for j in range(3):
        zeile(f"Umsatz Jahr {j + 1}", lambda r, j=j: eur(r["kpi"]["jahre"][j]["umsatz"]))
    for j in range(3):
        zeile(f"Ergebnis Jahr {j + 1} (nach Unternehmerlohn)", lambda r, j=j: eur(r["kpi"]["jahre"][j]["ergebnis"]))
    zeile("Unternehmerlohn 36 Monate", lambda r: eur(sum(y["unternehmerlohn"] for y in r["kpi"]["jahre"])))
    zeile("Monatsumsatz in Monat 36", lambda r: eur(r["kpi"]["mrr_ende"]))
    zeile("Free-Abonnenten Monat 36", lambda r: zahl(r["kpi"]["jahre"][2]["free_ende"]))
    zeile("Plus-Mitglieder Monat 36", lambda r: zahl(r["kpi"]["jahre"][2]["plus_ende"]))
    zeile("B2B-Kunden Monat 36", lambda r: zahl(r["kpi"]["jahre"][2]["b2b_ende"]))
    zeile("Break-even (Monat, dauerhaft)", lambda r: str(r["kpi"]["break_even_monat"] or "nicht erreicht"))
    zeile("Max. Kapitalbedarf", lambda r: eur(r["kpi"]["kapitalbedarf"]))
    zeile("Kasse nach 36 Monaten (vor Steuern)", lambda r: eur(r["kpi"]["kasse_ende"]))
    zeile(f"Ergebnis Jahr 3 nach Steuerrücklage ({steuer_satz:.0%})",
          lambda r: eur(r["kpi"]["jahre"][2]["ergebnis"] * (1 - steuer_satz)
                        if r["kpi"]["jahre"][2]["ergebnis"] > 0 else r["kpi"]["jahre"][2]["ergebnis"]))

    basis = ergebnisse["basis"]["kpi"]
    out += ["", "## Basis-Szenario: Umsatzmix", "",
            "| Jahr | Plus-Abo | Digitale Produkte | Sponsoring | B2B | Gesamt | Kosten | Ergebnis vor Lohn | Ergebnis |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for y in basis["jahre"]:
        out.append(f"| {y['jahr']} | {eur(y['umsatz_plus'])} | {eur(y['umsatz_produkte'])} | "
                   f"{eur(y['umsatz_sponsoring'])} | {eur(y['umsatz_b2b'])} | {eur(y['umsatz'])} | "
                   f"{eur(y['kosten'])} | {eur(y['ergebnis_vor_lohn'])} | {eur(y['ergebnis'])} |")

    out += ["", "## Unit Economics Plus-Abo (Basis)", "",
            f"- Ø Netto-Erlös je Mitglied und Monat (nach USt und Zahlungsgebühren): **{ue['arpu_netto_nach_gebuehren']:.2f} €**",
            f"- Ø Lebensdauer: **{ue['lebensdauer_monate']:.1f} Monate**",
            f"- Customer Lifetime Value (LTV): **{ue['ltv_plus']:.2f} €**",
            f"- Anteil Free-Abonnenten, die irgendwann Plus werden: **{ue['lebenszeit_conversion_free_zu_plus']:.1%}**",
            f"- Werbekosten je gewonnenem Plus-Mitglied (CAC): **{ue['cac_je_plus_mitglied']:.2f} €**",
            f"- LTV/CAC: **{ue['ltv_cac']:.1f}** (Zielwert ≥ 3; Produkte, Sponsoring und B2B kommen zusätzlich hinzu)",
            ""]
    return "\n".join(out)


def main():
    pfad = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "annahmen.json"
    basis = json.loads(pfad.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(exist_ok=True)

    ergebnisse = {}
    for name in basis["szenarien"]:
        a = szenario_annahmen(basis, name)
        zeilen = simuliere(a)
        schreibe_csv(OUT_DIR / f"{name}.csv", zeilen)
        ergebnisse[name] = {"zeilen": zeilen, "kpi": kennzahlen(zeilen)}

    ue = unit_economics(szenario_annahmen(basis, "basis"))
    text = zusammenfassung(ergebnisse, ue, basis["steuer_ruecklage_satz"])
    (OUT_DIR / "zusammenfassung.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
