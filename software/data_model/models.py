#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Annotated, List, Optional, Union, ClassVar, Any, Dict, Set
from pydantic import Field, ConfigDict, computed_field
from pydantic_rdf import BaseRdfModel, WithPredicate
from rdflib import RDFS, RDF, URIRef
import util.schema as schema
from .type_map import SdoTermType

class TermList(list):
    """List subclass that adds a convenience .ids getter for backward compatibility."""
    @property
    def ids(self) -> List[str]:
        return [getattr(t, "id", str(t)) for t in self]
    @property
    def terms(self) -> List[Any]:
        return self
class ExpandedBool(int):
    """Boolean-like integer that also supports being called as a zero-argument function."""
    def __new__(cls, val=1):
        return super().__new__(cls, val)
    def __call__(self) -> bool:
        return True
    def __str__(self) -> str:
        return "True"
    def __repr__(self) -> str:
        return "True"

class SdoTerm(BaseRdfModel):
    """Base model for all Schema.org terms."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    rdf_type: ClassVar[URIRef] = RDFS.Resource

    label: Annotated[str, WithPredicate(RDFS.label)]
    comment: Annotated[Optional[str], WithPredicate(RDFS.comment)] = ""
    isPartOf: Annotated[Optional[URIRef], WithPredicate(schema.URI.isPartOf)] = None
    
    source_uris: Annotated[List[URIRef], WithPredicate(schema.URI.source)] = Field(default_factory=list)
    contributor_uris: Annotated[List[URIRef], WithPredicate(schema.URI.contributor)] = Field(default_factory=list)
    superseded_by_uri: Annotated[Optional[URIRef], WithPredicate(schema.URI.supersededBy)] = None
    equivalent_uris: Annotated[List[URIRef], WithPredicate(URIRef("http://www.w3.org/2002/07/owl#equivalentClass"))] = Field(default_factory=list)

    # Metadata tracked by the system (not necessarily in the RDF graph predicates)
    pending: bool = False
    retired: bool = False
    layer: str = "core"
    term_id: Optional[str] = None # Legacy support for tests

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        """The short ID (e.g. 'Hotel') extracted from the full URI."""
        if self.term_id:
            return self.term_id
        uri_str = str(self.uri)
        if uri_str.startswith(schema.VOCABURI):
            return uri_str[len(schema.VOCABURI) :]
        if ".org/" in uri_str:
            return uri_str.split(".org/")[-1]
        return uri_str.split("/")[-1].split("#")[-1]

    def __str__(self) -> str:
        return self.id

    @property
    def expanded(self) -> ExpandedBool:
        return ExpandedBool(1)

    @property
    def examples(self) -> List[Any]:
        import SchemaExamples.schemaexamples as schemaexamples
        return schemaexamples.SchemaExamples.examplesForTerm(self.id)
    @property
    def termType(self) -> Optional[str]:
        if isinstance(self, SdoProperty):
            return "Property"
        if isinstance(self, SdoDataType) or self.id == "DataType":
            return "Datatype"
        if isinstance(self, SdoEnumeration) or self.id == "Enumeration":
            return "Enumeration"
        if isinstance(self, SdoEnumerationvalue):
            return "Enumerationvalue"
        if isinstance(self, SdoReference):
            return "Reference"
        if isinstance(self, SdoType):
            return "Type"
        return None

    @property
    def superseded(self) -> bool:
        return bool(self.superseded_by_uri)

    @property
    def supersededBy(self) -> str:
        return str(self.superseded_by_uri).split("/")[-1] if self.superseded_by_uri else ""

    @property
    def supersedes(self) -> List[str]:
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        return sorted([
            t.id for t in registry.all_terms().values() 
            if getattr(t, "superseded_by_uri", None) == self.uri
        ])

    @property
    def sources(self) -> List[str]:
        return [str(u) for u in self.source_uris]

    @property
    def extLayer(self) -> str:
        return self.layer if self.layer and self.layer != "core" else ""

    @property
    def equivalents(self) -> TermList:
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        eqs = [t for u in self.equivalent_uris if (t := registry.get(u)) and t.id != self.id]
        if isinstance(self, SdoProperty):
            for u in getattr(self, "equivalent_property_uris", []):
                if (t := registry.get(u)):
                    eqs.append(t)
        return TermList(sorted(list(set(eqs)), key=lambda x: x.id))

    @equivalents.setter
    def equivalents(self, value: List[Any]) -> None:
        from rdflib import URIRef
        self.equivalent_uris = [URIRef(getattr(t, "uri", str(t))) for t in value]

    @property
    def acknowledgements(self) -> TermList:
        import SchemaTerms.sdocollaborators as sdocollaborators
        acks = []
        for uri in self.contributor_uris:
            cont = sdocollaborators.collaborator.getContributor(str(uri))
            if cont:
                acks.append(cont)
        return TermList(sorted(acks, key=lambda t: getattr(t, "title", "")))

    @property
    def supers(self) -> TermList:
        if not hasattr(self, "super_uris"):
            return TermList()
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        res = []
        for u in getattr(self, "super_uris", []):
            t = registry.get(u)
            if not t and "schema.org" in str(u):
                stem = str(u).split("/")[-1].split("#")[-1]
                t = self.__class__(id=stem, uri=str(u), label=stem)
            if t: res.append(t)
        return TermList(sorted(res, key=lambda x: x.id))

    @supers.setter
    def supers(self, value: List[Any]) -> None:
        from rdflib import URIRef
        self.super_uris = [URIRef(getattr(t, "uri", str(t))) for t in value]

    @property
    def subs(self) -> TermList:
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        res = [
            t for t in registry.all_terms().values()
            if isinstance(t, type(self)) and self.uri in getattr(t, "super_uris", [])
        ]
        return TermList(sorted(res, key=lambda x: x.id))

    @subs.setter
    def subs(self, value: List[Any]) -> None:
        pass  # subs is dynamically computed from super_uris on subclasses

    @property
    def termStack(self) -> TermList:
        stack = []
        for sup in self.supers:
            if sup not in stack:
                stack.append(sup)
                for ancestor in getattr(sup, "termStack", []):
                    if ancestor not in stack:
                        stack.append(ancestor)
        return TermList(stack)

    @property
    def superPaths(self) -> List[List[Any]]:
        if self.id == "Thing":
            return [[self]]
        if isinstance(self, SdoEnumerationvalue):
            parent = getattr(self, "enumerationParent", None)
            paths = getattr(parent, "superPaths", [[]])
            return [TermList() for p in paths if p and getattr(p[0], "id", "") == "Enumeration"] or [TermList()]
        if not self.supers:
            return [[self]]
        paths = []
        for parent in self.supers:
            for path in getattr(parent, "superPaths", []):
                paths.append(path + [self])
        return paths

    def __hash__(self):
        return hash(self.uri)
    
    def __eq__(self, other):
        if not isinstance(other, SdoTerm):
            return False
        return self.uri == other.uri

class SdoType(SdoTerm):
    """Model for Schema.org Classes."""
    rdf_type: ClassVar[URIRef] = RDFS.Class
    super_uris: Annotated[List[URIRef], WithPredicate(RDFS.subClassOf)] = Field(default_factory=list)

    @property
    def properties(self) -> TermList:
        from .registry import TermRegistry
        from .models import SdoProperty
        registry = TermRegistry.get_instance()
        terms = [t for t in registry.all_terms().values() if isinstance(t, SdoProperty) and self.uri in getattr(t, "domain_uris", [])]
        return TermList(sorted(terms, key=lambda x: x.id))

    @property
    def allproperties(self) -> TermList:
        props = sorted(list(set(self.properties) | set([p for t in self.termStack for p in getattr(t, "properties", [])])), key=lambda x: x.id)
        return TermList(props)

    @property
    def expectedTypeFor(self) -> TermList:
        from .registry import TermRegistry
        from .models import SdoProperty
        registry = TermRegistry.get_instance()
        terms = [t for t in registry.all_terms().values() if isinstance(t, SdoProperty) and self.uri in getattr(t, "range_uris", [])]
        return TermList(sorted(terms, key=lambda x: x.id))

class SdoProperty(SdoTerm):
    """Model for Schema.org Properties."""
    rdf_type: ClassVar[URIRef] = RDF.Property
    
    domain_uris: Annotated[List[URIRef], WithPredicate(schema.URI.domainIncludes)] = Field(default_factory=list)
    range_uris: Annotated[List[URIRef], WithPredicate(schema.URI.rangeIncludes)] = Field(default_factory=list)
    inverse_uri: Annotated[Optional[URIRef], WithPredicate(schema.URI.inverseOf)] = None
    super_uris: Annotated[List[URIRef], WithPredicate(RDFS.subPropertyOf)] = Field(default_factory=list)
    equivalent_property_uris: Annotated[List[URIRef], WithPredicate(URIRef("http://www.w3.org/2002/07/owl#equivalentProperty"))] = Field(default_factory=list)

    @property
    def domainIncludes(self) -> TermList:
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        res = []
        for u in self.domain_uris:
            t = registry.get(u)
            if not t and "schema.org" in str(u):
                stem = str(u).split("/")[-1].split("#")[-1]
                t = SdoType(id=stem, uri=str(u), label=stem)
            if t: res.append(t)
        return TermList(sorted(res, key=lambda x: x.id))

    @domainIncludes.setter
    def domainIncludes(self, value: List[Any]) -> None:
        from rdflib import URIRef
        self.domain_uris = [URIRef(getattr(t, "uri", str(t))) for t in value]

    @property
    def rangeIncludes(self) -> TermList:
        from .registry import TermRegistry
        registry = TermRegistry.get_instance()
        res = []
        for u in self.range_uris:
            t = registry.get(u)
            if not t and "schema.org" in str(u):
                stem = str(u).split("/")[-1].split("#")[-1]
                t = SdoType(id=stem, uri=str(u), label=stem)
            if t: res.append(t)
        return TermList(sorted(res, key=lambda x: x.id))

    @rangeIncludes.setter
    def rangeIncludes(self, value: List[Any]) -> None:
        from rdflib import URIRef
        self.range_uris = [URIRef(getattr(t, "uri", str(t))) for t in value]

    @property
    def domains(self) -> List["SdoType"]:
        return self.domainIncludes

    @property
    def ranges(self) -> List["SdoType"]:
        return self.rangeIncludes

    @property
    def inverseOf(self) -> Optional["SdoProperty"]:
        return self.inverse

    def getInverseOf(self) -> Optional["SdoProperty"]:
        return self.inverse

    @property
    def inverse(self) -> Optional["SdoProperty"]:
        from .registry import TermRegistry
        from .models import SdoProperty
        registry = TermRegistry.get_instance()
        res = None
        if self.inverse_uri:
            res = registry.get(self.inverse_uri)
        if not res:
            for t in registry.all_terms().values():
                if isinstance(t, SdoProperty) and getattr(t, "inverse_uri", None) == self.uri:
                    res = t
                    break
        return res

class SdoDataType(SdoType):
    """Model for Schema.org Data Types."""
    pass

class SdoEnumeration(SdoType):
    """Model for Schema.org Enumerations."""
    @property
    def supers(self) -> TermList:
        if self.id == "Enumeration":
            return TermList()
        res = [t for t in super().supers if isinstance(t, self.__class__) or getattr(t, "id", "") == "Enumeration"]
        return TermList(res)

    @property
    def enumerationMembers(self) -> TermList:
        from .registry import TermRegistry
        from .models import SdoEnumerationvalue
        registry = TermRegistry.get_instance()
        res = [
            t for t in registry.all_terms().values() 
            if isinstance(t, SdoEnumerationvalue) and getattr(t, "enumeration_uri", None) and str(getattr(t, "enumeration_uri", "")).split("/")[-1] == self.id
        ]
        return TermList(sorted(res, key=lambda x: x.id))

class SdoEnumerationvalue(SdoTerm):
    """Model for Schema.org Enumeration Values."""
    enumeration_uri: Optional[URIRef] = None
    @property
    def enumerationParent(self) -> Optional["SdoEnumeration"]:
        if not self.enumeration_uri:
            return None
        from .registry import TermRegistry
        from .models import SdoEnumeration
        t = TermRegistry.get_instance().get(self.enumeration_uri)
        return t if isinstance(t, SdoEnumeration) else None

class SdoReference(SdoTerm):
    """Model for external references."""
    pass
