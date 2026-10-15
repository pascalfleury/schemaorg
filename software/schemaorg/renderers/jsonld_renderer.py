#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""JSON-LD context and class-tree renderer."""

import functools
import json
import logging
from typing import Any, Dict, Optional, Set

import rdflib
from rdflib.term import URIRef
from schemaorg.model import Vocabulary
from schemaorg.sdo_uri import SCHEMA_URL, SDO, SdoUri
import SchemaTerms.localmarkdown as localmarkdown
import util.pretty_logger as pretty_logger
from util.sort_dict import sort_dict
import util.textutils as textutils

log: logging.Logger = logging.getLogger(__name__)

# Published JSON-LD context keeps the legacy http scheme.
SDO_HTTP: rdflib.Namespace = rdflib.Namespace(SCHEMA_URL._replace(scheme="http").geturl())


class JsonLdRenderer:
    """JSON-LD context (graph prefixes plus term aliases) and class tree."""

    def __init__(self, graph: rdflib.Graph, vocab: Vocabulary) -> None:
        self.graph = graph
        self.vocab = vocab

    @functools.cache
    def context(self) -> str:
        schema_http_uri = str(SDO_HTTP)
        with pretty_logger.BlockLog(
            message="Creating JSON-LD context", logger=log
        ):
            json_context: Dict[str, Any] = {
                "type": "@type",
                "id": "@id",
                "HTML": {"@id": "rdf:HTML"},
                "@vocab": schema_http_uri,
            }

            done_namespaces: Set[str] = set()
            for pref, path in self.graph.namespaces():
                pref_str = str(pref)
                if pref_str and pref_str not in done_namespaces:
                    done_namespaces.add(pref_str)
                    if pref_str == "schema":
                        path = schema_http_uri
                    if pref_str == "geo":
                        continue
                    json_context[pref_str] = str(path)

            for term in self.vocab.all_terms().values():
                json_context[term.id] = {"@id": f"schema:{term.id}"}

            return json.dumps(sort_dict({"@context": json_context}), indent=2)

    def tree(self) -> str:
        context: Dict[str, Any] = {
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            # Legacy output: no trailing slash.
            "schema": str(SdoUri.for_layer()),
            "rdfs:subClassOf": {"@type": "@id"},
            "description": "rdfs:comment",
            "children": {"@reverse": "rdfs:subClassOf"},
        }
        data = self._tree_node(
            SDO.Thing, visitset=set(), term_dict={"@context": context}
        )
        return json.dumps(sort_dict(data), indent=3)

    def _tree_node(
        self,
        uri: URIRef,
        visitset: Set[URIRef],
        term_dict: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        vocab = self.vocab
        termdesc = vocab.term(uri)
        if termdesc is None:
            raise ValueError(f"No description for term {uri}")

        node: Dict[str, Any] = term_dict if term_dict is not None else {}
        rendered_comment = (
            localmarkdown.Markdown.parse(termdesc.comment).strip()
            if termdesc.comment
            else ""
        )
        node.update({
            "@type": "rdfs:Class",
            "@id": f"schema:{termdesc.id}",
            "name": termdesc.label or termdesc.id,
            "description": textutils.ShortenOnSentence(
                textutils.StripHtmlTags(rendered_comment)
            ),
        })

        supers = getattr(termdesc, "supers", [])
        if supers:
            sups = [f"schema:{SdoUri(sup).term_name()}" for sup in supers]
            node["rdfs:subClassOf"] = sups[0] if len(sups) == 1 else sups

        layer = vocab.layer(uri)
        if layer == "pending":
            node["pending"] = True
        if layer == "attic":
            node["attic"] = True

        if uri not in visitset:
            visitset.add(uri)
            sub_uris = vocab.subs.get(uri, ())
            if sub_uris:
                node["children"] = [
                    self._tree_node(sub, visitset)
                    for sub in sub_uris
                    if vocab.term(sub) is not None
                ]
        return node
