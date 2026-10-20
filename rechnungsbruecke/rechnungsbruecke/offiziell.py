"""Prüfung gegen die offiziellen Regelwerke (XSD + kompilierte Schematron-XSLT).

Die Regeln werden über `regeln.py` eingerichtet und vor der Verwendung gegen ihr Manifest
geprüft. Kompilierte Stylesheets werden pro Prozess zwischengespeichert, damit Stapel- und
Hotfolder-Läufe nicht jede Rechnung neu kompilieren.
"""
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .regeln import Regelwerk, lade

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
    root = etree.fromstring(xml)
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


def pruefe_xsd(xml: bytes) -> list[Befund]:
    from facturx import xml_check_xsd

    if _syntax(xml) != "CII":
        return []
    try:
        xml_check_xsd(xml, flavor="factur-x", level="en16931")
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
    _stylesheet(regelwerke_fuer(xml, werk)[0])  # stellt sicher, dass der Prozessor existiert
    quelle = _SAXON.parse_xml(xml_text=xml.decode("utf-8"))
    befunde = []
    for xsl in regelwerke_fuer(xml, werk):
        svrl = etree.fromstring(_stylesheet(xsl).transform_to_string(xdm_node=quelle).encode("utf-8"))
        for fa in svrl.iterfind(".//svrl:failed-assert", SVRL):
            text = " ".join(fa.findtext("svrl:text", "", SVRL).split())
            befunde.append(Befund(fa.get("id", "?"), fa.get("flag", "fatal"), text, fa.get("location", "")))
    return befunde


def pruefe_offiziell(xml: bytes, regeln: Regelwerk | Path) -> list[Befund]:
    werk = regeln if isinstance(regeln, Regelwerk) else lade(Path(regeln))
    return pruefe_xsd(xml) + pruefe_schematron(xml, werk)
