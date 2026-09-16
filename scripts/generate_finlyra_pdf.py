#!/usr/bin/env python3
"""Extract the FINLYRA-RELEVANZ section from a daily briefing and render it as a
standalone one-page PDF for the Content Agent.

Usage: python3 generate_finlyra_pdf.py [YYYY-MM-DD]
Defaults to today's date. Reads briefings/<date>.md, writes
briefings/finlyra/<date>-finlyra.pdf.
"""
import re
import sys
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

REPO_ROOT = Path(__file__).resolve().parent.parent
BRIEFINGS_DIR = REPO_ROOT / "briefings"
OUT_DIR = BRIEFINGS_DIR / "finlyra"


def extract_section(text: str, heading: str, next_headings: list[str]) -> str:
    pattern = rf"##\s*{re.escape(heading)}\s*\n(.*?)(?=\n##\s*(?:{'|'.join(re.escape(h) for h in next_headings)})|\Z)"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""


def extract_thema(section_text: str) -> str:
    m = re.search(r"###\s*Thema:\s*(.+)", section_text)
    return m.group(1).strip() if m else ""


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    md_path = BRIEFINGS_DIR / f"{day}.md"
    if not md_path.exists():
        print(f"Briefing nicht gefunden: {md_path}", file=sys.stderr)
        sys.exit(1)

    text = md_path.read_text(encoding="utf-8")

    finanzwissen = extract_section(
        text, "2. FINANZWISSEN DES TAGES", ["3. GELD & VERHALTEN"]
    )
    verhalten = extract_section(
        text, "3. GELD & VERHALTEN", ["4. FINLYRA-RELEVANZ"]
    )
    finlyra = extract_section(text, "4. FINLYRA-RELEVANZ", ["__END__"])

    finanzwissen_thema = extract_thema(finanzwissen)
    verhalten_thema = extract_thema(verhalten)

    if not finlyra:
        finlyra = "Kein Content-relevantes Thema für Finlyra an diesem Tag identifiziert."

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{day}-finlyra.pdf"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom", parent=styles["Title"], fontSize=18, spaceAfter=4,
    )
    date_style = ParagraphStyle(
        "DateCustom", parent=styles["Normal"], fontSize=10, textColor="#666666",
        spaceAfter=16,
    )
    label_style = ParagraphStyle(
        "Label", parent=styles["Normal"], fontSize=9, textColor="#888888",
        spaceBefore=10, spaceAfter=2, alignment=TA_LEFT,
    )
    context_style = ParagraphStyle(
        "Context", parent=styles["Normal"], fontSize=11, spaceAfter=2,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=13, leading=18, spaceBefore=6,
    )

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
    )

    story = [
        Paragraph("Finlyra-Relevanz", title_style),
        Paragraph(f"Aus dem Finanz-Rundum-Briefing vom {day}", date_style),
        HRFlowable(width="100%", thickness=0.75, color="#cccccc"),
    ]

    if finanzwissen_thema or verhalten_thema:
        story.append(Paragraph("Themen des Tages", label_style))
        if finanzwissen_thema:
            story.append(Paragraph(f"Finanzwissen: {finanzwissen_thema}", context_style))
        if verhalten_thema:
            story.append(Paragraph(f"Geld &amp; Verhalten: {verhalten_thema}", context_style))

    story.append(Paragraph("Content-Idee", label_style))
    finlyra_html = finlyra.replace("\n", " ").strip()
    story.append(Paragraph(finlyra_html, body_style))

    doc.build(story)
    print(f"PDF erstellt: {out_path}")


if __name__ == "__main__":
    main()
