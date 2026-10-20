"""Festgeschriebene Versionen der unterstützten Standards.

Eine neue XRechnung- oder ZUGFeRD-Version wird bewusst übernommen: Konstanten hier ändern,
Prüfregeln neu einrichten, alle Tests gegen die offiziellen Regeln laufen lassen.
"""
XRECHNUNG_VERSION = "3.0"
XRECHNUNG_KENNUNG = f"urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_{XRECHNUNG_VERSION}"
EN16931_KENNUNG = "urn:cen.eu:en16931:2017"
PEPPOL_PROZESS = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
ZUGFERD_PROFIL = "EN 16931"          # ZUGFeRD 2.x / Factur-X 1.x, Profil EN 16931 (COMFORT)
PDFA = "PDF/A-3b"
