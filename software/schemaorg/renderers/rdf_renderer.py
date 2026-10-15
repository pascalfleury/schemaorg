#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""RDF graph renderer (turtle, nt, nquads, rdf/xml, json-ld)."""

import functools
import json
import logging
from typing import Any, Optional, Tuple, Union

import rdflib
from rdflib.compare import to_canonical_graph
from util.sort_dict import sort_dict, sort_xml

log: logging.Logger = logging.getLogger(__name__)

RDF_FORMATS: Tuple[str, ...] = ("json-ld", "nquads", "nt", "rdf", "turtle")


def _type_sort_key(trip: Tuple[Any, Any, Any]) -> Tuple[int, str, str]:
    s, p, o = trip
    if p == rdflib.RDF.type:
        if o == rdflib.RDFS.Class:
            return (0, str(s), str(o))
        return (1, str(s), str(o))
    return (2, str(s), str(p))


class RdfRenderer:
    """Deterministic serializations of one graph; canonicalizes it once for all formats."""

    def __init__(self, graph: rdflib.Graph) -> None:
        self.graph = graph

    @functools.cached_property
    def canonical(self) -> rdflib.Graph:
        g_can: rdflib.Graph = to_canonical_graph(self.graph)
        g_can.namespace_manager = self.graph.namespace_manager
        return g_can

    @functools.cached_property
    def _type_sorted(self) -> rdflib.Graph:
        # rdf/xml lists class declarations first, then other typings, then the rest.
        g_out = rdflib.Graph()
        g_out.namespace_manager = self.graph.namespace_manager
        for t in sorted(self.canonical, key=_type_sort_key):
            g_out.add(t)
        return g_out

    @functools.cache
    def render(
        self,
        output_format: str,
        dataset_uri: Optional[rdflib.URIRef] = None,
    ) -> str:
        """Serializes the graph; nquads wraps it in a dataset named dataset_uri."""
        if output_format not in RDF_FORMATS:
            raise ValueError(f"Unknown RDF export format: {output_format}")

        source: Union[rdflib.Graph, rdflib.Dataset] = self.canonical
        if output_format == "rdf":
            source = self._type_sorted
        elif output_format == "nquads":
            if dataset_uri is None:
                raise ValueError("nquads export requires a dataset_uri")
            ds: rdflib.Dataset = rdflib.Dataset()
            qg: rdflib.Graph = ds.graph(dataset_uri)
            for trip in self.canonical:
                qg.add(trip)
            source = ds

        fmt: str = "pretty-xml" if output_format == "rdf" else output_format
        out: str = str(
            source.serialize(
                format=fmt, auto_compact=True, sort_keys=True, max_depth=1
            )
        )

        if output_format in ("nt", "nquads"):
            out = (
                "\n".join(
                    sorted(
                        line.rstrip()
                        for line in out.splitlines()
                        if line.strip()
                    )
                )
                + "\n"
            )
        elif output_format == "rdf":
            try:
                out = sort_xml(out)
            except Exception as e:
                log.warning(f"Failed to sort RDF XML: {e}")
        elif output_format == "json-ld":
            try:
                out = json.dumps(sort_dict(json.loads(out)), indent=2)
            except Exception as e:
                log.warning(f"Failed to sort JSON-LD: {e}")

        return out
