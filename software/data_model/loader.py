#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from typing import Dict, List, Optional, Set, Type, Union, Any

from rdflib import Graph, RDF, RDFS, URIRef
from util.paths import InputLayout, Domain
import util.schema as schema
from util.schema import URI
from .models import SdoType, SdoDataType, SdoEnumeration, SdoEnumerationvalue, SdoProperty, SdoTerm
from .registry import TermRegistry

log: logging.Logger = logging.getLogger(__name__)

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

class GraphLoader:
    """Loader to populate Pydantic models from an rdflib.Graph using bulk queries."""

    def __init__(self, graph: Graph, registry: Optional[TermRegistry] = None):
        self.graph = graph
        self.registry = registry or TermRegistry.get_instance()
        self.registry._graph = graph
        self.graph.bind("schema", schema.URI)
        for prefix, uri in NAMESPACES.items():
            self.graph.bind(prefix, URIRef(uri))

    @classmethod
    def from_layout(cls, layout: InputLayout, vocaburi: Optional[str] = None) -> "GraphLoader":
        import util.schema as schema
        if vocaburi:
            schema.setVocabUri(vocaburi)
        g = Graph()
        files = layout.domain_files(Domain.DATA, ["*.ttl", "ext/**/*.ttl"])
        for f in sorted(files):
            try:
                g.parse(str(f), format="turtle")
            except Exception as e:
                log.warning(f"Failed to parse {f}: {e}")
        return cls(g)


    def load_all(self) -> int:
        """Loads all Schema.org entities from the graph into the registry efficiently."""
        
        # Data structure: term_data[uri][field_name] = value_or_list
        term_data: Dict[URIRef, Dict[str, Any]] = {}
        term_types: Dict[URIRef, Set[URIRef]] = {}

        # 1. Fetch all terms and their types
        # Include DataType as a type itself
        query_types = f"""
        SELECT ?term ?type WHERE {{
            ?term a ?type .
            FILTER(?type IN (<{RDFS.Class}>, <{RDF.Property}>, <http://schema.org/DataType>, <https://schema.org/DataType>))
        }}
        """
        for term, type_ in self.graph.query(query_types):
            if isinstance(term, URIRef):
                term_types.setdefault(term, set()).add(type_)
                term_data.setdefault(term, {"uri": term})

        # 2. Fetch all metadata and relations in bulk
        query_data = f"""
        SELECT ?term ?p ?o WHERE {{
            ?term a ?type .
            FILTER(?type IN (<{RDFS.Class}>, <{RDF.Property}>, <http://schema.org/DataType>, <https://schema.org/DataType>))
            ?term ?p ?o .
        }}
        """
        
        # Map predicates to field names in our models
        field_map = {
            RDFS.label: "label",
            RDFS.comment: "comment",
            URI.isPartOf: "isPartOf",
            URI.source: "source_uris",
            URI.contributor: "contributor_uris",
            URI.supersededBy: "superseded_by_uri",
            RDFS.subClassOf: "super_uris",
            RDFS.subPropertyOf: "super_uris",
            URI.domainIncludes: "domain_uris",
            URI.rangeIncludes: "range_uris",
            URI.inverseOf: "inverse_uri",
            URIRef("http://www.w3.org/2002/07/owl#equivalentClass"): "equivalent_uris",
            URIRef("http://www.w3.org/2002/07/owl#equivalentProperty"): "equivalent_property_uris",
        }

        for term, p, o in self.graph.query(query_data):
            if p in field_map and isinstance(term, URIRef):
                field = field_map[p]
                data = term_data.setdefault(term, {"uri": term})
                
                if field.endswith("_uris"): # List fields
                    data.setdefault(field, []).append(o)
                else:
                    # Convert literals to strings, keep URIRefs
                    data[field] = str(o) if not isinstance(o, URIRef) else o

        # 3. Instantiate and register Class/Property terms
        for uri, data in term_data.items():
            is_schema = "schema.org" in str(uri)
            types = term_types.get(uri, set())
            
            # Ensure mandatory fields have at least a default if missing in graph
            if "label" not in data:
                if is_schema:
                    data["label"] = str(uri).split("/")[-1].split("#")[-1]
                else:
                    try:
                        qname = self.graph.namespace_manager.compute_qname(uri)
                        data["label"] = f"{qname[0]}:{qname[2]}"
                    except Exception:
                        data["label"] = str(uri).split("/")[-1].split("#")[-1]

            obj: Any = None
            try:
                if RDF.Property in types:
                    obj = SdoProperty.model_validate(data)
                elif RDFS.Class in types or URI.DataType in types or URIRef("https://schema.org/DataType") in types:
                    if URI.DataType in types or URIRef("https://schema.org/DataType") in types or self._is_subclass_of(uri, URI.DataType) or self._is_subclass_of(uri, URIRef("https://schema.org/DataType")):
                        obj = SdoDataType.model_validate(data)
                    elif self._is_subclass_of(uri, URI.Enumeration) or self._is_subclass_of(uri, URIRef("https://schema.org/Enumeration")):
                        obj = SdoEnumeration.model_validate(data)
                    else:
                        obj = SdoType.model_validate(data)
                else:
                    continue
                
                self._enrich_metadata(obj)
                self.registry.register(obj)
            except Exception as e:
                log.warning(f"Failed to validate term {uri}: {e}")

        # 4. Handle Enumeration Values (Instances of Enumerations)
        # We need to find classes that are subclasses of Enumeration
        query_enums = f"""
        SELECT ?val ?enum ?label ?comment ?isPartOf WHERE {{
            {{
                ?enum <{RDFS.subClassOf}>* ?rootEnum .
                FILTER(?rootEnum IN (<http://schema.org/Enumeration>, <https://schema.org/Enumeration>))
            }} UNION {{
                ?enum <{RDFS.subClassOf}>* ?parent .
                ?parent a ?dataTypeClass .
                FILTER(?dataTypeClass IN (<http://schema.org/DataType>, <https://schema.org/DataType>))
            }}
            ?val a ?enum .
            FILTER(?enum NOT IN (<http://schema.org/Enumeration>, <https://schema.org/Enumeration>, <http://schema.org/DataType>, <https://schema.org/DataType>))
            OPTIONAL {{ ?val <{RDFS.label}> ?label }}
            OPTIONAL {{ ?val <{RDFS.comment}> ?comment }}
            OPTIONAL {{ ?val <{URI.isPartOf}> ?isPartOf }}
            OPTIONAL {{ ?val <https://schema.org/isPartOf> ?isPartOf }}
        }}
        """
        enum_vals_data: Dict[URIRef, Dict[str, Any]] = {}
        for val, enum, label, comment, is_part_of in self.graph.query(query_enums):
            if isinstance(val, URIRef):
                if "schema.org" not in str(val):
                    continue
                data = enum_vals_data.setdefault(val, {
                    "uri": val,
                    "label": str(label or str(val).split("/")[-1]),
                    "comment": str(comment or ""),
                    "isPartOf": is_part_of,
                    "enumeration_uris": []
                })
                if enum not in data["enumeration_uris"]:
                    data["enumeration_uris"].append(enum)

        for uri, data in enum_vals_data.items():
            try:
                super_uris = [o for o in self.graph.objects(uri, RDFS.subClassOf) if isinstance(o, URIRef)]
                equivalent_uris = [o for o in self.graph.objects(uri, URIRef("http://www.w3.org/2002/07/owl#equivalentClass")) if isinstance(o, URIRef)]
                superseded_by = next(self.graph.objects(uri, URI.supersededBy), None) or next(self.graph.objects(uri, URIRef("https://schema.org/supersededBy")), None)
                
                source_uris = list(self.graph.objects(uri, URIRef("http://schema.org/source"))) + list(self.graph.objects(uri, URIRef("https://schema.org/source")))
                source_uris = list(set([o for o in source_uris if isinstance(o, URIRef)]))
                
                contributor_uris = list(self.graph.objects(uri, URIRef("http://schema.org/contributor"))) + list(self.graph.objects(uri, URIRef("https://schema.org/contributor")))
                contributor_uris = list(set([o for o in contributor_uris if isinstance(o, URIRef)]))

                data.update({
                    "super_uris": super_uris,
                    "equivalent_uris": equivalent_uris,
                    "superseded_by_uri": superseded_by,
                    "source_uris": source_uris,
                    "contributor_uris": contributor_uris
                })
                
                val = SdoEnumerationvalue.model_validate(data)
                self._enrich_metadata(val)
                self.registry.register(val)
            except Exception as e:
                log.warning(f"Failed to load enum value {uri}: {e}")

        # Clear termStack for Enumerations with no properties (matching old codebase bug)
        for term in list(self.registry.all_terms().values()):
            if isinstance(term, SdoEnumeration) and term.id != "Enumeration" and not term.properties:
                term._stack_cleared = True

        return len(self.registry)

    def _enrich_metadata(self, term: SdoTerm):
        """Adds system metadata (layer, pending, retired) to a term."""
        if term.isPartOf:
            layer = schema.layerFromUri(str(term.isPartOf))
            if layer:
                term.layer = layer
                if layer == "pending":
                    term.pending = True
                elif layer == "attic":
                    term.retired = True
            else:
                term.layer = "core"
        else:
            term.layer = "core"

    def _is_subclass_of(self, uri: URIRef, parent: URIRef) -> bool:
        """Recursive check for subclass relationship in the raw graph."""
        if uri == parent:
            return True
        for sup in self.graph.objects(uri, RDFS.subClassOf):
            if isinstance(sup, URIRef) and self._is_subclass_of(sup, parent):
                return True
        return False
