# Finlyra

Deutschsprachige Finanzbildung mit Fokus auf Geldpsychologie. Keine Anlageberatung.

| Ordner | Inhalt |
|---|---|
| [`business/geschaeftsmodell.md`](business/geschaeftsmodell.md) | Geschäftsmodell: Zielgruppe, Produkte & Preise, Go-to-Market, Finanzplan, Recht, Risiken, KPIs, 90-Tage-Plan |
| [`business/finanzmodell/`](business/finanzmodell/) | 36-Monats-Finanzmodell (`annahmen.json` → `finanzmodell.py` → `ergebnisse/`) |
| [`briefings/`](briefings/) | Tägliches Finanz-Rundum-Briefing (Content-Quelle) |
| [`scripts/`](scripts/) | `generate_finlyra_pdf.py` (Content-Briefing-PDF), `build_newsletter.py` (Free-/Plus-Newsletter + Social-Caption) |
| [`newsletter/`](newsletter/) | Erzeugte Newsletter-Ausgaben |

```bash
python3 business/finanzmodell/finanzmodell.py   # Finanzmodell neu berechnen
python3 scripts/build_newsletter.py 2026-10-09   # Newsletter aus einem Briefing erzeugen
python3 -m unittest discover tests               # Tests
```
