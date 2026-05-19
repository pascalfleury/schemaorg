#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Annotated, List, Optional, Union, ClassVar
from pydantic import Field, ConfigDict, computed_field
from pydantic_rdf import BaseRdfModel, WithPredicate
from rdflib import RDFS, RDF, URIRef
import util.schema as schema
from .type_map import SdoTermType

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

    @computed_field
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

    @property
    def termType(self) -> Optional[SdoTermType]:
        if isinstance(self, SdoProperty):
            return SdoTermType.PROPERTY
        if isinstance(self, SdoDataType):
            return SdoTermType.DATATYPE
        if isinstance(self, SdoEnumeration):
            return SdoTermType.ENUMERATION
        if isinstance(self, SdoEnumerationvalue):
            return SdoTermType.ENUMERATIONVALUE
        if isinstance(self, SdoReference):
            return SdoTermType.REFERENCE
        if isinstance(self, SdoType):
            return SdoTermType.TYPE
        return None

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

class SdoProperty(SdoTerm):
    """Model for Schema.org Properties."""
    rdf_type: ClassVar[URIRef] = RDF.Property
    
    domain_uris: Annotated[List[URIRef], WithPredicate(schema.URI.domainIncludes)] = Field(default_factory=list)
    range_uris: Annotated[List[URIRef], WithPredicate(schema.URI.rangeIncludes)] = Field(default_factory=list)
    inverse_uri: Annotated[Optional[URIRef], WithPredicate(schema.URI.inverseOf)] = None
    super_uris: Annotated[List[URIRef], WithPredicate(RDFS.subPropertyOf)] = Field(default_factory=list)
    equivalent_property_uris: Annotated[List[URIRef], WithPredicate(URIRef("http://www.w3.org/2002/07/owl#equivalentProperty"))] = Field(default_factory=list)

class SdoDataType(SdoType):
    """Model for Schema.org Data Types."""
    pass

class SdoEnumeration(SdoType):
    """Model for Schema.org Enumerations."""
    pass

class SdoEnumerationvalue(SdoTerm):
    """Model for Schema.org Enumeration Values."""
    enumeration_uri: Optional[URIRef] = None

class SdoReference(SdoTerm):
    """Model for external references."""
    pass
