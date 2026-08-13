#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Canonical RDF namespaces for Schema.org."""

from typing import Dict, Optional
from rdflib import Graph, URIRef

NAMESPACES: Dict[str, str] = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "dctype": "http://purl.org/dc/dcmitype/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "void": "http://rdfs.org/ns/void#",
    "cmns-cls": "https://www.omg.org/spec/Commons/Classifiers/",
    "cmns-col": "https://www.omg.org/spec/Commons/Collections/",
    "cmns-dt": "https://www.omg.org/spec/Commons/DatesAndTimes/",
    "cmns-ge": "https://www.omg.org/spec/Commons/GeopoliticalEntities/",
    "cmns-id": "https://www.omg.org/spec/Commons/Identifiers/",
    "cmns-loc": "https://www.omg.org/spec/Commons/Locations/",
    "cmns-q": "https://www.omg.org/spec/Commons/Quantities/",
    "cmns-txt": "https://www.omg.org/spec/Commons/Text/",
    "lcc-3166-1": "https://www.omg.org/spec/LCC/Countries/ISO3166-1-CountryCodes/",
    "lcc-4217": "https://www.omg.org/spec/LCC/Countries/ISO4217-CurrencyCodes/",
    "lcc-lr": "https://www.omg.org/spec/LCC/Languages/LanguageRepresentation/",
    "fibo-be-corp-corp": "https://spec.edmcouncil.org/fibo/ontology/BE/Corporations/Corporations/",
    "fibo-be-ge-ge": "https://spec.edmcouncil.org/fibo/ontology/BE/GovernmentEntities/GovernmentEntities/",
    "fibo-be-le-cb": "https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/CorporateBodies/",
    "fibo-be-le-lp": "https://spec.edmcouncil.org/fibo/ontology/BE/LegalEntities/LegalPersons/",
    "fibo-be-nfp-nfp": "https://spec.edmcouncil.org/fibo/ontology/BE/NotForProfitOrganizations/NotForProfitOrganizations/",
    "fibo-be-oac-cctl": "https://spec.edmcouncil.org/fibo/ontology/BE/OwnershipAndControl/CorporateControl/",
    "fibo-fbc-dae-dbt": "https://spec.edmcouncil.org/fibo/ontology/FBC/DebtAndEquities/Debt/",
    "fibo-fbc-pas-fpas": "https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/FinancialProductsAndServices/",
    "fibo-fnd-acc-cur": "https://spec.edmcouncil.org/fibo/ontology/FND/Accounting/CurrencyAmount/",
    "fibo-fnd-agr-ctr": "https://spec.edmcouncil.org/fibo/ontology/FND/Agreements/Contracts/",
    "fibo-fnd-arr-doc": "https://spec.edmcouncil.org/fibo/ontology/FND/Arrangements/Documents/",
    "fibo-fnd-arr-lif": "https://spec.edmcouncil.org/fibo/ontology/FND/Arrangements/Lifecycles/",
    "fibo-fnd-dt-oc": "https://spec.edmcouncil.org/fibo/ontology/FND/DatesAndTimes/Occurrences/",
    "fibo-fnd-org-org": "https://spec.edmcouncil.org/fibo/ontology/FND/Organizations/Organizations/",
    "fibo-fnd-pas-pas": "https://spec.edmcouncil.org/fibo/ontology/FND/ProductsAndServices/ProductsAndServices/",
    "fibo-fnd-plc-adr": "https://spec.edmcouncil.org/fibo/ontology/FND/Places/Addresses/",
    "fibo-fnd-plc-fac": "https://spec.edmcouncil.org/fibo/ontology/FND/Places/Facilities/",
    "fibo-fnd-plc-loc": "https://spec.edmcouncil.org/fibo/ontology/FND/Places/Locations/",
    "fibo-fnd-pty-pty": "https://spec.edmcouncil.org/fibo/ontology/FND/Parties/Parties/",
    "fibo-fnd-rel-rel": "https://spec.edmcouncil.org/fibo/ontology/FND/Relations/Relations/",
    "fibo-pay-ps-ps": "https://spec.edmcouncil.org/fibo/ontology/PAY/PaymentServices/PaymentServices/",
    "gleif-L1": "https://www.gleif.org/ontology/L1/",
    "gs1": "https://ref.gs1.org/voc/",
    "lcc-cr": "https://www.omg.org/spec/LCC/Countries/CountryRepresentation/",
    "unece": "http://unece.org/vocab#",
    "vcard": "http://www.w3.org/2006/vcard/ns#",
    "bibo": "http://purl.org/ontology/bibo/",
    "sarif": "http://sarif.info/",
    "lrmoo": "http://iflastandards.info/ns/lrm/lrmoo/",
    "snomed": "http://purl.bioontology.org/ontology/SNOMEDCT/",
    "eli": "http://data.europa.eu/eli/ontology#",
    "prov": "http://www.w3.org/ns/prov#",
    "hydra": "http://www.w3.org/ns/hydra/core#",
    "mo": "http://purl.org/ontology/mo/",
    "og": "http://ogp.me/ns#",
}


def bind_namespaces(graph: Graph) -> None:
    """Binds standard Schema.org namespaces to an RDFLib graph."""
    for prefix, uri in NAMESPACES.items():
        graph.bind(prefix, URIRef(uri))


def get_prefix_for_uri(uri: str) -> Optional[str]:
    """Returns the matching prefix for a URI string if known."""
    for prefix, pth in NAMESPACES.items():
        if uri.startswith(pth):
            return prefix
    return None
