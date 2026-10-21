"""Sicheres Einlesen fremder XML-Dateien (Eingangsrechnungen, eingebettete ZUGFeRD-XML).

E-Rechnungen (CII, UBL) benötigen nie DOCTYPE- oder ENTITY-Deklarationen. Dateien mit solchen
Deklarationen werden deshalb grundsätzlich abgelehnt (Schutz vor XXE und Entity-Expansion).
Alle weiteren Verarbeiter, insbesondere Saxon, erhalten nur das von lxml geparste und neu
serialisierte XML, damit sie nie selbst externe Ressourcen auflösen.
"""
import re

from lxml import etree

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False,
                          huge_tree=False)
_DEKLARATION = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


class UnsicheresXML(ValueError):
    pass


def parse(xml: bytes) -> etree._Element:
    if _DEKLARATION.search(xml):
        raise UnsicheresXML("Die Datei enthält eine DOCTYPE- oder ENTITY-Deklaration. E-Rechnungen benötigen das "
                            "nie; die Datei wird aus Sicherheitsgründen nicht verarbeitet.")
    try:
        root = etree.fromstring(xml, parser=_PARSER)
    except etree.XMLSyntaxError as e:
        raise UnsicheresXML(f"Kein gültiges XML: {e}") from None
    # Zweite Sicherung, z. B. für UTF-16-kodierte Dateien, die die Byte-Suche oben nicht erfasst
    if root.getroottree().docinfo.doctype or root.getroottree().docinfo.internalDTD is not None:
        raise UnsicheresXML("Die Datei enthält eine DOCTYPE-Deklaration und wird nicht verarbeitet.")
    return root


def bereinigt(xml: bytes) -> bytes:
    """Neu serialisiertes UTF-8-XML ohne DTD; nur dieses wird an Saxon und XSD-Prüfung weitergegeben."""
    return etree.tostring(parse(xml), xml_declaration=True, encoding="UTF-8")
