"""Erzeugt eine ZUGFeRD-/Factur-X-Rechnung: lesbares PDF/A-3 mit eingebettetem CII-XML."""
import io
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from .ansicht import EINHEIT_TEXT, TYPEN, eur, menge
from .cii import erzeuge_cii
from .modell import Rechnung

SCHRIFT_KANDIDATEN = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]


class PdfFehler(RuntimeError):
    pass


def _schriften() -> tuple[str, str]:
    """PDF/A verlangt eingebettete Schriften, daher wird eine TrueType-Schrift benötigt."""
    if "RB" in pdfmetrics.getRegisteredFontNames():
        return "RB", "RB-Bold"
    kandidaten = SCHRIFT_KANDIDATEN
    if os.environ.get("RB_SCHRIFT"):
        normal = os.environ["RB_SCHRIFT"]
        kandidaten = [(normal, os.environ.get("RB_SCHRIFT_FETT", normal))]
    for normal, fett in kandidaten:
        if Path(normal).exists() and Path(fett).exists():
            pdfmetrics.registerFont(TTFont("RB", normal))
            pdfmetrics.registerFont(TTFont("RB-Bold", fett))
            return "RB", "RB-Bold"
    raise PdfFehler("Keine TrueType-Schrift gefunden. Pfad über Umgebungsvariable RB_SCHRIFT angeben.")


def _visuelles_pdf(r: Rechnung) -> bytes:
    normal, fett = _schriften()
    s = ParagraphStyle("n", fontName=normal, fontSize=9.5, leading=13)
    klein = ParagraphStyle("k", parent=s, fontSize=7.5, leading=10, textColor=colors.HexColor("#555555"))
    titel = ParagraphStyle("t", parent=s, fontName=fett, fontSize=16, leading=20, spaceAfter=6)
    v, k = r.verkaeufer, r.kaeufer
    w = r.waehrung

    def p(text, style=s):
        return Paragraph(text.replace("&", "&amp;").replace("\n", "<br/>"), style)

    story = [
        p(f"{v.name} · {v.anschrift.strasse} · {v.anschrift.plz} {v.anschrift.ort}", klein),
        Spacer(0, 3 * mm),
        p(f"{k.name}\n{k.anschrift.strasse}\n{k.anschrift.plz} {k.anschrift.ort}"
          + ("" if k.anschrift.land == "DE" else f"\n{k.anschrift.land}")),
        Spacer(0, 12 * mm),
        p(f"{TYPEN.get(r.typ, 'Rechnung')} {r.nummer}", titel),
    ]
    meta = [["Rechnungsdatum", r.datum.strftime("%d.%m.%Y")]]
    if r.leistungsdatum:
        meta.append(["Leistungsdatum", r.leistungsdatum.strftime("%d.%m.%Y")])
    if r.leistungszeitraum:
        meta.append(["Leistungszeitraum", f"{r.leistungszeitraum[0]:%d.%m.%Y} – {r.leistungszeitraum[1]:%d.%m.%Y}"])
    if r.kaeufer_referenz:
        meta.append(["Ihre Referenz", r.kaeufer_referenz])
    if r.bestellnummer:
        meta.append(["Bestellnummer", r.bestellnummer])
    if k.ust_id:
        meta.append(["Ihre USt-IdNr.", k.ust_id])
    story += [Table(meta, colWidths=[40 * mm, 80 * mm], hAlign="LEFT",
                    style=[("FONT", (0, 0), (-1, -1), normal, 9.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]),
              Spacer(0, 8 * mm)]

    daten = [["Pos.", "Bezeichnung", "Menge", "Einzelpreis", "USt", "Netto"]]
    for i, pos in enumerate(r.positionen, start=1):
        daten.append([str(i), p(pos.bezeichnung), f"{menge(pos.menge)} {EINHEIT_TEXT.get(pos.einheit, pos.einheit)}",
                      eur(pos.einzelpreis, w), f"{menge(pos.ust_satz)} %", eur(pos.netto, w)])
    n_pos = len(daten)
    daten.append(["", "Summe netto", "", "", "", eur(r.netto, w)])
    for st in r.steuern:
        label = f"USt {menge(st.satz)} % auf {eur(st.basis, w)}" if st.kategorie in ("S", "Z") else st.befreiungsgrund
        daten.append(["", p(label), "", "", "", eur(st.steuer, w)])
    daten.append(["", "Gesamtbetrag", "", "", "", eur(r.brutto, w)])
    if r.vorauszahlung:
        daten.append(["", "Bereits gezahlt", "", "", "", eur(-r.vorauszahlung, w)])
        daten.append(["", "Zahlbetrag", "", "", "", eur(r.zahlbetrag, w)])
    story.append(Table(daten, colWidths=[11 * mm, 72 * mm, 22 * mm, 26 * mm, 15 * mm, 26 * mm], repeatRows=1, style=[
        ("FONT", (0, 0), (-1, -1), normal, 9.5),
        ("FONT", (0, 0), (-1, 0), fett, 9.5),
        ("FONT", (0, len(daten) - 1), (-1, len(daten) - 1), fett, 9.5),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
        ("LINEBELOW", (0, n_pos - 1), (-1, n_pos - 1), 0.6, colors.black),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black),
    ]))
    story.append(Spacer(0, 8 * mm))
    zahlung = []
    if r.zahlungsbedingungen:
        zahlung.append(r.zahlungsbedingungen + (f" (fällig am {r.faelligkeit:%d.%m.%Y})" if r.faelligkeit else "") + ".")
    if r.bank:
        zahlung.append(f"Bitte überweisen Sie {eur(r.zahlbetrag, w)} auf IBAN {r.bank.iban}"
                       + (f", BIC {r.bank.bic}" if r.bank.bic else "") + f", Verwendungszweck {r.nummer}.")
    if r.bemerkung:
        zahlung.append(r.bemerkung)
    story += [p(z) for z in zahlung]
    story.append(Spacer(0, 10 * mm))
    fuss = [f"{v.name} · {v.anschrift.strasse} · {v.anschrift.plz} {v.anschrift.ort}"]
    ids = [x for x in (f"USt-IdNr. {v.ust_id}" if v.ust_id else "", f"Steuernr. {v.steuernummer}" if v.steuernummer else "",
                       v.registernummer) if x]
    if ids:
        fuss.append(" · ".join(ids))
    if v.kontakt_name:
        fuss.append(f"Ansprechpartner: {v.kontakt_name} · {v.kontakt_telefon} · {v.kontakt_email}")
    fuss.append("Diese Rechnung enthält eine strukturierte E-Rechnung (ZUGFeRD/Factur-X, EN 16931).")
    story += [p(f, klein) for f in fuss]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                      bottomMargin=18 * mm, title=f"Rechnung {r.nummer}", author=v.name,
                      lang="de-DE", initialFontName=normal).build(story)
    return buf.getvalue()


def _mit_output_intent(pdf: bytes) -> bytes:
    """PDF/A verlangt einen OutputIntent mit eingebettetem ICC-Farbprofil (sRGB)."""
    from PIL import ImageCms
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (ArrayObject, DictionaryObject, NameObject, NumberObject, StreamObject,
                               TextStringObject)

    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    stream = StreamObject()
    stream.set_data(icc)
    stream[NameObject("/N")] = NumberObject(3)
    intent = DictionaryObject({
        NameObject("/Type"): NameObject("/OutputIntent"),
        NameObject("/S"): NameObject("/GTS_PDFA1"),
        NameObject("/OutputConditionIdentifier"): TextStringObject("sRGB IEC61966-2.1"),
        NameObject("/Info"): TextStringObject("sRGB IEC61966-2.1"),
        NameObject("/DestOutputProfile"): writer._add_object(stream),
    })
    writer._root_object[NameObject("/OutputIntents")] = ArrayObject([writer._add_object(intent)])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def erzeuge_zugferd(r: Rechnung, xml: bytes | None = None) -> bytes:
    """`xml` ist das bereits geprüfte CII-XML (Profil zugferd); fehlt es, wird es erzeugt."""
    from facturx import generate_from_binary

    xml = xml or erzeuge_cii(r, profil="zugferd")
    pdf = _mit_output_intent(_visuelles_pdf(r))
    return generate_from_binary(
        pdf, xml, flavor="factur-x", level="en16931", check_xsd=True, lang="de-DE",
        pdf_metadata={"author": r.verkaeufer.name, "keywords": "Rechnung, ZUGFeRD, Factur-X",
                      "title": f"{r.verkaeufer.name}: Rechnung {r.nummer}",
                      "subject": f"Rechnung {r.nummer} vom {r.datum:%d.%m.%Y}"},
    )
