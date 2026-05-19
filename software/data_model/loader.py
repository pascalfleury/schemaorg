#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from typing import Dict, List, Optional, Set, Type, Union, Any

from rdflib import Graph, RDF, RDFS, URIRef

from util.schema import URI
from .models import SdoType, SdoDataType, SdoEnumeration, SdoEnumerationvalue, SdoProperty, SdoTerm
from .registry import TermRegistry

log: logging.Logger = logging.getLogger(__name__)

class GraphLoader:
    """Loader to populate Pydantic models from an rdflib.Graph using bulk queries."""

    def __init__(self, graph: Graph, registry: Optional[TermRegistry] = None):
        self.graph = graph
        self.registry = registry or TermRegistry.get_instance()

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
            FILTER(?type IN (<{RDFS.Class}>, <{RDF.Property}>, <{URI.DataType}>))
        }}
        """
        for row in self.graph.query(query_types):
            uri = row.term
            if isinstance(uri, URIRef):
                term_types.setdefault(uri, set()).add(row.type)
                term_data.setdefault(uri, {"uri": uri})

        # 2. Fetch all metadata and relations in bulk
        query_data = f"""
        SELECT ?term ?p ?o WHERE {{
            ?term a ?type .
            FILTER(?type IN (<{RDFS.Class}>, <{RDF.Property}>, <{URI.DataType}>))
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

        for row in self.graph.query(query_data):
            uri, p, o = row.term, row.p, row.o
            if p in field_map:
                field = field_map[p]
                data = term_data.setdefault(uri, {"uri": uri})
                
                if field.endswith("_uris"): # List fields
                    data.setdefault(field, []).append(o)
                else:
                    # Convert literals to strings, keep URIRefs
                    data[field] = str(o) if not isinstance(o, URIRef) else o

        # 3. Instantiate and register Class/Property terms
        for uri, data in term_data.items():
            types = term_types.get(uri, set())
            
            # Ensure mandatory fields have at least a default if missing in graph
            if "label" not in data:
                data["label"] = str(uri).split("/")[-1].split("#")[-1]

            try:
                if RDF.Property in types:
                    obj = SdoProperty.model_validate(data)
                elif RDFS.Class in types or URI.DataType in types:
                    if URI.DataType in types or self._is_subclass_of(uri, URI.DataType):
                        obj = SdoDataType.model_validate(data)
                    elif self._is_subclass_of(uri, URI.Enumeration):
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
            ?enum <{RDFS.subClassOf}>* <{URI.Enumeration}> .
            ?val a ?enum .
            OPTIONAL {{ ?val <{RDFS.label}> ?label }}
            OPTIONAL {{ ?val <{RDFS.comment}> ?comment }}
            OPTIONAL {{ ?val <{URI.isPartOf}> ?isPartOf }}
        }}
        """
        for row in self.graph.query(query_enums):
            uri = row.val
            if isinstance(uri, URIRef):
                if uri in self.registry.all_terms():
                    continue
                    
                try:
                    val = SdoEnumerationvalue.model_validate({
                        "uri": uri,
                        "label": str(row.label or str(uri).split("/")[-1]),
                        "comment": str(row.comment or ""),
                        "isPartOf": row.isPartOf,
                        "enumeration_uri": row.enum
                    })
                    self._enrich_metadata(val)
                    self.registry.register(val)
                except Exception as e:
                    log.warning(f"Failed to load enum value {uri}: {e}")

        return len(self.registry)

    def _enrich_metadata(self, term: SdoTerm):
        """Adds system metadata (layer, pending, retired) to a term."""
        if term.isPartOf:
            uri_str = str(term.isPartOf)
            if "pending" in uri_str:
                term.layer = "pending"
                term.pending = True
            elif "attic" in uri_str:
                term.layer = "attic"
                term.retired = True
            else:
                # Handle cases like http://bib.schema.org/
                parts = uri_str.rstrip("/").split("/")
                last = parts[-1]
                if "." in last:
                    term.layer = last.split(".")[-2]
                else:
                    term.layer = last
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
