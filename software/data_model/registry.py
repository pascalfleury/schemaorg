#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Dict, Optional
from rdflib import URIRef

class TermRegistry:
    """Central registry for all Schema.org terms identified by their full URIs."""
    
    _instance: Optional["TermRegistry"] = None

    def __init__(self):
        self._terms: Dict[URIRef, "SdoTerm"] = {}

    @classmethod
    def get_instance(cls) -> "TermRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """Clears the global registry instance. Useful for testing."""
        cls._instance = None

    def register(self, term: "SdoTerm"):
        """Adds a term to the registry."""
        self._terms[term.uri] = term

    def get(self, uri: URIRef) -> Optional["SdoTerm"]:
        """Retrieves a term by its full URI."""
        return self._terms.get(uri)

    def all_terms(self) -> Dict[URIRef, "SdoTerm"]:
        """Returns all registered terms."""
        return self._terms.copy()

    def __len__(self) -> int:
        return len(self._terms)
