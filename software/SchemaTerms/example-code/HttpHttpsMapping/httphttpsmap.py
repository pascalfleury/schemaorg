#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import glob
import os
import sys

import rdflib
from rdflib.namespace import OWL

if os.getcwd() not in sys.path:
    sys.path.insert(1, os.getcwd())
import software

from software.util.paths import DefaultInputLayout
from software.data_model.loader import GraphLoader
from software.data_model.registry import TermRegistry
from software.data_model.type_map import SdoTermType
from rdflib import URIRef
import util.schema as schema


parser = argparse.ArgumentParser()
parser.add_argument("-o", "--output", required=True, help="output file")
args = parser.parse_args()

exts = {"rdf": ".rdf", "nt": ".nt", "json-ld": ".jsonld", "turtle": ".ttl"}

layout = DefaultInputLayout()
loader = GraphLoader.from_layout(layout)
loader.load_all()
registry = TermRegistry.get_instance()

s_p = "http://schema.org/"
s_s = "https://schema.org/"
outGraph = rdflib.Graph()
outGraph.bind("schema_p", s_p)
outGraph.bind("schema_s", s_s)
outGraph.bind("owl", OWL)

VOCABURI = schema.VOCABURI
terms = [t.id for t in registry.all_terms().values() if t.id]
print("Loaded %d terms" % len(terms))

for term in terms:
    t = registry.get_by_id(term)
    if not t: continue

    if t.uri.startswith(VOCABURI):  # Filter out non Schema terms
        eqiv = OWL.equivalentClass
        if t.termType == SdoTermType.PROPERTY:
            eqiv = OWL.equivalentProperty

        p = URIRef(s_p + t.id)
        s = URIRef(s_s + t.id)
        outGraph.add((p, eqiv, s))
        outGraph.add((s, eqiv, p))
        print(t.id)

for ftype in exts:
    ext = exts[ftype]
    fname = "%s%s" % (args.output, ext)
    print("%s: Writing to: %s" % (sys.argv[0], fname))
    kwargs = {'sort_keys': True}
    f = open(fname, "w")
    format = ftype
    if format == "rdf":
        format = "pretty-xml"
    output = outGraph.serialize(format=format, auto_compact=True, **kwargs).decode()
    f.write(output)
