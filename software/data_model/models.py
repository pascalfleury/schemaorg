#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Annotated, List, Optional, Union, ClassVar, Any, Dict, Set
from pydantic import Field, ConfigDict, computed_field, field_validator, PrivateAttr
from pydantic_rdf import BaseRdfModel, WithPredicate
from rdflib import RDFS, RDF, URIRef, Namespace
import SchemaExamples.schemaexamples as schemaexamples
from SchemaTerms.localmarkdown import Markdown
import SchemaTerms.sdocollaborators as sdocollaborators
import util.schema as schema
from . import registry
from .type_map import SdoTermType

SCHEMA = Namespace("https://schema.org/")

class TermList(list):
    """List subclass that adds a convenience .ids getter for backward compatibility."""
    @property
    def ids(self) -> List[str]:
        return [getattr(t, "id", str(t)) for t in self]
    @property
    def terms(self) -> List[Any]:
        return self

class SdoTerm(BaseRdfModel):
    """Base model for all Schema.org terms."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    rdf_type: ClassVar[URIRef] = RDFS.Resource

    label: Annotated[str, WithPredicate(RDFS.label)]
    comment: Annotated[Optional[str], WithPredicate(RDFS.comment)] = ""

    @field_validator('comment', mode='before')
    @classmethod
    def convert_markdown(cls, v: Optional[str]) -> Optional[str]:
        if v:
            parsed = Markdown.parse(v)
            return parsed.strip() if parsed else parsed
        return v
    isPartOf: Annotated[Optional[URIRef], WithPredicate(SCHEMA.isPartOf)] = None
    
    source_uris: Annotated[List[URIRef], WithPredicate(SCHEMA.source)] = Field(default_factory=list)
    contributor_uris: Annotated[List[URIRef], WithPredicate(SCHEMA.contributor)] = Field(default_factory=list)
    superseded_by_uri: Annotated[Optional[URIRef], WithPredicate(SCHEMA.supersededBy)] = None
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
        for prefix in ("https://schema.org/", "http://schema.org/"):
            if uri_str.startswith(prefix):
                return uri_str[len(prefix) :]
        return uri_str

    def __str__(self) -> str:
        return self.id

    @property
    def expanded(self) -> bool:
        return True

    @property
    def examples(self) -> List[Any]:
        return schemaexamples.SchemaExamples.examplesForTerm(self.id)
    @property
    def termType(self) -> Optional[str]:
        if not schema.isSchemaUri(self.uri):
            return "Reference"
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
        reg = registry.TermRegistry.get_instance()
        return sorted([
            t.id for t in reg.all_terms().values() 
            if getattr(t, "superseded_by_uri", None) == self.uri
        ])

    @property
    def sources(self) -> List[str]:
        return sorted([str(u) for u in self.source_uris])

    @property
    def extLayer(self) -> str:
        return self.layer if self.layer and self.layer != "core" else ""

    @property
    def equivalents(self) -> TermList:
        term_registry = registry.TermRegistry.get_instance()
        eqs = []
        
        def get_or_create_ref(u: URIRef) -> SdoTerm:
            t = term_registry.get(u)
            if t:
                return t
            uri_str = str(u)
            label = schema.prefixedIdFromUri(uri_str)
            if label == uri_str:
                if ".org/" in uri_str:
                    label = uri_str.split(".org/")[-1]
                else:
                    label = uri_str.split("/")[-1].split("#")[-1]
            ref = SdoReference(uri=u, label=label)
            term_registry.register(ref)
            return ref

        for u in self.equivalent_uris:
            if u == self.uri:
                continue
            eqs.append(get_or_create_ref(u))
            
        if isinstance(self, SdoProperty):
            for u in getattr(self, "equivalent_property_uris", []):
                eqs.append(get_or_create_ref(u))
                
        return TermList(sorted(list(set(eqs)), key=lambda x: schema.prefixedIdFromUri(str(x.uri))))

    @equivalents.setter
    def equivalents(self, value: List[Any]) -> None:
        self.equivalent_uris = [URIRef(getattr(t, "uri", str(t))) for t in value]

    @property
    def acknowledgements(self) -> TermList:
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
        term_registry = registry.TermRegistry.get_instance()
        res = []
        for u in getattr(self, "super_uris", []):
            t = term_registry.get(u)
            if not t:
                uri_str = str(u)
                if schema.isSchemaUri(uri_str):
                    stem = uri_str.split("/")[-1].split("#")[-1]
                    t = self.__class__(id=stem, uri=str(u), label=stem)
                else:
                    label = schema.prefixedIdFromUri(uri_str)
                    t = SdoReference(uri=u, label=label)
                    term_registry.register(t)
            elif not schema.isSchemaUri(u):
                label = schema.prefixedIdFromUri(str(u))
                if label != str(u) and hasattr(t, "label"):
                    t.label = label
            if t: res.append(t)
        return TermList(sorted(res, key=lambda x: x.id))

    @supers.setter
    def supers(self, value: List[Any]) -> None:
        self.super_uris = [URIRef(getattr(t, "uri", str(t))) for t in value]

    @property
    def subs(self) -> TermList:
        term_registry = registry.TermRegistry.get_instance()
        
        is_type = isinstance(self, (SdoType, SdoDataType))
        is_prop = isinstance(self, SdoProperty)
        
        res = []
        for t in term_registry.all_terms().values():
            if is_type:
                compatible = isinstance(t, (SdoType, SdoDataType, SdoEnumerationvalue))
            elif is_prop:
                compatible = isinstance(t, SdoProperty)
            else:
                compatible = False
                
            if compatible and self.uri in getattr(t, "super_uris", []):
                res.append(t)
                
        if isinstance(self, SdoDataType):
            g = getattr(term_registry, "_graph", None)
            if g is not None:
                for subj in g.subjects(RDF.type, self.uri):
                    term = term_registry.get(subj)
                    if term and not isinstance(term, SdoReference) and schema.isSchemaUri(term.uri):
                        res.append(term)
                
        return TermList(sorted(list(set(res)), key=lambda x: x.id))

    @subs.setter
    def subs(self, value: List[Any]) -> None:
        pass  # subs is dynamically computed from super_uris on subclasses

    @property
    def termStack(self) -> TermList:
        raw_stack = []
        for sup in self.supers:
            if isinstance(sup, SdoReference) or getattr(sup, "termType", None) == "Reference":
                continue
            raw_stack.append(sup)
            for ancestor in getattr(sup, "termStack", []):
                if not isinstance(ancestor, SdoReference):
                    raw_stack.append(ancestor)
        
        stack = []
        for t in reversed(raw_stack):
            if t not in stack:
                stack.append(t)
        return TermList(list(reversed(stack)))

    @property
    def _allproperties_stack(self) -> TermList:
        return self.termStack

    @property
    def superPaths(self) -> List[TermList]:
        if self.id == "Thing":
            return [TermList([self])]
        if self.id == "DataType":
            return [TermList([self])]

        term_registry = registry.TermRegistry.get_instance()

        pstacks: List[List[Any]] = []
        cstack: List[Any] = []
        pstacks.append(cstack)

        def _getParentPaths(curr: Any, cur_stack: List[Any]) -> None:
            cur_stack.insert(0, curr)
            tmpStacks: List[List[Any]] = [cur_stack]
            super_terms: List[Any] = []
            for s in getattr(curr, "supers", []):
                if (
                    schema.isSchemaUri(s.uri)
                    and getattr(s, "termType", None) != "Reference"
                    and not isinstance(s, SdoReference)
                    and s != curr
                ):
                    super_terms.append(s)
            if isinstance(curr, SdoEnumerationvalue) and getattr(curr, "enumerationParent", None):
                ep = curr.enumerationParent
                if ep not in super_terms:
                    super_terms.append(ep)

            if super_terms:
                for i in range(1, len(super_terms)):
                    t = cur_stack[:]
                    tmpStacks.append(t)
                    pstacks.append(t)
                for x, parent in enumerate(super_terms):
                    _getParentPaths(parent, tmpStacks[x])

        _getParentPaths(self, cstack)

        inserts: List[Any] = []
        if isinstance(self, SdoProperty):
            thing = term_registry.get_by_id("Thing")
            prop = term_registry.get_by_id("Property")
            inserts = [t for t in [prop, thing] if t]
        elif isinstance(self, SdoDataType) and self.id != "DataType":
            dt = term_registry.get_by_id("DataType")
            if dt:
                inserts = [dt]
        elif isinstance(self, SdoType):
            base = pstacks[0][0]
            if base and (isinstance(base, SdoDataType) or getattr(base, "id", None) == "DataType"):
                dt = term_registry.get_by_id("DataType")
                if dt:
                    inserts = [dt]
            elif base and base.id != "Thing":
                thing = term_registry.get_by_id("Thing")
                if thing:
                    inserts = [thing]

        for ins in inserts:
            for s in pstacks:
                s.insert(0, ins)

        for s in pstacks:
            if s and s[0].id not in ("Thing", "DataType") and not isinstance(self, (SdoProperty, SdoDataType)):
                thing = term_registry.get_by_id("Thing")
                if thing and thing not in s:
                    s.insert(0, thing)

        return [TermList(p) for p in pstacks]

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
        term_registry = registry.TermRegistry.get_instance()
        terms = [t for t in term_registry.all_terms().values() if isinstance(t, SdoProperty) and self.uri in getattr(t, "domain_uris", [])]
        return TermList(sorted(terms, key=lambda x: x.id))

    @property
    def allproperties(self) -> TermList:
        props = sorted(list(set(self.properties) | set([p for t in self._allproperties_stack for p in getattr(t, "properties", [])])), key=lambda x: x.id)
        return TermList(props)

    @property
    def expectedTypeFor(self) -> TermList:
        term_registry = registry.TermRegistry.get_instance()
        terms = [t for t in term_registry.all_terms().values() if isinstance(t, SdoProperty) and self.uri in getattr(t, "range_uris", [])]
        return TermList(sorted(terms, key=lambda x: x.id))

class SdoProperty(SdoTerm):
    """Model for Schema.org Properties."""
    rdf_type: ClassVar[URIRef] = RDF.Property
    
    domain_uris: Annotated[List[URIRef], WithPredicate(SCHEMA.domainIncludes)] = Field(default_factory=list)
    range_uris: Annotated[List[URIRef], WithPredicate(SCHEMA.rangeIncludes)] = Field(default_factory=list)
    inverse_uri: Annotated[Optional[URIRef], WithPredicate(SCHEMA.inverseOf)] = None
    super_uris: Annotated[List[URIRef], WithPredicate(RDFS.subPropertyOf)] = Field(default_factory=list)
    equivalent_property_uris: Annotated[List[URIRef], WithPredicate(URIRef("http://www.w3.org/2002/07/owl#equivalentProperty"))] = Field(default_factory=list)

    @property
    def domainIncludes(self) -> TermList:
        term_registry = registry.TermRegistry.get_instance()
        res = []
        for u in self.domain_uris:
            t = term_registry.get(u)
            if not t and schema.isSchemaUri(u):
                stem = str(u).split("/")[-1].split("#")[-1]
                t = SdoType(id=stem, uri=str(u), label=stem)
            if t: res.append(t)
        return TermList(sorted(res, key=lambda x: x.id))

    @domainIncludes.setter
    def domainIncludes(self, value: List[Any]) -> None:
        self.domain_uris = [URIRef(getattr(t, "uri", str(t))) for t in value]

    @property
    def rangeIncludes(self) -> TermList:
        term_registry = registry.TermRegistry.get_instance()
        res = []
        for u in self.range_uris:
            t = term_registry.get(u)
            if not t and schema.isSchemaUri(u):
                stem = str(u).split("/")[-1].split("#")[-1]
                t = SdoType(id=stem, uri=str(u), label=stem)
            if t: res.append(t)
        return TermList(sorted(res, key=lambda x: x.id))

    @rangeIncludes.setter
    def rangeIncludes(self, value: List[Any]) -> None:
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
        term_registry = registry.TermRegistry.get_instance()
        res = None
        if self.inverse_uri:
            res = term_registry.get(self.inverse_uri)
        if not res:
            for t in term_registry.all_terms().values():
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
    def termStack(self) -> TermList:
        if not self.properties:
            return TermList()
        return super().termStack

    @property
    def _allproperties_stack(self) -> TermList:
        return super().termStack

    @property
    def enumerationMembers(self) -> TermList:
        term_registry = registry.TermRegistry.get_instance()
        res = [
            t for t in term_registry.all_terms().values() 
            if isinstance(t, SdoEnumerationvalue) and any(str(u).split("/")[-1] == self.id for u in t.enumeration_uris)
        ]
        return TermList(sorted(res, key=lambda x: x.id))

class SdoEnumerationvalue(SdoTerm):
    """Model for Schema.org Enumeration Values."""
    enumeration_uris: List[URIRef] = Field(default_factory=list)
    # Added for backward compatibility with previous codebase: dual-typed terms (e.g. DietNutrition) also have subClassOf (super_uris)
    super_uris: Annotated[List[URIRef], WithPredicate(RDFS.subClassOf)] = Field(default_factory=list)

    @property
    def enumeration_uri(self) -> Optional[URIRef]:
        return self.enumeration_uris[0] if self.enumeration_uris else None

    @property
    def enumerationParent(self) -> Optional["SdoEnumeration"]:
        if not self.enumeration_uri:
            return None
        t = registry.TermRegistry.get_instance().get(self.enumeration_uri)
        return t if isinstance(t, SdoEnumeration) else None

class SdoReference(SdoTerm):
    """Model for external references."""
    pass
