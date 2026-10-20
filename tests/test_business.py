"""Tests für Finanzmodell und Newsletter-Pipeline. Ausführen: python3 -m unittest discover tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "business" / "finanzmodell"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_newsletter  # noqa: E402
import finanzmodell  # noqa: E402

ANNAHMEN = json.loads((ROOT / "business" / "finanzmodell" / "annahmen.json").read_text(encoding="utf-8"))


class FinanzmodellTest(unittest.TestCase):
    def setUp(self):
        self.ergebnis = {n: finanzmodell.simuliere(finanzmodell.szenario_annahmen(ANNAHMEN, n))
                         for n in ANNAHMEN["szenarien"]}

    def test_stufe(self):
        t = [[1, 0], [4, 300], [13, 900]]
        self.assertEqual(finanzmodell.stufe(t, 3), 0)
        self.assertEqual(finanzmodell.stufe(t, 4), 300)
        self.assertEqual(finanzmodell.stufe(t, 40), 900)

    def test_umsatz_summe_konsistent(self):
        for z in self.ergebnis["basis"]:
            teile = z["umsatz_plus"] + z["umsatz_produkte"] + z["umsatz_sponsoring"] + z["umsatz_b2b"]
            self.assertAlmostEqual(z["umsatz_gesamt"], teile, places=6)

    def test_kasse_ist_kumuliertes_ergebnis(self):
        zeilen = self.ergebnis["basis"]
        self.assertAlmostEqual(zeilen[-1]["kasse_kumuliert"], sum(z["ergebnis"] for z in zeilen), places=6)

    def test_szenarien_geordnet(self):
        umsatz = {n: sum(z["umsatz_gesamt"] for z in zeilen) for n, zeilen in self.ergebnis.items()}
        self.assertLess(umsatz["pessimistisch"], umsatz["basis"])
        self.assertLess(umsatz["basis"], umsatz["optimistisch"])

    def test_basis_profitabel(self):
        kpi = finanzmodell.kennzahlen(self.ergebnis["basis"])
        self.assertIsNotNone(kpi["break_even_monat"])
        self.assertGreater(kpi["jahre"][2]["ergebnis"], 0)
        self.assertGreater(kpi["kasse_ende"], 0)

    def test_unit_economics_tragfaehig(self):
        ue = finanzmodell.unit_economics(finanzmodell.szenario_annahmen(ANNAHMEN, "basis"))
        self.assertGreaterEqual(ue["ltv_cac"], 3)


class NewsletterTest(unittest.TestCase):
    BRIEFING = """# Finanz-Rundum-Briefing — Test

## 1. MARKTLAGE HEUTE

- **DAX:** leicht im Plus.

---

## 2. FINANZWISSEN DES TAGES

### Thema: Zinsstrukturkurve — kurz erklärt

Text zur Kurve.

*(Themen-Log: intern.)*

---

## 3. GELD & VERHALTEN

### Thema: Ankereffekt — warum der Kaufpreis nichts zählt

Aufhänger von heute: Viele halten am Einstiegskurs fest.

**Was ist der Ankereffekt?**
- Eine Zahl prägt die Bewertung.

**Gegenstrategie**
- Bewerte neu.

## 4. FINLYRA-RELEVANZ

Gutes Format ("Dein Kaufkurs ist dem Markt völlig egal – warum?") für Reels.
"""

    def test_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "briefings").mkdir()
            (tmp / "briefings" / "2026-01-01.md").write_text(self.BRIEFING, encoding="utf-8")
            orig = build_newsletter.BRIEFINGS_DIR, build_newsletter.OUT_ROOT
            build_newsletter.BRIEFINGS_DIR, build_newsletter.OUT_ROOT = tmp / "briefings", tmp / "newsletter"
            try:
                out = build_newsletter.build("2026-01-01")
            finally:
                build_newsletter.BRIEFINGS_DIR, build_newsletter.OUT_ROOT = orig

            free = (out / "free.md").read_text(encoding="utf-8")
            plus = (out / "plus.md").read_text(encoding="utf-8")
            social = (out / "social.txt").read_text(encoding="utf-8")
            html = (out / "plus.html").read_text(encoding="utf-8")

            self.assertIn("> Dein Kaufkurs ist dem Markt völlig egal – warum?", free)
            self.assertNotIn("Bewerte neu", free)  # Vollanalyse nur in Plus
            self.assertIn("keine Anlageberatung", free)
            self.assertIn("Bewerte neu", plus)
            self.assertIn("DAX", plus)
            self.assertNotIn("Themen-Log", plus)
            self.assertNotIn("Gutes Format", free + plus + social)  # interne Notiz bleibt intern
            self.assertTrue(social.startswith("Dein Kaufkurs ist dem Markt völlig egal"))
            self.assertIn("<strong>DAX:</strong>", html)

    def test_fehlendes_briefing(self):
        with self.assertRaises(FileNotFoundError):
            build_newsletter.build("1900-01-01")


if __name__ == "__main__":
    unittest.main()
