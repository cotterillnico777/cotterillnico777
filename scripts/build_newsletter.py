#!/usr/bin/env python3
"""Build the Finlyra newsletter editions and a social caption from a daily briefing.

Usage: python3 build_newsletter.py [YYYY-MM-DD]
Defaults to today's date. Reads briefings/<date>.md, writes to newsletter/<date>/:
  free.md / free.html   kostenlose Ausgabe (Denkfehler-Teaser + Gedanke des Tages + CTA)
  plus.md / plus.html   Finlyra-Plus-Ausgabe (Marktlage, Finanzwissen, Geld & Verhalten)
  social.txt            Caption für Instagram/LinkedIn aus der Finlyra-Relevanz
"""
import html
import re
import sys
from datetime import date
from pathlib import Path

from generate_finlyra_pdf import extract_section, extract_thema

REPO_ROOT = Path(__file__).resolve().parent.parent
BRIEFINGS_DIR = REPO_ROOT / "briefings"
OUT_ROOT = REPO_ROOT / "newsletter"

PLUS_URL = "https://finlyra.de/plus"
DISCLAIMER = (
    "Finlyra ist ein Bildungsangebot. Alle Inhalte dienen ausschließlich der "
    "Information und Weiterbildung und stellen keine Anlageberatung, keine "
    "Kauf- oder Verkaufsempfehlung und keine Kursprognose dar."
)
SECTIONS = {
    "markt": ("1. MARKTLAGE HEUTE", ["2. FINANZWISSEN DES TAGES"]),
    "wissen": ("2. FINANZWISSEN DES TAGES", ["3. GELD & VERHALTEN"]),
    "verhalten": ("3. GELD & VERHALTEN", ["4. FINLYRA-RELEVANZ"]),
    "finlyra": ("4. FINLYRA-RELEVANZ", ["__END__"]),
}


def strip_thema_heading(text: str) -> str:
    return re.sub(r"^###\s*Thema:.*\n?", "", text, count=1, flags=re.MULTILINE).strip()


def strip_internal_notes(text: str) -> str:
    """Remove the briefing's internal dedupe notes, e.g. *(Thema erstmals behandelt ...)*."""
    text = re.sub(r"\n-{3,}\s*$", "", text.strip())
    return re.sub(r"\n\*\((?:.|\n)*?\)\*\s*$", "", text).strip()


def hook(finlyra: str) -> str:
    """Reader-facing headline quoted in the (internal) Finlyra-Relevanz note, if any."""
    flat = re.sub(r"\s+", " ", finlyra)
    m = re.search(r'["„“]([^"„“]{20,}?)["“”]', flat)
    return m.group(1).strip() if m else ""


def kurzthema(thema: str) -> str:
    return re.split(r"\s+[—–-]\s+", thema, maxsplit=1)[0].strip()


def teaser(text: str, max_blocks: int = 2) -> str:
    """Hook paragraph plus the first bold-headed block (the definition)."""
    blocks = [b for b in re.split(r"\n\s*\n", strip_thema_heading(text)) if b.strip()]
    return "\n\n".join(blocks[:max_blocks])


def build_free(day: str, s: dict) -> str:
    thema = extract_thema(s["verhalten"]) or "Geld & Verhalten"
    parts = [
        f"# Finlyra – Denkfehler des Tages ({day})",
        f"## {thema}",
    ]
    if hook(s["finlyra"]):
        parts.append(f"> {hook(s['finlyra'])}")
    parts += [
        teaser(s["verhalten"]),
        f"**In Finlyra Plus** liest du heute die vollständige Analyse dieses Denkfehlers – "
        f"inklusive Gegenstrategien – sowie die Marktlage des Tages und "
        f"„{extract_thema(s['wissen'])}“ verständlich erklärt.",
    ]
    parts += [f"[Finlyra Plus testen – 14 Tage kostenlos]({PLUS_URL})", "---", f"*{DISCLAIMER}*"]
    return "\n\n".join(parts) + "\n"


def build_plus(day: str, s: dict) -> str:
    parts = [f"# Finlyra Plus – Ausgabe vom {day}"]
    if s["markt"]:
        parts += ["## Marktlage", strip_internal_notes(s["markt"])]
    if s["wissen"]:
        parts += [f"## Finanzwissen: {extract_thema(s['wissen'])}",
                  strip_internal_notes(strip_thema_heading(s["wissen"]))]
    if s["verhalten"]:
        parts += [f"## Geld & Verhalten: {extract_thema(s['verhalten'])}",
                  strip_internal_notes(strip_thema_heading(s["verhalten"]))]
    parts += ["---", f"*{DISCLAIMER}*"]
    return "\n\n".join(parts) + "\n"


def build_social(s: dict) -> str:
    kurz = kurzthema(extract_thema(s["verhalten"])) or "Geld & Verhalten"
    blocks = re.split(r"\n\s*\n", strip_thema_heading(s["verhalten"]))
    lead = re.sub(r"^Aufhänger von heute:\s*", "", re.sub(r"\s+", " ", blocks[0]).strip())
    titel = hook(s["finlyra"]) or f"Denkfehler des Tages: {kurz}"
    return (
        f"{titel}\n\n{lead}\n\n"
        f"Mehr im kostenlosen Finlyra-Newsletter (Link in Bio).\n\n"
        f"Keine Anlageberatung – reine Finanzbildung.\n\n"
        f"#Finanzbildung #Geldpsychologie #Finlyra #Behavioralfinance\n"
    )


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" style="color:#0b6e4f">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)


def md_to_html(md: str, title: str) -> str:
    """Minimal, e-mail-safe Markdown renderer for the briefing's subset of Markdown."""
    out, para, items = [], [], []

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        m = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if not stripped:
            flush()
        elif m:
            flush()
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
        elif re.fullmatch(r"-{3,}", stripped):
            flush()
            out.append("<hr>")
        elif re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            if para:
                flush()
            items.append(re.sub(r"^([-*]|\d+\.)\s+", "", stripped))
        elif items and raw.startswith(" "):
            items[-1] += " " + stripped
        elif stripped.startswith(">"):
            flush()
            out.append(f"<blockquote>{inline(stripped.lstrip('> '))}</blockquote>")
        elif stripped.startswith("|"):
            flush()
            out.append(f"<p style=\"font-family:monospace;font-size:13px\">{inline(stripped)}</p>")
        else:
            if items:
                flush()
            para.append(stripped)
    flush()

    body = "\n".join(out)
    return (
        "<!doctype html>\n<html lang=\"de\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(title)}</title>"
        "<style>body{margin:0;background:#f6f5f2;color:#1d1d1b;font:16px/1.6 Georgia,serif}"
        ".w{max-width:640px;margin:0 auto;padding:24px 16px;background:#fff}"
        "h1{font-size:24px;color:#0b6e4f}h2{font-size:20px;margin-top:28px}h3{font-size:17px}"
        "hr{border:0;border-top:1px solid #ddd;margin:24px 0}"
        "blockquote{margin:0;padding-left:12px;border-left:3px solid #0b6e4f;color:#555}</style>"
        f"</head><body><div class=\"w\">\n{body}\n</div></body></html>\n"
    )


def build(day: str) -> Path:
    md_path = BRIEFINGS_DIR / f"{day}.md"
    if not md_path.exists():
        raise FileNotFoundError(f"Briefing nicht gefunden: {md_path}")
    text = md_path.read_text(encoding="utf-8")
    s = {k: extract_section(text, h, nxt) for k, (h, nxt) in SECTIONS.items()}
    if not s["verhalten"]:
        raise ValueError(f"Abschnitt '3. GELD & VERHALTEN' fehlt in {md_path}")

    out = OUT_ROOT / day
    out.mkdir(parents=True, exist_ok=True)
    free, plus = build_free(day, s), build_plus(day, s)
    (out / "free.md").write_text(free, encoding="utf-8")
    (out / "plus.md").write_text(plus, encoding="utf-8")
    (out / "free.html").write_text(md_to_html(free, f"Finlyra {day}"), encoding="utf-8")
    (out / "plus.html").write_text(md_to_html(plus, f"Finlyra Plus {day}"), encoding="utf-8")
    (out / "social.txt").write_text(build_social(s), encoding="utf-8")
    return out


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    try:
        out = build(day)
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(f"Newsletter erstellt: {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
