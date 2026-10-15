#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Vocabulary term-count renderer (JSON and JSONP)."""

import functools
import json
from typing import Any, Dict

from schemaorg.model import Vocabulary
from schemaorg.sdo_uri import SDO
from schemaorg.version import VersionItem
from util.sort_dict import sort_dict


class CountsRenderer:
    """Term counts per kind, as JSON and as the JSONP snippet used by the docs."""

    def __init__(self, vocab: Vocabulary, version: VersionItem) -> None:
        self.vocab = vocab
        self.version = version

    @functools.cached_property
    def counts(self) -> Dict[str, Any]:
        vocab = self.vocab
        dt_roots = {
            u
            for u in vocab.datatypes
            if u in vocab.types and u != SDO.DataType
        }
        dt_classes = {
            u
            for u in vocab.types
            if u in dt_roots
            or any(a in dt_roots for a in vocab.ancestors.get(u, ()))
        }
        classes = len(vocab.types)
        properties = len(vocab.properties)
        enums = len(vocab.enumerations)
        enumvals = len(vocab.enum_values)
        dt_literals = len(vocab.datatypes.keys() - vocab.types.keys())
        datatypes = len(dt_classes) + dt_literals
        types = classes - 1 - enums - len(dt_classes)

        return {
            "Type": types,
            "Property": properties,
            "Datatype": datatypes,
            "Enumeration": enums,
            "Enumerationvalue": enumvals,
            "All": types + properties + datatypes + enums + enumvals,
            "schemaorgversion": self.version.number(),
        }

    def json(self) -> str:
        return json.dumps(sort_dict(self.counts))

    def jsonp(self) -> str:
        return f"\n    COUNTS = '{self.json()}';\n\n    insertschemacounts ( COUNTS );\n    "
