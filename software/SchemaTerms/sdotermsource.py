#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Union, NamedTuple

import rdflib
import util.schema as schema
from software.data_model.bridge import *

log: logging.Logger = logging.getLogger(__name__)

# Core re-export from the new Bridge
# SdoTermSource is already exported via *

class ProtoAndRoot(NamedTuple):
    protocol: Optional[str]
    root: Optional[str]

# Utility functions required by the rest of the project
def toFullId(term_id: str) -> str:
    """Converts a short ID or prefixed ID to a full URI."""
    if term_id.startswith(("http:", "https:")):
        return term_id
    if ":" in term_id:
        prefix, name = term_id.split(":", 1)
        # Attempt to resolve prefix via rdflib if graph is loaded
        if SdoTermSource._graph:
            for pref, pth in SdoTermSource._graph.namespaces():
                if str(pref) == prefix:
                    return f"{pth}{name}"
        return term_id
    return f"{schema.VOCABURI}{term_id}"

def uri2id(uri: str) -> str:
    """Extracts the ID from a URI."""
    if uri.startswith(schema.VOCABURI):
        return uri[len(schema.VOCABURI):]
    if str(uri).endswith("/"):
        return str(uri)
    return str(uri).split("/")[-1].split("#")[-1]

def prefixedIdFromUri(uri: str) -> str:
    """Converts a URI to prefix:id format."""
    if SdoTermSource._graph:
        for pref, pth in SdoTermSource._graph.namespaces():
            if str(uri).startswith(str(pth)):
                p = str(pref) or "schema"
                return f"{p}:{str(uri)[len(str(pth)):]}"
    return str(uri)

def layerFromUri(uri: str) -> Optional[str]:
    """Determines the layer from a URI."""
    if not uri: return None
    uri_str = str(uri)
    if "pending" in uri_str: return "pending"
    if "attic" in uri_str: return "attic"
    if uri_str.startswith("https://schema.org/"):
        return None
    match = re.match(r"https?://([^.]+)\.schema\.org/", uri_str)
    if match:
        return match.group(1)
    return None

def uriFromLayer(layer: Optional[str] = None) -> str:
    """Returns the base URI for a layer."""
    if not layer or layer == "core":
        return "https://schema.org"
    return f"https://{layer}.schema.org"

def prefixFromUri(uri: str) -> Optional[str]:
    if not uri: return None
    if SdoTermSource._graph:
        for pref, pth in SdoTermSource._graph.namespaces():
            if str(uri).startswith(str(pth)):
                return str(pref) or "schema"
    return None

def uriForPrefix(prefix: str) -> Optional[rdflib.URIRef]:
    if not prefix: return None
    if SdoTermSource._graph:
        for pref, pth in SdoTermSource._graph.namespaces():
            if str(pref) == prefix:
                return rdflib.URIRef(pth)
    return None

def getProtoAndRoot(uri: str) -> ProtoAndRoot:
    if not uri: return ProtoAndRoot(None, None)
    match = re.match(r"^(https?://)(.*)", uri)
    if match:
        return ProtoAndRoot(match.group(1), match.group(2))
    return ProtoAndRoot(None, None)

def uriWrap(identity_str: str) -> str:
    """Wraps identity in brackets for SPARQL if it's a URI."""
    if identity_str.startswith(("http://", "https://")):
        return f"<{identity_str}>"
    return identity_str

# Initialization bridge
def bindNameSpaces(graph: rdflib.Graph) -> None:
    # Most namespaces are now handled by rdflib or explicitly in the loader
    pass
