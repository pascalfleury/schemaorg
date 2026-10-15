#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""ShEx and SHACL shape renderer."""

import functools

import rdflib
from schemaorg import constants
from schemaorg.renderers.postprocess import protocol_swap
from scripts.shex_shacl_shapes_exporter import ShaclParser, ShExJParser


class ShapesRenderer:
    """ShEx and SHACL shapes of one graph.

    The shape parsers key on the ``http://schema.org/`` namespace, so the
    graph is rewritten to that scheme before use.
    """

    def __init__(self, graph: rdflib.Graph) -> None:
        self.graph = graph

    @functools.cached_property
    def http_graph(self) -> rdflib.Graph:
        swap = protocol_swap()

        def http(node: rdflib.term.Node) -> rdflib.term.Node:
            if isinstance(node, rdflib.URIRef):
                return rdflib.URIRef(swap(str(node)))
            return node

        out = rdflib.Graph(bind_namespaces="none")
        out.bind("schema", swap(constants.SCHEMA_URI))
        for s, p, o in self.graph:
            out.add((http(s), http(p), http(o)))
        return out

    def shex(self) -> str:
        return ShExJParser.to_shex(self.http_graph)

    def shacl(self) -> str:
        return ShaclParser.to_shacl(self.http_graph)

    def subclasses(self) -> str:
        return ShaclParser.get_subclasses(self.http_graph)
