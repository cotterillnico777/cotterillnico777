"""Liest eingehende E-Rechnungen (XRechnung/ZUGFeRD als CII oder UBL, auch als PDF)."""
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from lxml import etree

from .modell import runden

CII = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}
UBL = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cn": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


class LeseFehler(ValueError):
    pass


@dataclass
class Zeile:
    bezeichnung: str
    menge: Decimal
    einheit: str
    einzelpreis: Decimal
    netto: Decimal
    kategorie: str
    satz: Decimal


@dataclass
class Steuerzeile:
    kategorie: str
    satz: Decimal
    basis: Decimal
    steuer: Decimal
    grund: str = ""


@dataclass
class Eingangsrechnung:
    syntax: str
    profil: str
    nummer: str
    datum: str
    typ: str
    waehrung: str
    verkaeufer: str
    verkaeufer_anschrift: str
    verkaeufer_ust_id: str
    verkaeufer_email: str
    kaeufer: str
    kaeufer_referenz: str
    faelligkeit: str
    zahlungsbedingungen: str
    iban: str
    bic: str
    netto: Decimal
    steuer: Decimal
    brutto: Decimal
    zahlbetrag: Decimal
    zeilen: list[Zeile] = field(default_factory=list)
    steuern: list[Steuerzeile] = field(default_factory=list)
    bemerkungen: list[str] = field(default_factory=list)

    def plausibilitaet(self) -> list[str]:
        """Rechnet die Summen nach und meldet Abweichungen."""
        probleme = []
        summe = sum((z.netto for z in self.zeilen), Decimal("0"))
        if self.zeilen and runden(summe) != runden(self.netto):
            probleme.append(f"Summe der Positionen ({summe:.2f}) weicht vom Nettobetrag ({self.netto:.2f}) ab")
        st = sum((s.steuer for s in self.steuern), Decimal("0"))
        if runden(st) != runden(self.steuer):
            probleme.append(f"Summe der Steuerbeträge ({st:.2f}) weicht von der Gesamtsteuer ({self.steuer:.2f}) ab")
        for s in self.steuern:
            erwartet = runden(s.basis * s.satz / 100)
            if abs(erwartet - s.steuer) > Decimal("0.01"):
                probleme.append(f"Steuer {s.satz} %: {s.steuer:.2f} angegeben, {erwartet:.2f} erwartet")
        if runden(self.netto + self.steuer) != runden(self.brutto):
            probleme.append(f"Netto + Steuer ({self.netto + self.steuer:.2f}) ≠ Brutto ({self.brutto:.2f})")
        return probleme


def _d(text) -> Decimal:
    return Decimal(text.strip()) if text and text.strip() else Decimal("0")


def _datum(text: str) -> str:
    t = (text or "").strip()
    if len(t) == 8 and t.isdigit():
        return f"{t[6:8]}.{t[4:6]}.{t[0:4]}"
    if len(t) == 10 and t[4] == "-":
        return f"{t[8:10]}.{t[5:7]}.{t[0:4]}"
    return t


def _lies_cii(root) -> Eingangsrechnung:
    def x(path, ctx=root):
        r = ctx.xpath(path, namespaces=CII)
        return r[0].strip() if r and isinstance(r[0], str) else (r[0].text or "").strip() if r else ""

    tx = "rsm:SupplyChainTradeTransaction/"
    agr = tx + "ram:ApplicableHeaderTradeAgreement/"
    st = tx + "ram:ApplicableHeaderTradeSettlement/"
    sell = agr + "ram:SellerTradeParty/"
    summen = st + "ram:SpecifiedTradeSettlementHeaderMonetarySummation/"
    adr = [x(sell + f"ram:PostalTradeAddress/ram:{t}") for t in ("LineOne", "PostcodeCode", "CityName", "CountryID")]
    r = Eingangsrechnung(
        syntax="CII",
        profil=x("rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID"),
        nummer=x("rsm:ExchangedDocument/ram:ID"),
        datum=_datum(x("rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString")),
        typ=x("rsm:ExchangedDocument/ram:TypeCode"),
        waehrung=x(st + "ram:InvoiceCurrencyCode"),
        verkaeufer=x(sell + "ram:Name"),
        verkaeufer_anschrift=f"{adr[0]}, {adr[1]} {adr[2]}, {adr[3]}",
        verkaeufer_ust_id=x(sell + "ram:SpecifiedTaxRegistration/ram:ID[@schemeID='VA']"),
        verkaeufer_email=x(sell + "ram:URIUniversalCommunication/ram:URIID"),
        kaeufer=x(agr + "ram:BuyerTradeParty/ram:Name"),
        kaeufer_referenz=x(agr + "ram:BuyerReference"),
        faelligkeit=_datum(x(st + "ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString")),
        zahlungsbedingungen=x(st + "ram:SpecifiedTradePaymentTerms/ram:Description"),
        iban=x(st + "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID"),
        bic=x(st + "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeeSpecifiedCreditorFinancialInstitution/ram:BICID"),
        netto=_d(x(summen + "ram:TaxBasisTotalAmount")),
        steuer=_d(x(summen + "ram:TaxTotalAmount")),
        brutto=_d(x(summen + "ram:GrandTotalAmount")),
        zahlbetrag=_d(x(summen + "ram:DuePayableAmount")),
        bemerkungen=[n.text for n in root.xpath("rsm:ExchangedDocument/ram:IncludedNote/ram:Content", namespaces=CII)],
    )
    for li in root.xpath(tx + "ram:IncludedSupplyChainTradeLineItem", namespaces=CII):
        r.zeilen.append(Zeile(
            bezeichnung=x("ram:SpecifiedTradeProduct/ram:Name", li),
            menge=_d(x("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", li)),
            einheit=x("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity/@unitCode", li),
            einzelpreis=_d(x("ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount", li)),
            netto=_d(x("ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount", li)),
            kategorie=x("ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:CategoryCode", li),
            satz=_d(x("ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent", li)),
        ))
    for t in root.xpath(st + "ram:ApplicableTradeTax", namespaces=CII):
        r.steuern.append(Steuerzeile(x("ram:CategoryCode", t), _d(x("ram:RateApplicablePercent", t)),
                                     _d(x("ram:BasisAmount", t)), _d(x("ram:CalculatedAmount", t)),
                                     x("ram:ExemptionReason", t)))
    return r


def _lies_ubl(root) -> Eingangsrechnung:
    gutschrift = root.tag.endswith("}CreditNote")

    def x(path, ctx=root):
        r = ctx.xpath(path, namespaces=UBL)
        return r[0].strip() if r and isinstance(r[0], str) else (r[0].text or "").strip() if r else ""

    sell = "cac:AccountingSupplierParty/cac:Party/"
    adr = [x(sell + f"cac:PostalAddress/{t}") for t in
           ("cbc:StreetName", "cbc:PostalZone", "cbc:CityName", "cac:Country/cbc:IdentificationCode")]
    summen = "cac:LegalMonetaryTotal/"
    r = Eingangsrechnung(
        syntax="UBL",
        profil=x("cbc:CustomizationID"),
        nummer=x("cbc:ID"),
        datum=_datum(x("cbc:IssueDate")),
        typ=x("cbc:CreditNoteTypeCode" if gutschrift else "cbc:InvoiceTypeCode"),
        waehrung=x("cbc:DocumentCurrencyCode"),
        verkaeufer=x(sell + "cac:PartyLegalEntity/cbc:RegistrationName") or x(sell + "cac:PartyName/cbc:Name"),
        verkaeufer_anschrift=f"{adr[0]}, {adr[1]} {adr[2]}, {adr[3]}",
        verkaeufer_ust_id=x(sell + "cac:PartyTaxScheme[cac:TaxScheme/cbc:ID='VAT']/cbc:CompanyID"),
        verkaeufer_email=x(sell + "cbc:EndpointID"),
        kaeufer=(x("cac:AccountingCustomerParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName")
                 or x("cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name")),
        kaeufer_referenz=x("cbc:BuyerReference"),
        faelligkeit=_datum(x("cbc:DueDate") or x("cac:PaymentMeans/cbc:PaymentDueDate")),
        zahlungsbedingungen=x("cac:PaymentTerms/cbc:Note"),
        iban=x("cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID"),
        bic=x("cac:PaymentMeans/cac:PayeeFinancialAccount/cac:FinancialInstitutionBranch/cbc:ID"),
        netto=_d(x(summen + "cbc:TaxExclusiveAmount")),
        steuer=_d(x("cac:TaxTotal/cbc:TaxAmount")),
        brutto=_d(x(summen + "cbc:TaxInclusiveAmount")),
        zahlbetrag=_d(x(summen + "cbc:PayableAmount")),
        bemerkungen=[n.text for n in root.xpath("cbc:Note", namespaces=UBL)],
    )
    line, qty = ("cac:CreditNoteLine", "cbc:CreditedQuantity") if gutschrift else ("cac:InvoiceLine", "cbc:InvoicedQuantity")
    for li in root.xpath(line, namespaces=UBL):
        r.zeilen.append(Zeile(
            bezeichnung=x("cac:Item/cbc:Name", li),
            menge=_d(x(qty, li)), einheit=x(f"{qty}/@unitCode", li),
            einzelpreis=_d(x("cac:Price/cbc:PriceAmount", li)),
            netto=_d(x("cbc:LineExtensionAmount", li)),
            kategorie=x("cac:Item/cac:ClassifiedTaxCategory/cbc:ID", li),
            satz=_d(x("cac:Item/cac:ClassifiedTaxCategory/cbc:Percent", li)),
        ))
    for t in root.xpath("cac:TaxTotal/cac:TaxSubtotal", namespaces=UBL):
        r.steuern.append(Steuerzeile(x("cac:TaxCategory/cbc:ID", t), _d(x("cac:TaxCategory/cbc:Percent", t)),
                                     _d(x("cbc:TaxableAmount", t)), _d(x("cbc:TaxAmount", t)),
                                     x("cac:TaxCategory/cbc:TaxExemptionReason", t)))
    return r


def xml_aus_datei(pfad: Path) -> bytes:
    daten = Path(pfad).read_bytes()
    if daten[:5] == b"%PDF-":
        from facturx import get_xml_from_pdf

        _, xml = get_xml_from_pdf(daten, check_xsd=False)
        if not xml:
            raise LeseFehler(f"{pfad}: PDF enthält keine eingebettete E-Rechnung (kein ZUGFeRD/Factur-X)")
        return xml
    return daten


def lies(xml: bytes) -> Eingangsrechnung:
    try:
        root = etree.fromstring(xml, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as e:
        raise LeseFehler(f"Kein gültiges XML: {e}") from None
    if root.tag == f"{{{CII['rsm']}}}CrossIndustryInvoice":
        return _lies_cii(root)
    if root.tag in (f"{{{UBL['inv']}}}Invoice", f"{{{UBL['cn']}}}CreditNote"):
        return _lies_ubl(root)
    raise LeseFehler(f"Unbekanntes Format: {root.tag} (erwartet CII oder UBL)")


def lies_datei(pfad: Path) -> Eingangsrechnung:
    return lies(xml_aus_datei(pfad))
