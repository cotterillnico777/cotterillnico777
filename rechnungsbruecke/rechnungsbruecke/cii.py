"""Erzeugt UN/CEFACT-CII-XML (XRechnung 3.0 bzw. ZUGFeRD/Factur-X EN 16931) aus einer Rechnung."""
from decimal import Decimal

from lxml import etree

from .modell import Partei, Rechnung, runden

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
}
PROFILE = {
    "xrechnung": "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0",
    "zugferd": "urn:cen.eu:en16931:2017",
}
PEPPOL_PROZESS = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"


def _el(parent, tag, text=None, **attrib):
    prefix, name = tag.split(":")
    e = etree.SubElement(parent, f"{{{NS[prefix]}}}{name}", attrib)
    if text is not None:
        e.text = text
    return e


def betrag(d: Decimal) -> str:
    return f"{runden(d):.2f}"


def zahl(d: Decimal) -> str:
    """Menge/Preis/Satz ohne unnötige Nachkommastellen (z. B. 19, 2.5, 12.3456)."""
    s = format(Decimal(d).normalize(), "f")
    return s if s not in ("-0",) else "0"


def _datum(parent, tag, d):
    wrapper = _el(parent, tag)
    _el(wrapper, "udt:DateTimeString", d.strftime("%Y%m%d"), format="102")


def _partei(parent, tag, p: Partei, verkaeufer: bool):
    tp = _el(parent, tag)
    if p.kennung:
        _el(tp, "ram:ID", p.kennung)
    _el(tp, "ram:Name", p.name)
    if p.registernummer:
        _el(_el(tp, "ram:SpecifiedLegalOrganization"), "ram:ID", p.registernummer)
    if p.kontakt_name or p.kontakt_email or p.kontakt_telefon:
        c = _el(tp, "ram:DefinedTradeContact")
        if p.kontakt_name:
            _el(c, "ram:PersonName", p.kontakt_name)
        if p.kontakt_telefon:
            _el(_el(c, "ram:TelephoneUniversalCommunication"), "ram:CompleteNumber", p.kontakt_telefon)
        if p.kontakt_email:
            _el(_el(c, "ram:EmailURIUniversalCommunication"), "ram:URIID", p.kontakt_email)
    a = _el(tp, "ram:PostalTradeAddress")
    _el(a, "ram:PostcodeCode", p.anschrift.plz)
    _el(a, "ram:LineOne", p.anschrift.strasse)
    _el(a, "ram:CityName", p.anschrift.ort)
    _el(a, "ram:CountryID", p.anschrift.land)
    if p.email:
        _el(_el(tp, "ram:URIUniversalCommunication"), "ram:URIID", p.email, schemeID="EM")
    if p.ust_id:
        _el(_el(tp, "ram:SpecifiedTaxRegistration"), "ram:ID", p.ust_id, schemeID="VA")
    if p.steuernummer and verkaeufer:
        _el(_el(tp, "ram:SpecifiedTaxRegistration"), "ram:ID", p.steuernummer, schemeID="FC")


def erzeuge_cii(r: Rechnung, profil: str = "xrechnung") -> bytes:
    if profil not in PROFILE:
        raise ValueError(f"Unbekanntes Profil '{profil}', erlaubt: {', '.join(PROFILE)}")
    root = etree.Element(f"{{{NS['rsm']}}}CrossIndustryInvoice", nsmap=NS)

    ctx = _el(root, "rsm:ExchangedDocumentContext")
    if profil == "xrechnung":
        _el(_el(ctx, "ram:BusinessProcessSpecifiedDocumentContextParameter"), "ram:ID", PEPPOL_PROZESS)
    _el(_el(ctx, "ram:GuidelineSpecifiedDocumentContextParameter"), "ram:ID", PROFILE[profil])

    doc = _el(root, "rsm:ExchangedDocument")
    _el(doc, "ram:ID", r.nummer)
    _el(doc, "ram:TypeCode", r.typ)
    _datum(doc, "ram:IssueDateTime", r.datum)
    if r.bemerkung:
        _el(_el(doc, "ram:IncludedNote"), "ram:Content", r.bemerkung)

    tx = _el(root, "rsm:SupplyChainTradeTransaction")
    for i, p in enumerate(r.positionen, start=1):
        li = _el(tx, "ram:IncludedSupplyChainTradeLineItem")
        _el(_el(li, "ram:AssociatedDocumentLineDocument"), "ram:LineID", str(i))
        prod = _el(li, "ram:SpecifiedTradeProduct")
        if p.artikelnummer:
            _el(prod, "ram:SellerAssignedID", p.artikelnummer)
        _el(prod, "ram:Name", p.bezeichnung)
        agr = _el(li, "ram:SpecifiedLineTradeAgreement")
        _el(_el(agr, "ram:NetPriceProductTradePrice"), "ram:ChargeAmount", zahl(p.einzelpreis))
        _el(_el(li, "ram:SpecifiedLineTradeDelivery"), "ram:BilledQuantity", zahl(p.menge), unitCode=p.einheit)
        st = _el(li, "ram:SpecifiedLineTradeSettlement")
        tax = _el(st, "ram:ApplicableTradeTax")
        _el(tax, "ram:TypeCode", "VAT")
        _el(tax, "ram:CategoryCode", p.kategorie)
        _el(tax, "ram:RateApplicablePercent", zahl(p.ust_satz))
        _el(_el(st, "ram:SpecifiedTradeSettlementLineMonetarySummation"), "ram:LineTotalAmount", betrag(p.netto))

    agr = _el(tx, "ram:ApplicableHeaderTradeAgreement")
    if r.kaeufer_referenz:
        _el(agr, "ram:BuyerReference", r.kaeufer_referenz)
    _partei(agr, "ram:SellerTradeParty", r.verkaeufer, verkaeufer=True)
    _partei(agr, "ram:BuyerTradeParty", r.kaeufer, verkaeufer=False)
    if r.bestellnummer:
        _el(_el(agr, "ram:BuyerOrderReferencedDocument"), "ram:IssuerAssignedID", r.bestellnummer)

    lief = _el(tx, "ram:ApplicableHeaderTradeDelivery")
    if any(p.kategorie == "K" for p in r.positionen):
        # Lieferland (BT-80) ist bei innergemeinschaftlichen Lieferungen Pflicht
        ship = _el(lief, "ram:ShipToTradeParty")
        _el(ship, "ram:Name", r.kaeufer.name)
        a = _el(ship, "ram:PostalTradeAddress")
        _el(a, "ram:PostcodeCode", r.kaeufer.anschrift.plz)
        _el(a, "ram:LineOne", r.kaeufer.anschrift.strasse)
        _el(a, "ram:CityName", r.kaeufer.anschrift.ort)
        _el(a, "ram:CountryID", r.kaeufer.anschrift.land)
    if r.leistungsdatum:
        ev = _el(lief, "ram:ActualDeliverySupplyChainEvent")
        _datum(ev, "ram:OccurrenceDateTime", r.leistungsdatum)

    st = _el(tx, "ram:ApplicableHeaderTradeSettlement")
    _el(st, "ram:InvoiceCurrencyCode", r.waehrung)
    if r.bank:
        pm = _el(st, "ram:SpecifiedTradeSettlementPaymentMeans")
        _el(pm, "ram:TypeCode", "58")  # SEPA-Überweisung
        acc = _el(pm, "ram:PayeePartyCreditorFinancialAccount")
        _el(acc, "ram:IBANID", r.bank.iban.replace(" ", ""))
        if r.bank.kontoinhaber:
            _el(acc, "ram:AccountName", r.bank.kontoinhaber)
        if r.bank.bic:
            _el(_el(pm, "ram:PayeeSpecifiedCreditorFinancialInstitution"), "ram:BICID", r.bank.bic)
    for s in r.steuern:
        t = _el(st, "ram:ApplicableTradeTax")
        _el(t, "ram:CalculatedAmount", betrag(s.steuer))
        _el(t, "ram:TypeCode", "VAT")
        if s.befreiungsgrund:
            _el(t, "ram:ExemptionReason", s.befreiungsgrund)
        _el(t, "ram:BasisAmount", betrag(s.basis))
        _el(t, "ram:CategoryCode", s.kategorie)
        _el(t, "ram:RateApplicablePercent", zahl(s.satz))
    if r.leistungszeitraum:
        per = _el(st, "ram:BillingSpecifiedPeriod")
        _datum(per, "ram:StartDateTime", r.leistungszeitraum[0])
        _datum(per, "ram:EndDateTime", r.leistungszeitraum[1])
    if r.zahlungsbedingungen or r.faelligkeit:
        terms = _el(st, "ram:SpecifiedTradePaymentTerms")
        if r.zahlungsbedingungen:
            _el(terms, "ram:Description", r.zahlungsbedingungen)
        if r.faelligkeit:
            _datum(terms, "ram:DueDateDateTime", r.faelligkeit)
    summen = _el(st, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    _el(summen, "ram:LineTotalAmount", betrag(r.summe_positionen))
    _el(summen, "ram:TaxBasisTotalAmount", betrag(r.netto))
    _el(summen, "ram:TaxTotalAmount", betrag(r.steuer), currencyID=r.waehrung)
    _el(summen, "ram:GrandTotalAmount", betrag(r.brutto))
    if r.vorauszahlung:
        _el(summen, "ram:TotalPrepaidAmount", betrag(r.vorauszahlung))
    _el(summen, "ram:DuePayableAmount", betrag(r.zahlbetrag))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
