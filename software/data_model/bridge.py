#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
import os
import sys
import glob
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

import rdflib
from rdflib import URIRef

import util.schema as schema
from util.schema import URI
from .models import (
    SdoType,
    SdoDataType,
    SdoEnumeration,
    SdoEnumerationvalue,
    SdoProperty,
    SdoTerm,
    SdoReference,
)
from software.data_model.compat import CompatibilityList, UnexpandedTermError, LegacySdoTermAdapter, wrap_term
from .registry import TermRegistry
from .loader import GraphLoader

log: logging.Logger = logging.getLogger(__name__)

# Re-export for convenience
SdoTermSequence = CompatibilityList
SdoTermOrId = CompatibilityList

class SdoTermSource:
    """A compatibility bridge that mimics the old SdoTermSource API using the new Pydantic models."""

    _graph: Optional[rdflib.Graph] = None
    _loader: Optional[GraphLoader] = None
    _term_counts: Optional[Dict[str, int]] = None
    
    # Static attributes for backward compatibility
    MARKDOWNPROCESS = True
    
    SOURCEGRAPH: Optional[rdflib.Graph] = None
    LOADEDDEFAULT: bool = False

    @classmethod
    def setSourceGraph(cls, g: rdflib.Graph) -> None:
        """Sets the source graph and re-initializes the registry."""
        cls._graph = g
        cls.SOURCEGRAPH = g
        # Bind standard namespaces
        cls._graph.bind("schema", URI)
        cls._graph.bind("rdfs", rdflib.RDFS)
        cls._graph.bind("rdf", rdflib.RDF)
        cls._graph.bind("owl", rdflib.URIRef("http://www.w3.org/2002/07/owl#"))

        TermRegistry.reset()
        cls._loader = GraphLoader(cls._graph)
        cls._loader.load_all()
        cls._term_counts = None # Reset counts

    @classmethod
    def loadSourceGraph(cls, files: Optional[Union[str, List[str]]] = None, init: bool = False, vocaburi: Optional[str] = None) -> None:
        """Loads the source graph from files."""
        if init:
            cls._graph = None
            cls.SOURCEGRAPH = None
            cls.LOADEDDEFAULT = False
            TermRegistry.reset()
        if vocaburi:
            schema.setVocabUri(vocaburi)

        if files == "default" or files is None:
            if cls.LOADEDDEFAULT:
                return # Already loaded
            
            g = rdflib.Graph()
            # Find all turtle files in data directory and extensions
            standard_files = glob.glob("data/*.ttl") + glob.glob("data/ext/**/*.ttl", recursive=True)
            for f in sorted(standard_files):
                try:
                    g.parse(f, format="turtle")
                except Exception as e:
                    log.warning(f"Failed to parse {f}: {e}")
            cls.setSourceGraph(g)
            cls.LOADEDDEFAULT = True
        else:
            g = rdflib.Graph()
            if isinstance(files, str):
                g.parse(files)
            elif isinstance(files, list):
                for f in files:
                    g.parse(f)
            cls.setSourceGraph(g)

    @classmethod
    def sourceGraph(cls) -> rdflib.Graph:
        if cls.SOURCEGRAPH is None:
            cls.loadSourceGraph("default")
        return cls.SOURCEGRAPH

    @classmethod
    def getTerm(cls, term_id: str, expanded: bool = False, refresh: bool = False, createReference: bool = False) -> Optional[Any]:
        uri = cls.toFullId(term_id)
        registry = TermRegistry.get_instance()
        term = registry.get(URIRef(uri))
        
        if not term and createReference:
            term = SdoReference(uri=URIRef(uri), label=term_id)
            registry.register(term)

        if term:
            return wrap_term(term)
        return None

    @classmethod
    def termCache(cls) -> Dict[URIRef, Any]:
        return {uri: wrap_term(t) for uri, t in TermRegistry.get_instance().all_terms().items()}

    @classmethod
    def termCounts(cls) -> Dict[str, int]:
        if cls._term_counts is None:
            registry = TermRegistry.get_instance()
            counts = {
                "Type": 0,
                "Property": 0,
                "Datatype": 0,
                "Enumeration": 0,
                "Enumerationvalue": 0,
                "All": 0
            }
            for t in registry.all_terms().values():
                counts["All"] += 1
                if isinstance(t, SdoType): counts["Type"] += 1
                if isinstance(t, SdoProperty): counts["Property"] += 1
                if isinstance(t, SdoDataType): counts["Datatype"] += 1
                if isinstance(t, SdoEnumeration): counts["Enumeration"] += 1
                if isinstance(t, SdoEnumerationvalue): counts["Enumerationvalue"] += 1
            cls._term_counts = counts
        return cls._term_counts

    @classmethod
    def termsFromIds(cls, ids: Iterable[str]) -> CompatibilityList:
        return CompatibilityList([t for i in ids if (t := cls.getTerm(i))])

    @classmethod
    def expandTerms(cls, terms: Iterable[Union[str, SdoTerm]]) -> List[Any]:
        """Expands a list of term IDs or terms into a list of term objects."""
        res = []
        for t in terms:
            if isinstance(t, (SdoTerm, LegacySdoTermAdapter)):
                if isinstance(t, SdoTerm):
                    res.append(wrap_term(t))
                else:
                    res.append(t)
            else:
                term = cls.getTerm(t)
                if term:
                    res.append(term)
        return res

    @classmethod
    def getAllTypes(cls, **kwargs) -> List[Any]:
        return cls.getAllTerms(ttype="Class", **kwargs)

    @classmethod
    def getAllProperties(cls, **kwargs) -> List[Any]:
        return cls.getAllTerms(ttype="Property", **kwargs)

    @classmethod
    def getAllEnumerations(cls, **kwargs) -> List[Any]:
        return cls.getAllTerms(ttype="Enumeration", **kwargs)

    @classmethod
    def getAllEnumerationvalues(cls, **kwargs) -> List[Any]:
        return cls.getAllTerms(ttype="EnumerationValue", **kwargs)

    @classmethod
    def getAllDatatypes(cls, **kwargs) -> List[Any]:
        return cls.getAllTerms(ttype="DataType", **kwargs)

    @classmethod
    def subClassOf(cls, sub: str, sup: str) -> bool:
        t_sub = cls.getTerm(sub)
        t_sup = cls.getTerm(sup)
        if not t_sub or not t_sup:
            return False
        if t_sub == t_sup:
            return True
        return any(t_sup.id == ancestor.id for ancestor in t_sub.termStack)

    @classmethod
    def getParentPathTo(cls, term_id: str, target_id: str) -> CompatibilityList:
        term = cls.getTerm(term_id)
        if not term:
            return CompatibilityList()
        target = cls.getTerm(target_id)
        if not target:
            return CompatibilityList()
        
        if term == target:
            return CompatibilityList()

        paths = []
        for path in term.superPaths:
            if any(target.id == p.id for p in path):
                # Find the index of the target
                for idx, p in enumerate(path):
                    if p.id == target.id:
                        paths.append(CompatibilityList(path[idx:]))
                        break
        return CompatibilityList(paths)

    @classmethod
    def getAllTerms(
        cls,
        ttype: Optional[str] = None,
        layer: Optional[str] = None,
        suppressSourceLinks: bool = False,
        expanded: bool = False,
    ) -> List[Union[str, Any]]:
        registry = TermRegistry.get_instance()
        terms = list(registry.all_terms().values())

        filtered = []
        for t in terms:
            if layer and t.layer != layer:
                continue

            if ttype:
                if ttype == "Class" and not isinstance(t, SdoType):
                    continue
                if ttype == "Property" and not isinstance(t, SdoProperty):
                    continue
                if ttype == "DataType" and not isinstance(t, SdoDataType):
                    continue
                if ttype == "Enumeration" and not isinstance(t, SdoType): # Enumeration is a SdoType
                    if not isinstance(t, SdoEnumeration):
                         continue
                if ttype == "EnumerationValue" and not isinstance(t, SdoEnumerationvalue):
                    continue

            if suppressSourceLinks and t.source_uris:
                continue

            if expanded:
                filtered.append(wrap_term(t))
            else:
                filtered.append(t.id)

        if expanded:
            filtered.sort(key=lambda x: x.id)
        else:
            filtered.sort()

        return filtered

    @staticmethod
    def toFullId(term_id: str) -> str:
        if term_id.startswith(("http:", "https:")):
            return term_id
        if ":" in term_id:
            return term_id
        return f"{schema.VOCABURI}{term_id}"

    @classmethod
    def query(cls, query_string: str) -> Any:
        return cls.sourceGraph().query(query_string, initNs={
            "schema": URI,
            "rdfs": rdflib.RDFS,
            "rdf": rdflib.RDF,
            "owl": rdflib.URIRef("http://www.w3.org/2002/07/owl#")
        })

    @classmethod
    def vocabUri(cls) -> str:
        return schema.VOCABURI

    @classmethod
    def getTermAsRdfString(cls, term_id: str, format: str, full: bool = False) -> str:
        term = cls.getTerm(term_id)
        if not term: return ""
        # Implementation of RDF serialization could go here
        return ""
