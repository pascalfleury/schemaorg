#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Module that handles the schema.org version information and global constants."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, NamedTuple
import re

import rdflib

import software

import util.paths as paths
from util.sort_dict import sort_dict

VOCABURI: str = "https://schema.org/"
URI: rdflib.Namespace = rdflib.Namespace(VOCABURI)
DATATYPEURI: Optional[rdflib.URIRef] = None
ENUMERATIONURI: Optional[rdflib.URIRef] = None
THINGURI: Optional[rdflib.URIRef] = None


def setVocabUri(uri: Optional[str] = None) -> None:
    global VOCABURI, URI, DATATYPEURI, ENUMERATIONURI, THINGURI
    VOCABURI = uri or "https://schema.org/"
    URI = rdflib.Namespace(VOCABURI)
    DATATYPEURI = rdflib.URIRef(f"{VOCABURI}DataType")
    ENUMERATIONURI = rdflib.URIRef(f"{VOCABURI}Enumeration")
    THINGURI = rdflib.URIRef(f"{VOCABURI}Thing")


setVocabUri()  # Initialize


class constants:
    SITENAME: str = "Schema.org"
    DOCSDOCSDIR: str = "/docs"
    TERMDOCSDIR: str = "/docs"
    HANDLER_TEMPLATE: str = "handlers-template.yaml"
    HANDLER_FILE: str = "handlers.yaml"
    RELEASE_DIR: str = "software/site/releases"
    HOMEPAGE: str = "https://schema.org"


class config:
    BUILDOPTS: List[str] = []
    TERMS: List[str] = []
    PAGES: List[str] = []
    FILES: List[str] = []
    OUTPUTDIR: str = "software/site"


def hasOpt(opt: str) -> bool:
    """Return true if `opt` is among the build options"""
    return opt in config.BUILDOPTS


def getOutputDir() -> str:
    return config.OUTPUTDIR


def getDocsOutputDir() -> str:
    return str(Path(config.OUTPUTDIR) / "docs")


VERSION_DATA: Optional[Dict[str, Any]] = None


def getVersionData() -> Dict[str, Any]:
    global VERSION_DATA
    if VERSION_DATA is None:
        VERSION_DATA = json.loads(
            paths.DefaultInputLayout()
            .domain_file(paths.Domain.ROOT, "versions.json")
            .read_text()
        )
    assert VERSION_DATA is not None
    return VERSION_DATA


def getVersion() -> str:
    return str(getVersionData()["schemaversion"])


def getVersionDate(ver: str) -> Optional[str]:
    ret: Optional[str] = getVersionData()["releaseLog"].get(ver)
    return ret


def getCurrentVersionDate() -> Optional[str]:
    return getVersionDate(getVersion())


def setVersion(ver: str, date: str) -> None:
    versiondata: Dict[str, Any] = getVersionData()
    versiondata["schemaversion"] = ver
    versiondata["releaseLog"][ver] = date

    logs: Dict[str, str] = versiondata["releaseLog"]
    versiondata["releaseLog"] = dict(
        sorted(logs.items(), key=lambda x: float(x[0]), reverse=True)
    )

    paths.DefaultInputLayout().domain_file(
        paths.Domain.ROOT, "versions.json"
    ).write_text(json.dumps(sort_dict(versiondata), indent=4))


class ProtoAndRoot(NamedTuple):
    protocol: Optional[str]
    root: Optional[str]

def toFullId(term_id: str) -> str:
    """Converts a short ID or prefixed ID to a full URI."""
    if term_id.startswith(("http:", "https:")):
        return term_id
    if ":" in term_id:
        prefix, name = term_id.split(":", 1)
        from software.data_model.registry import TermRegistry
        graph = getattr(TermRegistry.get_instance(), "_graph", None)
        if graph:
            for pref, pth in graph.namespaces():
                if str(pref) == prefix:
                    return f"{pth}{name}"
        return term_id
    return f"{VOCABURI}{term_id}"

def uri2id(uri: str) -> str:
    """Extracts the ID from a URI."""
    if uri.startswith(VOCABURI):
        return uri[len(VOCABURI):]
    if str(uri).endswith("/"):
        return str(uri)
    return str(uri).split("/")[-1].split("#")[-1]

def prefixedIdFromUri(uri: str) -> str:
    """Converts a URI to prefix:id format."""
    from software.data_model.registry import TermRegistry
    graph = getattr(TermRegistry.get_instance(), "_graph", None)
    if graph:
        for pref, pth in graph.namespaces():
            if str(uri).startswith(str(pth)):
                p = str(pref) or "schema"
                return f"{p}:{str(uri)[len(str(pth)):]}"
    return str(uri)

def layerFromUri(uri: Optional[str]) -> Optional[str]:
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
    from software.data_model.registry import TermRegistry
    graph = getattr(TermRegistry.get_instance(), "_graph", None)
    if graph:
        for pref, pth in graph.namespaces():
            if str(uri).startswith(str(pth)):
                return str(pref) or "schema"
    return None

def uriForPrefix(prefix: str) -> Optional[rdflib.URIRef]:
    if not prefix: return None
    from software.data_model.registry import TermRegistry
    graph = getattr(TermRegistry.get_instance(), "_graph", None)
    if graph:
        for pref, pth in graph.namespaces():
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
