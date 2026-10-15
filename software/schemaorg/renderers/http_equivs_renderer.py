#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""HTTP/HTTPS equivalence Turtle renderer."""

import rdflib
import rdflib.namespace
from schemaorg.model import SchemaProperty, Vocabulary
from schemaorg.sdo_uri import SCHEMA_URL, SDO

SDO_HTTP: rdflib.Namespace = rdflib.Namespace(SCHEMA_URL._replace(scheme="http").geturl())


class HttpEquivsRenderer:
    """Turtle declaring the http and https versions of every live term equivalent."""

    def __init__(self, vocab: Vocabulary) -> None:
        self.vocab = vocab

    def render(self) -> str:
        outGraph: rdflib.Graph = rdflib.Graph()
        outGraph.bind("schema_p", SDO_HTTP)
        outGraph.bind("schema_s", SDO)
        outGraph.bind("owl", rdflib.namespace.OWL)

        for uri, t in self.vocab.all_terms().items():
            if self.vocab.layer(uri) != "attic":
                eqiv: rdflib.URIRef = (
                    rdflib.namespace.OWL.equivalentProperty
                    if isinstance(t, SchemaProperty)
                    else rdflib.namespace.OWL.equivalentClass
                )
                p_uri: rdflib.URIRef = SDO_HTTP[t.id]
                s_uri: rdflib.URIRef = SDO[t.id]
                outGraph.add((p_uri, eqiv, s_uri))
                outGraph.add((s_uri, eqiv, p_uri))

        return str(
            outGraph.serialize(
                format="turtle", auto_compact=True, sort_keys=True
            )
        )
