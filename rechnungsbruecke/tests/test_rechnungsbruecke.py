"""Tests der Rechnungsbrücke. Ausführen im Ordner rechnungsbruecke/:

    python3 -m unittest discover tests

Mit RB_REGELN=<Ordner mit EN16931-/XRechnung-Schematron-XSLT> laufen zusätzlich die
Prüfungen gegen die offiziellen Regelwerke (benötigt saxonche).
"""
import base64
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from lxml import etree

from rechnungsbruecke import lizenz as lizenzmodul
from rechnungsbruecke.cii import erzeuge_cii
from rechnungsbruecke.cli import main
from rechnungsbruecke.csv_import import ImportFehler, Stammdaten, dezimal, importiere
from rechnungsbruecke.leser import LeseFehler, lies, lies_datei
from rechnungsbruecke.lizenz import FREE, Lizenz, LizenzFehler, Nutzung, pruefe_lizenzdatei
from rechnungsbruecke.modell import (KLEINUNTERNEHMER_GRUND, Anschrift, Bankverbindung, Partei, Position,
                                     Rechnung)
from rechnungsbruecke.regeln import RegelFehler, einrichten, lade
from rechnungsbruecke.verarbeitung import hotfolder_durchlauf, konvertiere
from rechnungsbruecke.vorpruefung import iban_gueltig, leitweg_id_gueltig, pruefe

HIER = Path(__file__).resolve().parent
BEISPIELE = HIER.parent / "rechnungsbruecke" / "beispiele"
REGELN = Path(os.environ["RB_REGELN"]) if os.environ.get("RB_REGELN") else None
BUSINESS = Lizenz("Test GmbH", "business", date(2099, 12, 31))


def rechnung(**aenderungen) -> Rechnung:
    v = Partei("Muster GmbH", Anschrift("Industriestr. 5", "70173", "Stuttgart"), ust_id="DE123456789",
               email="rechnung@muster.de", kontakt_name="Erika Muster", kontakt_telefon="+49 711 1",
               kontakt_email="buchhaltung@muster.de")
    k = Partei("Kunde AG", Anschrift("Hauptstr. 1", "10115", "Berlin"), ust_id="DE987654321", email="eingang@kunde.de")
    r = Rechnung("R-1", date(2026, 10, 20), v, k,
                 [Position("Montage", D("7.5"), D("68.00"), D("19"), "HUR"),
                  Position("Fachbuch", D("3"), D("0.333"), D("7"))],
                 bank=Bankverbindung("DE02120300000000202051", "BYLADEM1001"),
                 leistungsdatum=date(2026, 10, 15), faelligkeit=date(2026, 11, 3),
                 zahlungsbedingungen="14 Tage netto", kaeufer_referenz="K-1")
    for k_, v_ in aenderungen.items():
        setattr(r, k_, v_)
    return r


class MitDatenverzeichnis(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = mock.patch.dict(os.environ, {"RB_DATENVERZEICHNIS": str(self.tmp / "daten")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)


class ModellTest(unittest.TestCase):
    def test_summen_und_rundung(self):
        r = rechnung()
        self.assertEqual(r.positionen[1].netto, D("1.00"))  # 3 × 0,333 = 0,999 → 1,00
        self.assertEqual(r.netto, D("511.00"))
        steuern = {(s.kategorie, s.satz): s.steuer for s in r.steuern}
        self.assertEqual(steuern[("S", D("19"))], D("96.90"))
        self.assertEqual(steuern[("S", D("7"))], D("0.07"))
        self.assertEqual(r.brutto, D("607.97"))

    def test_vorauszahlung(self):
        r = rechnung(vorauszahlung=D("100"))
        self.assertEqual(r.zahlbetrag, r.brutto - D("100.00"))

    def test_befreiung_mit_grund(self):
        r = rechnung(positionen=[Position("X", D("1"), D("50"), D("0"), kategorie="E")],
                     befreiungsgruende={"E": KLEINUNTERNEHMER_GRUND})
        self.assertEqual(r.steuern[0].befreiungsgrund, KLEINUNTERNEHMER_GRUND)
        self.assertEqual(r.steuer, D("0.00"))


class CiiTest(unittest.TestCase):
    def test_xsd_gueltig(self):
        from facturx import xml_check_xsd

        for profil in ("xrechnung", "zugferd"):
            self.assertTrue(xml_check_xsd(erzeuge_cii(rechnung(), profil), flavor="factur-x", level="en16931"))

    def test_profilkennung(self):
        self.assertIn(b"kosit:xrechnung_3.0", erzeuge_cii(rechnung(), "xrechnung"))
        self.assertIn(b"<ram:ID>urn:cen.eu:en16931:2017</ram:ID>", erzeuge_cii(rechnung(), "zugferd"))
        with self.assertRaises(ValueError):
            erzeuge_cii(rechnung(), "unbekannt")

    def test_lieferland_bei_innergemeinschaftlicher_lieferung(self):
        r = rechnung(positionen=[Position("X", D("1"), D("100"), D("0"), kategorie="K")])
        r.kaeufer = Partei("Client SARL", Anschrift("1 Rue", "75002", "Paris", "FR"), ust_id="FR40303265045",
                           email="f@client.fr")
        self.assertIn(b"ShipToTradeParty", erzeuge_cii(r))


@unittest.skipUnless(REGELN, "RB_REGELN nicht gesetzt: offizielle Regelprüfung übersprungen")
class OffizielleRegelnTest(MitDatenverzeichnis):
    def fatal(self, xml):
        from rechnungsbruecke.offiziell import pruefe_offiziell

        return [b.regel for b in pruefe_offiziell(xml, REGELN) if b.schwere == "fatal"]

    def test_beispiele_fehlerfrei(self):
        stamm = Stammdaten.laden(BEISPIELE / "stammdaten.json")
        mapping = json.loads((BEISPIELE / "mapping_altsystem.json").read_text(encoding="utf-8"))
        rechnungen = importiere(BEISPIELE / "rechnungen.csv", stamm) + importiere(
            BEISPIELE / "export_altsystem.csv", stamm, mapping)
        self.assertEqual(len(rechnungen), 4)
        for r in rechnungen:
            for profil in ("xrechnung", "zugferd"):
                with self.subTest(rechnung=r.nummer, profil=profil):
                    self.assertEqual(self.fatal(erzeuge_cii(r, profil)), [])

    def test_steuerfaelle_fehlerfrei(self):
        faelle = {
            "gemischt": rechnung(),
            "kleinunternehmer": rechnung(positionen=[Position("X", D("1"), D("50"), D("0"), kategorie="E")],
                                         befreiungsgruende={"E": KLEINUNTERNEHMER_GRUND}),
            "reverse_charge": rechnung(positionen=[Position("X", D("2"), D("80"), D("0"), kategorie="AE")]),
            "gutschrift": rechnung(typ="381"),
            "zeitraum": rechnung(leistungsdatum=None, leistungszeitraum=(date(2026, 9, 1), date(2026, 9, 30))),
            "vorauszahlung": rechnung(vorauszahlung=D("100")),
        }
        for name, r in faelle.items():
            with self.subTest(name):
                self.assertEqual(pruefe(r), [])
                self.assertEqual(self.fatal(erzeuge_cii(r)), [])

    def test_regeln_erkennen_fehler(self):
        xml = erzeuge_cii(rechnung())
        self.assertIn("BR-CO-15", self.fatal(xml.replace(b"<ram:GrandTotalAmount>607.97",
                                                         b"<ram:GrandTotalAmount>608.97")))
        self.assertIn("BR-DE-15", self.fatal(erzeuge_cii(rechnung(kaeufer_referenz=""))))

    def test_ubl_beispiel_fehlerfrei(self):
        self.assertEqual(self.fatal((HIER / "daten" / "ubl_eingang.xml").read_bytes()), [])

    def test_konvertieren_mit_regeln(self):
        erg = konvertiere(BEISPIELE / "rechnungen.csv", Stammdaten.laden(BEISPIELE / "stammdaten.json"),
                          self.tmp / "out", FREE, format="beide", regeln=lade(REGELN))
        self.assertTrue(erg.ok, erg.fehler)
        self.assertEqual(len(erg.erzeugt), 6)  # je Rechnung XML und PDF; auch das ZUGFeRD-XML ist geprüft
        self.assertEqual(len(erg.berichte), 3)
        bericht = json.loads(erg.berichte[0].read_text(encoding="utf-8"))
        self.assertEqual(bericht["offizielle_pruefung"], "bestanden")
        self.assertEqual(bericht["regeln"]["xrechnung_version"], "3.0")


class CsvImportTest(unittest.TestCase):
    def setUp(self):
        self.stamm = Stammdaten.laden(BEISPIELE / "stammdaten.json")

    def test_zahlenformate(self):
        self.assertEqual(dezimal("1.234,56", "x", 1), D("1234.56"))
        self.assertEqual(dezimal("1,234.56", "x", 1), D("1234.56"))
        self.assertEqual(dezimal("68,00 €", "x", 1), D("68.00"))
        self.assertEqual(dezimal("1.250", "x", 1, "de"), D("1250"))
        self.assertEqual(dezimal("1.250", "x", 1, "en"), D("1.250"))
        with self.assertRaisesRegex(ImportFehler, "mehrdeutig"):
            dezimal("1.250", "x", 1)

    def test_beispiel_gruppiert_positionen(self):
        rechnungen = importiere(BEISPIELE / "rechnungen.csv", self.stamm)
        self.assertEqual([r.nummer for r in rechnungen], ["RE-2026-1001", "RE-2026-1002", "RE-2026-1003"])
        r1 = rechnungen[0]
        self.assertEqual(len(r1.positionen), 3)
        self.assertEqual(r1.positionen[0].einheit, "HUR")
        self.assertEqual(r1.netto, D("1569.00"))
        self.assertEqual(r1.faelligkeit, date(2026, 11, 3))
        self.assertEqual(rechnungen[1].positionen[0].kategorie, "K")
        self.assertEqual(rechnungen[2].kaeufer_referenz, "991-33333TEST-33")

    def test_altsystem_cp1252_mit_mapping(self):
        mapping = json.loads((BEISPIELE / "mapping_altsystem.json").read_text(encoding="utf-8"))
        (r,) = importiere(BEISPIELE / "export_altsystem.csv", self.stamm, mapping)
        self.assertEqual(r.kaeufer.name, "Müller & Söhne GmbH")
        self.assertEqual(r.positionen[1].menge, D("1250"))
        self.assertEqual(r.brutto, D("3111.26"))

    def test_altsystem_ohne_zahlenformat_wird_abgelehnt(self):
        mapping = json.loads((BEISPIELE / "mapping_altsystem.json").read_text(encoding="utf-8"))
        del mapping["_zahlenformat"]
        with self.assertRaisesRegex(ImportFehler, "1.250.*mehrdeutig"):
            importiere(BEISPIELE / "export_altsystem.csv", self.stamm, mapping)

    def test_fehlende_spalten(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("rechnungsnummer;kunde_name\nR1;X\n")
        try:
            with self.assertRaisesRegex(ImportFehler, "Pflichtspalten fehlen: rechnungsdatum"):
                importiere(Path(f.name), self.stamm)
        finally:
            os.unlink(f.name)

    def test_kleinunternehmer(self):
        self.stamm.kleinunternehmer = True
        r = importiere(BEISPIELE / "rechnungen.csv", self.stamm)[0]
        self.assertEqual({p.kategorie for p in r.positionen}, {"E"})
        self.assertEqual(r.steuer, D("0.00"))
        self.assertEqual(r.steuern[0].befreiungsgrund, KLEINUNTERNEHMER_GRUND)


class VorpruefungTest(unittest.TestCase):
    def texte(self, r):
        return " ".join(m.text for m in pruefe(r) if m.schwere == "fehler")

    def test_gueltige_rechnung(self):
        self.assertEqual(pruefe(rechnung()), [])

    def test_iban(self):
        self.assertTrue(iban_gueltig("DE02 1203 0000 0000 2020 51"))
        self.assertFalse(iban_gueltig("DE02120300000000202052"))
        self.assertIn("IBAN", self.texte(rechnung(bank=Bankverbindung("DE02120300000000202052"))))

    def test_typische_fehler(self):
        r = rechnung()
        r.kaeufer.email = ""
        r.verkaeufer.kontakt_telefon = ""
        t = self.texte(r)
        self.assertIn("Käufer: elektronische Adresse", t)
        self.assertIn("Ansprechpartner", t)

    def test_steuerlogik(self):
        self.assertIn("Kategorie S erfordert", self.texte(
            rechnung(positionen=[Position("X", D("1"), D("1"), D("0"), kategorie="S")])))
        r = rechnung(positionen=[Position("X", D("1"), D("1"), D("0"), kategorie="AE")])
        r.kaeufer.ust_id = ""
        self.assertIn("USt-IdNr. des Käufers", self.texte(r))
        self.assertIn("nicht unterstützt", self.texte(
            rechnung(positionen=[Position("X", D("1"), D("1"), D("0"), kategorie="O")])))


class LeserTest(MitDatenverzeichnis):
    def test_cii_rundreise(self):
        original = rechnung()
        r = lies(erzeuge_cii(original))
        self.assertEqual((r.nummer, r.brutto, r.steuer), ("R-1", original.brutto, original.steuer))
        self.assertEqual(len(r.zeilen), 2)
        self.assertEqual(r.plausibilitaet(), [])

    def test_ubl(self):
        r = lies_datei(HIER / "daten" / "ubl_eingang.xml")
        self.assertEqual((r.syntax, r.verkaeufer, r.brutto), ("UBL", "Stahlhandel Nord GmbH", D("893.69")))
        self.assertEqual(r.zeilen[0].einheit, "KGM")
        self.assertEqual(r.faelligkeit, "11.11.2026")
        self.assertEqual(r.plausibilitaet(), [])

    def test_rechenfehler_werden_erkannt(self):
        xml = erzeuge_cii(rechnung()).replace(b"<ram:GrandTotalAmount>607.97", b"<ram:GrandTotalAmount>617.97")
        self.assertTrue(any("Brutto" in p for p in lies(xml).plausibilitaet()))

    def test_ungueltige_eingaben(self):
        with self.assertRaises(LeseFehler):
            lies(b"kein xml")
        with self.assertRaises(LeseFehler):
            lies(b"<foo/>")

    def test_zugferd_pdf(self):
        from pypdf import PdfReader

        from rechnungsbruecke.pdf import erzeuge_zugferd

        pdf = erzeuge_zugferd(rechnung())
        pfad = self.tmp / "r.pdf"
        pfad.write_bytes(pdf)
        self.assertEqual(lies_datei(pfad).brutto, D("607.97"))
        reader = PdfReader(io.BytesIO(pdf))
        root = reader.trailer["/Root"]
        self.assertIn("/OutputIntents", root)
        self.assertEqual(list(reader.attachments), ["factur-x.xml"])
        self.assertIn(b"<pdfaid:part>3</pdfaid:part>", root["/Metadata"].get_object().get_data())
        for seite in reader.pages:
            for schrift in seite["/Resources"]["/Font"].values():
                s = schrift.get_object()
                desc = (s["/DescendantFonts"][0].get_object() if "/DescendantFonts" in s else s)["/FontDescriptor"]
                self.assertIn("/FontFile2", desc.get_object(), f"{s['/BaseFont']} nicht eingebettet (PDF/A)")


class LizenzTest(MitDatenverzeichnis):
    def setUp(self):
        super().setUp()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        self.privat = Ed25519PrivateKey.generate()
        roh = self.privat.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.schluessel = mock.patch.object(lizenzmodul, "OEFFENTLICHER_SCHLUESSEL", base64.b64encode(roh).decode())
        self.schluessel.start()

    def tearDown(self):
        self.schluessel.stop()
        super().tearDown()

    def lizenzdatei(self, tarif="business", bis="2099-12-31", manipulation=None):
        import sys

        sys.path.insert(0, str(HIER.parent / "werkzeuge"))
        from lizenz_ausstellen import ausstellen

        d = ausstellen(self.privat, "Test GmbH", tarif, bis)
        d.update(manipulation or {})
        pfad = self.tmp / "lizenz.json"
        pfad.write_text(json.dumps(d), encoding="utf-8")
        return pfad

    def test_gueltige_lizenz(self):
        liz = pruefe_lizenzdatei(self.lizenzdatei())
        self.assertEqual((liz.tarif, liz.limit, liz.hotfolder), ("business", 3000, True))

    def test_manipulierte_lizenz(self):
        with self.assertRaisesRegex(LizenzFehler, "Signatur"):
            pruefe_lizenzdatei(self.lizenzdatei(tarif="starter", manipulation={"tarif": "unternehmen"}))

    def test_abgelaufene_lizenz(self):
        with self.assertRaisesRegex(LizenzFehler, "abgelaufen"):
            pruefe_lizenzdatei(self.lizenzdatei(bis="2026-01-31"), heute=date(2026, 10, 20))

    def test_kontingent_free(self):
        n = Nutzung(FREE)
        n.buchen(25)
        with self.assertRaisesRegex(LizenzFehler, "Monatskontingent"):
            Nutzung(FREE).buchen(1)

    def test_kontingent_stoppt_konvertierung(self):
        Nutzung(FREE).buchen(24)
        erg = konvertiere(BEISPIELE / "rechnungen.csv", Stammdaten.laden(BEISPIELE / "stammdaten.json"),
                          self.tmp / "out", FREE, ohne_offizielle_pruefung=True)
        self.assertEqual(len(erg.erzeugt), 1)
        self.assertTrue(any("Monatskontingent" in f for f in erg.fehler))

    def test_hotfolder_nicht_im_free_tarif(self):
        with self.assertRaisesRegex(LizenzFehler, "Hotfolder"):
            hotfolder_durchlauf(self.tmp, self.tmp / "ziel", None, FREE)


class HotfolderTest(MitDatenverzeichnis):
    def test_ausgang_und_eingang(self):
        eingang = self.tmp / "hotfolder"
        eingang.mkdir()
        shutil.copy(BEISPIELE / "rechnungen.csv", eingang)
        shutil.copy(HIER / "daten" / "ubl_eingang.xml", eingang)
        (eingang / "kaputt.xml").write_text("<foo/>")
        (eingang / "notiz.txt").write_text("ignorieren")
        alt = time.time() - 60
        for f in eingang.iterdir():
            os.utime(f, (alt, alt))
        ergebnisse = hotfolder_durchlauf(eingang, self.tmp / "ziel", Stammdaten.laden(BEISPIELE / "stammdaten.json"),
                                         BUSINESS, format="beide", ohne_offizielle_pruefung=True)
        status = {d.name: e.ok for d, e in ergebnisse}
        self.assertEqual(status, {"rechnungen.csv": True, "ubl_eingang.xml": True, "kaputt.xml": False})
        self.assertEqual(len(list((self.tmp / "ziel" / "ausgang").glob("*.pdf"))), 3)
        self.assertTrue((self.tmp / "ziel" / "eingang" / "buchungsliste.csv").exists())
        self.assertEqual(len(list((eingang / "verarbeitet").iterdir())), 2)
        self.assertTrue(list((eingang / "fehler").glob("*.log")))
        self.assertTrue((eingang / "notiz.txt").exists())

    def test_junge_dateien_warten(self):
        eingang = self.tmp / "hotfolder"
        eingang.mkdir()
        shutil.copy(BEISPIELE / "rechnungen.csv", eingang)
        self.assertEqual(hotfolder_durchlauf(eingang, self.tmp / "ziel", None, BUSINESS, mindestalter_s=3600), [])


class KaeuferreferenzTest(MitDatenverzeichnis):
    def test_keine_selbst_vergebene_referenz(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("rechnungsnummer;rechnungsdatum;kunde_name;kunde_strasse;kunde_plz;kunde_ort;kunde_email;"
                    "bestellnummer;bezeichnung;menge;einzelpreis\n"
                    "R-77;20.10.2026;Kunde AG;Weg 1;10115;Berlin;e@k.de;PO-1;Teil;1;10,00\n")
        try:
            (r,) = importiere(Path(f.name), Stammdaten.laden(BEISPIELE / "stammdaten.json"))
        finally:
            os.unlink(f.name)
        self.assertEqual(r.kaeufer_referenz, "")  # weder Rechnungs- noch Bestellnummer
        fehler = " ".join(m.text for m in pruefe(r, "xrechnung") if m.schwere == "fehler")
        self.assertIn("Käuferreferenz fehlt", fehler)
        self.assertEqual([m for m in pruefe(r, "zugferd") if m.schwere == "fehler"], [])
        self.assertNotIn(b"BuyerReference", erzeuge_cii(r, "zugferd"))

    def test_leitweg_id_pruefziffer(self):
        self.assertTrue(leitweg_id_gueltig("991-33333TEST-33"))
        self.assertTrue(leitweg_id_gueltig("04011000-1234512345-06"))
        self.assertFalse(leitweg_id_gueltig("991-12345-67"))
        hinweise = [m.text for m in pruefe(rechnung(kaeufer_referenz="991-12345-67")) if m.schwere == "hinweis"]
        self.assertTrue(any("Prüfziffer" in h for h in hinweise))
        self.assertEqual(pruefe(rechnung(kaeufer_referenz="Bestellung 4711")), [])


class RegelnTest(MitDatenverzeichnis):
    def regelpaket(self, version="3.0", mit_en=True) -> Path:
        quelle = self.tmp / "kosit" / "resources" / "xrechnung" / version / "xsl"
        quelle.mkdir(parents=True)
        (quelle / "XRechnung-CII-validation.xsl").write_text(
            f'<x><xsl:variable name="XR-MAJOR-MINOR-VERSION" select="\'{version}\'"/></x>')
        if mit_en:
            (quelle.parent / "EN16931-CII-validation.xslt").write_text("<x>en16931</x>")
        paket = self.tmp / "kosit.zip"
        shutil.make_archive(str(paket.with_suffix("")), "zip", self.tmp / "kosit")
        return paket

    def test_einrichten_mit_manifest(self):
        werk = einrichten(self.regelpaket())
        self.assertEqual(werk.manifest["xrechnung_version"], "3.0")
        self.assertEqual(set(werk.manifest["dateien"]), {"XRechnung-CII-validation.xsl", "EN16931-CII-validation.xsl"})
        self.assertEqual(lade(werk.ordner).manifest["quelle"], "kosit.zip")

    def test_veraenderte_regeln_werden_erkannt(self):
        werk = einrichten(self.regelpaket())
        (werk.ordner / "EN16931-CII-validation.xsl").write_text("<x>manipuliert</x>")
        with self.assertRaisesRegex(RegelFehler, "verändert"):
            lade(werk.ordner)

    def test_falsche_version_abgelehnt(self):
        with self.assertRaisesRegex(RegelFehler, "XRechnung 2.3"):
            einrichten(self.regelpaket(version="2.3"))

    def test_unvollstaendig_abgelehnt(self):
        with self.assertRaisesRegex(RegelFehler, "EN16931-CII-validation"):
            einrichten(self.regelpaket(mit_en=False))

    def test_ohne_regeln_wird_nichts_geschrieben(self):
        erg = konvertiere(BEISPIELE / "rechnungen.csv", Stammdaten.laden(BEISPIELE / "stammdaten.json"),
                          self.tmp / "out", FREE)
        self.assertFalse(erg.ok)
        self.assertIn("regeln-einrichten", erg.fehler[0])
        self.assertFalse((self.tmp / "out").exists())


class OberflaecheTest(MitDatenverzeichnis):
    def setUp(self):
        super().setUp()
        import threading

        from rechnungsbruecke.oberflaeche import erstelle_server

        self.server, self.token = erstelle_server(self.tmp / "arbeit", port=0, ohne_offizielle_pruefung=True)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def anfrage(self, pfad, daten=None, token=True, host=None):
        import urllib.error
        import urllib.request

        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{pfad}", data=daten,
                                     method="POST" if daten is not None else "GET")
        if token:
            req.add_header("X-RB-Token", self.token)
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req) as antwort:
                return antwort.status, antwort.read(), antwort.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers.get("Content-Type", "")

    def json(self, pfad, daten=None):
        status, inhalt, _ = self.anfrage(pfad, daten)
        return status, json.loads(inhalt)

    def test_sicherheit(self):
        self.assertEqual(self.anfrage("/api/status", token=False)[0], 403)
        self.assertEqual(self.anfrage("/api/status", host="evil.example:80")[0], 403)
        status, seite, typ = self.anfrage("/", token=False)
        self.assertEqual(status, 200)
        self.assertIn(self.token.encode(), seite)
        (self.tmp / "geheim.txt").write_text("x")
        for pfad in ("../geheim.txt", "../../etc/passwd", "stammdaten.json"):
            self.assertEqual(self.anfrage(f"/api/datei?pfad={pfad}")[0], 404, pfad)

    def test_ablauf_erstellen_und_lesen(self):
        status, s = self.json("/api/status")
        self.assertFalse(s["stammdaten_vorhanden"])
        csv = (BEISPIELE / "rechnungen.csv").read_bytes()
        self.assertEqual(self.anfrage("/api/pruefen?format=xrechnung&name=x.csv", csv)[0], 409)  # Firmendaten fehlen

        stamm = (BEISPIELE / "stammdaten.json").read_bytes()
        self.assertEqual(self.json("/api/stammdaten", stamm)[0], 200)
        kaputt = json.dumps({"verkaeufer": {"name": "X"}}).encode()
        self.assertEqual(self.anfrage("/api/stammdaten", kaputt)[0], 422)

        status, d = self.json("/api/pruefen?format=beide&name=export.csv", csv)
        self.assertEqual(status, 200)
        self.assertEqual([r["ok"] for r in d["rechnungen"]], [True, True, True])
        self.assertEqual(d["dateien"], [])
        self.assertEqual(Nutzung(FREE).verbraucht, 0)  # Prüfen verbraucht kein Kontingent

        status, d = self.json("/api/erzeugen?format=beide&name=export.csv", csv)
        self.assertTrue(d["ok"], d)
        self.assertEqual(len([x for x in d["dateien"] if x.endswith((".xml", ".pdf"))]), 6)
        status, inhalt, typ = self.anfrage("/api/datei?pfad=" + d["dateien"][0])
        self.assertEqual(status, 200)
        status, inhalt, typ = self.anfrage("/api/zip", json.dumps({"dateien": d["dateien"]}).encode())
        self.assertEqual(typ, "application/zip")

        ubl = (HIER / "daten" / "ubl_eingang.xml").read_bytes()
        status, d = self.json("/api/lesen?buchen=1&name=ubl.xml", ubl)
        self.assertEqual((d["nummer"], d["probleme"], d["gebucht"]), ("LF-778", [], True))
        self.assertEqual(self.anfrage("/api/datei?pfad=gelesen/buchungsliste.csv")[0], 200)
        self.assertEqual(self.anfrage("/api/lesen?name=x.xml", b"<foo/>")[0], 422)

    def test_mapping(self):
        mapping = (BEISPIELE / "mapping_altsystem.json").read_bytes()
        self.assertEqual(self.json("/api/mapping", mapping)[0], 200)
        self.assertEqual(self.json("/api/mapping")[1]["_zahlenformat"], "de")
        self.assertEqual(self.anfrage("/api/mapping", b"[1,2]")[0], 400)


class CliTest(MitDatenverzeichnis):
    def lauf(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main([str(a) for a in args])
        return code, out.getvalue()

    def test_konvertieren_und_pruefen(self):
        code, out = self.lauf("konvertieren", BEISPIELE / "rechnungen.csv", "--stammdaten",
                              BEISPIELE / "stammdaten.json", "--ziel", self.tmp / "out", "--ohne-offizielle-pruefung")
        self.assertEqual(code, 0, out)
        self.assertIn("3 Rechnung(en) erzeugt, 0 Fehler", out)
        code, out = self.lauf("pruefen", self.tmp / "out" / "RE-2026-1001.xml")
        self.assertEqual(code, 0, out)
        code, out = self.lauf("lizenz")
        self.assertIn("Diesen Monat erzeugt: 3 von 25", out)

    def test_beispiel(self):
        code, _ = self.lauf("beispiel", self.tmp / "bsp")
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "bsp" / "stammdaten.json").exists())

    def test_xml_ist_wohlgeformt(self):
        self.lauf("konvertieren", BEISPIELE / "rechnungen.csv", "--stammdaten", BEISPIELE / "stammdaten.json",
                  "--ziel", self.tmp / "out", "--ohne-offizielle-pruefung")
        for f in (self.tmp / "out").glob("*.xml"):
            etree.parse(str(f))


if __name__ == "__main__":
    unittest.main()
