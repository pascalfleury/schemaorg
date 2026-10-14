#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Pydantic-RDF models and Vocabulary container for schema.org."""

from schemaorg.model.loader import VocabularyLoader
from schemaorg.model.terms import (
    DataType,
    EnumerationValue,
    SchemaProperty,
    SchemaTerm,
    SchemaType,
)
from schemaorg.model.vocabulary import Vocabulary
from schemaorg.so_uri import SDO, SoUri

__all__ = [
    "DataType",
    "EnumerationValue",
    "SDO",
    "SchemaProperty",
    "SchemaTerm",
    "SchemaType",
    "SoUri",
    "Vocabulary",
    "VocabularyLoader",
]
