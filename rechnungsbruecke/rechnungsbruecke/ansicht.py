"""Lesbare Darstellung (HTML) und Buchungsliste (CSV) für gelesene E-Rechnungen."""
import csv
import html
from decimal import Decimal
from pathlib import Path

from .leser import Eingangsrechnung

TYPEN = {"380": "Rechnung", "381": "Gutschrift", "384": "Rechnungskorrektur", "389": "Selbstfakturierte Rechnung",
         "326": "Teilrechnung", "875": "Teilschlussrechnung", "877": "Schlussrechnung"}

EINHEIT_TEXT = {"C62": "Stk", "H87": "Stk", "HUR": "Std", "DAY": "Tag", "KGM": "kg", "MTR": "m", "MTK": "m²",
                "MTQ": "m³", "LTR": "l", "LS": "pauschal", "MON": "Monat", "TNE": "t", "KMT": "km"}


def eur(d: Decimal, waehrung: str = "EUR") -> str:
    s = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {'€' if waehrung == 'EUR' else waehrung}"


def menge(d: Decimal) -> str:
    return format(d.normalize(), "f").replace(".", ",")


def als_html(r: Eingangsrechnung) -> str:
    e = lambda s: html.escape(str(s or ""))  # noqa: E731
    zeilen = "".join(
        f"<tr><td>{i}</td><td>{e(z.bezeichnung)}</td><td class=n>{menge(z.menge)} {e(EINHEIT_TEXT.get(z.einheit, z.einheit))}</td>"
        f"<td class=n>{eur(z.einzelpreis, r.waehrung)}</td><td class=n>{menge(z.satz)} % ({e(z.kategorie)})</td>"
        f"<td class=n>{eur(z.netto, r.waehrung)}</td></tr>"
        for i, z in enumerate(r.zeilen, start=1))
    steuern = "".join(
        f"<tr><td colspan=5>USt {menge(s.satz)} % auf {eur(s.basis, r.waehrung)}"
        f"{' – ' + e(s.grund) if s.grund else ''}</td><td class=n>{eur(s.steuer, r.waehrung)}</td></tr>"
        for s in r.steuern)
    probleme = r.plausibilitaet()
    warnung = ("<div class=warn><strong>Achtung, Rechenfehler:</strong><ul>"
               + "".join(f"<li>{e(p)}</li>" for p in probleme) + "</ul></div>") if probleme else ""
    bem = "".join(f"<p>{e(b)}</p>" for b in r.bemerkungen)
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(TYPEN.get(r.typ, 'Rechnung'))} {e(r.nummer)}</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;margin:0;background:#f4f5f7;color:#1c1e21}}
.w{{max-width:860px;margin:0 auto;padding:24px 16px;background:#fff}}
h1{{font-size:22px;margin:0 0 4px}} .meta{{color:#555;margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
.box{{border:1px solid #ddd;border-radius:6px;padding:10px 12px}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:6px 4px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}}
.n{{text-align:right;white-space:nowrap}} tfoot td{{font-weight:600}}
.warn{{background:#fff3cd;border:1px solid #e0b100;padding:8px 12px;border-radius:6px;margin-bottom:16px}}
@media (max-width:600px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="w">
<h1>{e(TYPEN.get(r.typ, 'Rechnung ' + r.typ))} {e(r.nummer)}</h1>
<div class="meta">vom {e(r.datum)} · Format {e(r.syntax)} · {e(r.profil)}</div>
{warnung}
<div class="grid">
<div class="box"><strong>Von</strong><br>{e(r.verkaeufer)}<br>{e(r.verkaeufer_anschrift)}<br>
USt-IdNr.: {e(r.verkaeufer_ust_id) or '–'}<br>{e(r.verkaeufer_email)}</div>
<div class="box"><strong>An</strong><br>{e(r.kaeufer)}<br>Referenz: {e(r.kaeufer_referenz) or '–'}<br>
<strong>Zahlung</strong><br>IBAN {e(r.iban) or '–'} {('· BIC ' + e(r.bic)) if r.bic else ''}<br>
Fällig: {e(r.faelligkeit) or '–'}<br>{e(r.zahlungsbedingungen)}</div>
</div>
<table><thead><tr><th>#</th><th>Bezeichnung</th><th class=n>Menge</th><th class=n>Einzelpreis</th><th class=n>USt</th><th class=n>Netto</th></tr></thead>
<tbody>{zeilen}</tbody>
<tfoot><tr><td colspan=5>Summe netto</td><td class=n>{eur(r.netto, r.waehrung)}</td></tr>{steuern}
<tr><td colspan=5>Gesamtbetrag</td><td class=n>{eur(r.brutto, r.waehrung)}</td></tr>
<tr><td colspan=5>Zahlbetrag</td><td class=n>{eur(r.zahlbetrag, r.waehrung)}</td></tr></tfoot></table>
{bem}
</div></body></html>
"""


BUCHUNG_SPALTEN = ["rechnungsnummer", "rechnungsdatum", "faelligkeit", "lieferant", "lieferant_ust_id", "iban",
                   "steuerkategorie", "ust_satz", "netto", "ust", "brutto", "waehrung"]


def buchungszeilen(r: Eingangsrechnung) -> list[dict]:
    """Eine Zeile je Steuersatz, z. B. für den Import in die Buchhaltung."""
    return [{
        "rechnungsnummer": r.nummer, "rechnungsdatum": r.datum, "faelligkeit": r.faelligkeit,
        "lieferant": r.verkaeufer, "lieferant_ust_id": r.verkaeufer_ust_id, "iban": r.iban,
        "steuerkategorie": s.kategorie, "ust_satz": menge(s.satz),
        "netto": f"{s.basis:.2f}".replace(".", ","), "ust": f"{s.steuer:.2f}".replace(".", ","),
        "brutto": f"{s.basis + s.steuer:.2f}".replace(".", ","), "waehrung": r.waehrung,
    } for s in r.steuern]


def schreibe_buchungsliste(pfad: Path, rechnungen: list[Eingangsrechnung]) -> None:
    neu = not Path(pfad).exists()
    with open(pfad, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=BUCHUNG_SPALTEN, delimiter=";")
        if neu:
            w.writeheader()
        for r in rechnungen:
            w.writerows(buchungszeilen(r))
