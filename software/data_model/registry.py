#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Dict, List, Optional, Any
from rdflib import URIRef

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

    def register(self, term: Any):
        """Adds a term to the registry and indexes its short ID."""
        self._terms[term.uri] = term
        if hasattr(term, "id") and term.id:
            self._id_index[term.id] = term.uri
            # Also index prefixed version if available
            if ":" not in term.id:
                self._id_index[f"schema:{term.id}"] = term.uri

    def get(self, uri: URIRef) -> Optional[Any]:
        """Retrieves a term by its full URI."""
        return self._terms.get(uri)

    def get_by_id(self, term_id: Any) -> Optional[Any]:
        """Retrieves a term by its short ID (e.g., 'Hotel') or full URI."""
        if not term_id:
            return None
        from .models import SdoTerm
        if isinstance(term_id, SdoTerm):
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

    def get_all_terms(self, layer: Optional[str] = None) -> List[Any]:
        terms = list(self._terms.values())
        if layer:
            terms = [t for t in terms if getattr(t, "layer", None) == layer]
        return terms

    def get_all_types(self, layer: Optional[str] = None) -> List[Any]:
        from .models import SdoType
        terms = [t for t in self._terms.values() if isinstance(t, SdoType)]
        if layer:
            terms = [t for t in terms if getattr(t, "layer", None) == layer]
        return terms

    def get_all_properties(self, layer: Optional[str] = None) -> List[Any]:
        from .models import SdoProperty
        terms = [t for t in self._terms.values() if isinstance(t, SdoProperty)]
        if layer:
            terms = [t for t in terms if getattr(t, "layer", None) == layer]
        return terms

    def get_all_datatypes(self, layer: Optional[str] = None) -> List[Any]:
        from .models import SdoDataType
        terms = [t for t in self._terms.values() if isinstance(t, SdoDataType)]
        if layer:
            terms = [t for t in terms if getattr(t, "layer", None) == layer]
        return terms

    def get_all_enumerations(self, layer: Optional[str] = None) -> List[Any]:
        from .models import SdoEnumeration
        terms = [t for t in self._terms.values() if isinstance(t, SdoEnumeration)]
        if layer:
            terms = [t for t in terms if getattr(t, "layer", None) == layer]
        return terms

    def get_all_enumerationvalues(self, layer: Optional[str] = None) -> List[Any]:
        from .models import SdoEnumerationvalue
        terms = [t for t in self._terms.values() if isinstance(t, SdoEnumerationvalue)]
        if layer:
            terms = [t for t in terms if getattr(t, "layer", None) == layer]
        return terms

    def termCounts(self) -> Dict[str, int]:
        counts = {
            "Type": len(self.get_all_types()),
            "Property": len(self.get_all_properties()),
            "Datatype": len(self.get_all_datatypes()),
            "Enumeration": len(self.get_all_enumerations()),
            "Enumerationvalue": len(self.get_all_enumerationvalues()),
            "All": len(self._terms)
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

    # Legacy aliases
    getTerm = get_by_id
    getAllTypes = get_all_types

    def __len__(self) -> int:
        return len(self._terms)

