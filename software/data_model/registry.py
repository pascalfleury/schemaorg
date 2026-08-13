#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Dict, List, Optional, Any
from rdflib import URIRef
import util.schema as schema
from . import models

class TermRegistry:
    """Central registry for all Schema.org terms identified by their full URIs or short IDs."""
    
    _instance: Optional["TermRegistry"] = None

    def __init__(self):
        self._terms: Dict[URIRef, Any] = {}
        self._id_index: Dict[str, URIRef] = {}
        self._graph: Optional[Any] = None

    @classmethod
    def get_instance(cls) -> "TermRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """Clears the global registry instance. Useful for testing."""
        cls._instance = None

    def _index_id(self, term_id: str, uri: URIRef):
        existing_uri = self._id_index.get(term_id)
        if not existing_uri:
            self._id_index[term_id] = uri
            return

        new_is_schema = schema.isSchemaUri(uri)
        old_is_schema = schema.isSchemaUri(existing_uri)
        
        if new_is_schema and not old_is_schema:
            self._id_index[term_id] = uri
            return

        if new_is_schema and old_is_schema:
            vocab_uri = getattr(schema, "VOCABURI", "https://schema.org/")
            if str(uri).startswith(vocab_uri) and not str(existing_uri).startswith(vocab_uri):
                self._id_index[term_id] = uri

    def register(self, term: Any):
        """Adds a term to the registry and indexes its short ID."""
        self._terms[term.uri] = term
        if hasattr(term, "id") and term.id:
            self._index_id(term.id, term.uri)
            # Also index prefixed version if available
            if ":" not in term.id:
                self._index_id(f"schema:{term.id}", term.uri)

    def get(self, uri: URIRef) -> Optional[Any]:
        """Retrieves a term by its full URI."""
        return self._terms.get(uri)

    def get_by_id(self, term_id: Any) -> Optional[Any]:
        """Retrieves a term by its short ID (e.g., 'Hotel') or full URI."""
        if not term_id:
            return None
        if isinstance(term_id, models.SdoTerm):
            return term_id
        if hasattr(term_id, "uri"):
            return self.get(URIRef(getattr(term_id, "uri")))
        term_id_str = str(term_id)
        if term_id_str.startswith(("http://", "https://")):
            return self.get(URIRef(term_id_str))
        uri = self._id_index.get(term_id_str)
        if not uri and ":" in term_id_str:
            # Try stripping prefix
            uri = self._id_index.get(term_id_str.split(":", 1)[1])
        return self.get(uri) if uri else None

    def all_terms(self) -> Dict[URIRef, Any]:
        """Returns all registered terms."""
        return self._terms.copy()

    @staticmethod
    def _filter_layer(terms: List[Any], layer: Optional[str]) -> List[Any]:
        if not layer:
            return terms
        if layer == "core":
            return [t for t in terms if not getattr(t, "isPartOf", None)]
        return [
            t for t in terms 
            if getattr(t, "layer", None) == layer 
            or layer in str(getattr(t, "isPartOf", ""))
        ]

    def get_all_terms(self, layer: Optional[str] = None) -> List[Any]:
        terms = [t for t in self._terms.values() if schema.isSchemaUri(t.uri)]
        return self._filter_layer(terms, layer)

    def get_all_types(self, layer: Optional[str] = None) -> List[Any]:
        terms = [
            t for t in self._terms.values() 
            if isinstance(t, models.SdoType) and not isinstance(t, (models.SdoEnumeration, models.SdoDataType)) and schema.isSchemaUri(t.uri)
        ]
        return self._filter_layer(terms, layer)

    def get_all_properties(self, layer: Optional[str] = None) -> List[Any]:
        terms = [t for t in self._terms.values() if isinstance(t, models.SdoProperty) and schema.isSchemaUri(t.uri)]
        return self._filter_layer(terms, layer)

    def get_all_datatypes(self, layer: Optional[str] = None) -> List[Any]:
        terms = [t for t in self._terms.values() if isinstance(t, models.SdoDataType) and schema.isSchemaUri(t.uri)]
        return self._filter_layer(terms, layer)

    def get_all_enumerations(self, layer: Optional[str] = None) -> List[Any]:
        terms = [t for t in self._terms.values() if isinstance(t, models.SdoEnumeration) and schema.isSchemaUri(t.uri)]
        return self._filter_layer(terms, layer)

    def get_all_enumerationvalues(self, layer: Optional[str] = None) -> List[Any]:
        terms = [t for t in self._terms.values() if isinstance(t, models.SdoEnumerationvalue) and schema.isSchemaUri(t.uri)]
        return self._filter_layer(terms, layer)

    def termCounts(self) -> Dict[str, int]:
        types = self.get_all_types()
        props = self.get_all_properties()
        dts = self.get_all_datatypes()
        enums = self.get_all_enumerations()
        enumvals = self.get_all_enumerationvalues()

        dt_uris = {t.uri for t in dts}
        dt_class_uris = set()
        for t in types:
            if any(u in dt_uris for u in getattr(t, "super_uris", [])):
                dt_class_uris.add(t.uri)
        for t in types:
            if any(u in dt_class_uris for u in getattr(t, "super_uris", [])):
                dt_class_uris.add(t.uri)

        types_count = len(types) - len(dt_class_uris)
        dts_count = len([d for d in dts if d.id != "DataType"]) + len(dt_class_uris)
        props_count = len(props)
        enums_count = len(enums)
        enumvals_count = len(enumvals)

        counts = {
            "Type": types_count,
            "Property": props_count,
            "Datatype": dts_count,
            "Enumeration": enums_count,
            "Enumerationvalue": enumvals_count,
            "All": types_count + props_count + dts_count + enums_count + enumvals_count
        }
        return counts

    def subClassOf(self, sub: str, sup: str) -> bool:
        t_sub = self.get_by_id(sub)
        t_sup = self.get_by_id(sup)
        if not t_sub or not t_sup:
            return False
        if t_sub.uri == t_sup.uri:
            return True
        return any(t_sup.uri == ancestor.uri for ancestor in getattr(t_sub, "termStack", []))

    def getParentPathTo(self, child_id: str, parent_id: str) -> List[Any]:
        child = self.get_by_id(child_id)
        parent = self.get_by_id(parent_id)
        if not child or not parent:
            return []
        if child.uri == parent.uri:
            return [[child]]
        paths = []
        for p in getattr(child, "superPaths", []):
            if parent in p:
                idx = p.index(parent)
                paths.append(p[idx:])
        return paths

    @classmethod
    def query(cls, q: str) -> Any:
        reg = cls.get_instance()
        if getattr(reg, "_graph", None):
            return reg._graph.query(q)
        return []


    def __len__(self) -> int:
        return len(self._terms)

