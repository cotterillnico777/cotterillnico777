"""Prüfung gegen die offiziellen Regelwerke (XSD + kompilierte Schematron-XSLT).

Die Regeln werden über `regeln.py` eingerichtet und vor der Verwendung gegen ihr Manifest
geprüft. Kompilierte Stylesheets werden pro Prozess zwischengespeichert, damit Stapel- und
Hotfolder-Läufe nicht jede Rechnung neu kompilieren.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .regeln import Regelwerk, lade
from .xmlsicher import bereinigt, parse

SVRL = {"svrl": "http://purl.oclc.org/dsdl/svrl"}
_SAXON = None
_KOMPILIERT: dict[tuple[str, float], object] = {}


@dataclass
class Befund:
    regel: str
    schwere: str  # "fatal" oder "warning"
    text: str
    ort: str = ""


def _syntax(xml: bytes) -> str:
    root = parse(xml)
    return "UBL" if root.tag.endswith("}Invoice") or root.tag.endswith("}CreditNote") else "CII"


def regelwerke_fuer(xml: bytes, werk: Regelwerk) -> list[Path]:
    syntax = _syntax(xml)
    namen = [f"EN16931-{syntax}-validation"]
    if b"xeinkauf.de:kosit:xrechnung" in xml:
        namen.append(f"XRechnung-{syntax}-validation")
    dateien, fehlend = [], []
    for name in namen:
        pfad = werk.datei(name)
        if pfad:
            dateien.append(pfad)
        else:
            fehlend.append(f"{werk.ordner / name}.xsl")
    if fehlend:
        raise FileNotFoundError("Regelwerk fehlt: " + ", ".join(fehlend))
    return dateien


KEINE_E_RECHNUNG = {"minimum": "MINIMUM", "basicwl": "BASIC WL"}


def pruefe_xsd(xml: bytes, eingang: bool = False) -> list[Befund]:
    """XSD-Prüfung. Ausgangsrechnungen sind immer CII im Profil EN 16931; bei Eingangsrechnungen
    werden UBL und das ZUGFeRD-Profil erkannt (BASIC, EN 16931, EXTENDED)."""
    from facturx import get_level, xml_check_xsd

    xml = bereinigt(xml)
    root = parse(xml)
    if _syntax(xml) == "UBL":
        if not eingang:
            return []
        flavor = "ubl-2.1-creditnote" if root.tag.endswith("}CreditNote") else "ubl-2.1-invoice"
        level = "autodetect"
    else:
        flavor, level = "factur-x", "en16931"
        if eingang:
            try:
                level = get_level(root, flavor="factur-x")
            except ValueError:
                level = "en16931"
            if level in KEINE_E_RECHNUNG:
                return [Befund("PROFIL", "fatal", f"Das ZUGFeRD-Profil {KEINE_E_RECHNUNG[level]} enthält nicht alle "
                               f"Pflichtangaben und gilt nicht als E-Rechnung. Bitte beim Lieferanten eine "
                               f"Rechnung im Profil EN 16931 (COMFORT), EXTENDED oder als XRechnung anfordern.")]
    try:
        xml_check_xsd(xml, flavor=flavor, level=level)
    except Exception as e:  # factur-x wirft für XSD-Fehler eine generische Exception
        return [Befund("XSD", "fatal", str(e))]
    return []


def _stylesheet(pfad: Path):
    global _SAXON
    from saxonche import PySaxonProcessor

    if _SAXON is None:
        _SAXON = PySaxonProcessor(license=False)
    schluessel = (str(pfad), pfad.stat().st_mtime)
    if schluessel not in _KOMPILIERT:
        _KOMPILIERT[schluessel] = _SAXON.new_xslt30_processor().compile_stylesheet(stylesheet_file=str(pfad))
    return _KOMPILIERT[schluessel]


def pruefe_schematron(xml: bytes, werk: Regelwerk) -> list[Befund]:
    xml = bereinigt(xml)  # Saxon würde externe Entities sonst selbst auflösen
    _stylesheet(regelwerke_fuer(xml, werk)[0])  # stellt sicher, dass der Prozessor existiert
    quelle = _SAXON.parse_xml(xml_text=xml.decode("utf-8"))
    befunde = []
    for xsl in regelwerke_fuer(xml, werk):
        svrl = etree.fromstring(_stylesheet(xsl).transform_to_string(xdm_node=quelle).encode("utf-8"))
        for fa in svrl.iterfind(".//svrl:failed-assert", SVRL):
            regel = fa.get("id", "?")
            text = " ".join(fa.findtext("svrl:text", "", SVRL).split())
            text = re.sub(rf"^\[{re.escape(regel)}\]-?\s*", "", text)  # Regelkennung steht schon in `regel`
            befunde.append(Befund(regel, fa.get("flag", "fatal"), text, fa.get("location", "")))
    return befunde


def pruefe_offiziell(xml: bytes, regeln: Regelwerk | Path, eingang: bool = False) -> list[Befund]:
    werk = regeln if isinstance(regeln, Regelwerk) else lade(Path(regeln))
    xsd = pruefe_xsd(xml, eingang)
    if any(b.regel == "PROFIL" for b in xsd):
        return xsd
    return xsd + pruefe_schematron(xml, werk)
