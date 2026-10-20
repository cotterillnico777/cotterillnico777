"""Prüfung gegen die offiziellen Regelwerke (XSD + kompilierte Schematron-XSLT).

Benötigt die optionalen Pakete `saxonche` und `factur-x` sowie ein Verzeichnis mit
den kompilierten Schematron-Regeln (EN16931-CII-validation.xsl,
XRechnung-CII-validation.xsl, ggf. UBL-Varianten), wie sie in der
KoSIT-Konfiguration für XRechnung bzw. bei CEN veröffentlicht werden.
"""
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

SVRL = {"svrl": "http://purl.oclc.org/dsdl/svrl"}


@dataclass
class Befund:
    regel: str
    schwere: str  # "fatal" oder "warning"
    text: str
    ort: str = ""


def regelwerke_fuer(xml: bytes, regeln: Path) -> list[Path]:
    root = etree.fromstring(xml)
    syntax = "UBL" if root.tag.endswith("}Invoice") or root.tag.endswith("}CreditNote") else "CII"
    namen = [f"EN16931-{syntax}-validation"]
    if b"xeinkauf.de:kosit:xrechnung" in xml:
        namen.append(f"XRechnung-{syntax}-validation")
    dateien, fehlend = [], []
    for name in namen:
        # KoSIT liefert .xsl, CEN (eInvoicing-EN16931) .xslt
        treffer = [regeln / f"{name}{endung}" for endung in (".xsl", ".xslt") if (regeln / f"{name}{endung}").exists()]
        if treffer:
            dateien.append(treffer[0])
        else:
            fehlend.append(f"{regeln / name}.xsl(t)")
    if fehlend:
        raise FileNotFoundError("Regelwerk fehlt: " + ", ".join(fehlend))
    return dateien


def pruefe_xsd(xml: bytes) -> list[Befund]:
    from facturx import xml_check_xsd

    root = etree.fromstring(xml)
    if not root.tag.endswith("}CrossIndustryInvoice"):
        return []
    try:
        xml_check_xsd(xml, flavor="factur-x", level="en16931")
    except Exception as e:  # factur-x wirft für XSD-Fehler eine generische Exception
        return [Befund("XSD", "fatal", str(e))]
    return []


def pruefe_schematron(xml: bytes, regeln: Path) -> list[Befund]:
    from saxonche import PySaxonProcessor

    befunde = []
    with PySaxonProcessor(license=False) as proc:
        quelle = proc.parse_xml(xml_text=xml.decode("utf-8"))
        for xsl in regelwerke_fuer(xml, regeln):
            exe = proc.new_xslt30_processor().compile_stylesheet(stylesheet_file=str(xsl))
            svrl = etree.fromstring(exe.transform_to_string(xdm_node=quelle).encode("utf-8"))
            for fa in svrl.iterfind(".//svrl:failed-assert", SVRL):
                text = " ".join(fa.findtext("svrl:text", "", SVRL).split())
                befunde.append(Befund(fa.get("id", "?"), fa.get("flag", "fatal"), text, fa.get("location", "")))
    return befunde


def pruefe_offiziell(xml: bytes, regeln: Path) -> list[Befund]:
    return pruefe_xsd(xml) + pruefe_schematron(xml, Path(regeln))
