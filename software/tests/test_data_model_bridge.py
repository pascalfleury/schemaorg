#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# Setup path
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
import software

from rdflib import Graph, RDF, RDFS, URIRef, Literal
from software.data_model.bridge import SdoTermSource
from software.data_model.models import SdoType
from software.util.schema import URI

def test_bridge():
    g = Graph()
    g.bind("schema", URI)
    
    # Setup some test data
    hotel = URI.Hotel
    g.add((hotel, RDF.type, RDFS.Class))
    g.add((hotel, RDFS.label, Literal("Hotel")))
    
    place = URI.Place
    g.add((place, RDF.type, RDFS.Class))
    g.add((place, RDFS.label, Literal("Place")))
    g.add((hotel, RDFS.subClassOf, place))
    
    # Initialize the bridge
    SdoTermSource.setSourceGraph(g)
    
    # Test the API
    term = SdoTermSource.getTerm("Hotel")
    print(f"Loaded term via bridge: {term.id}")
    assert term.id == "Hotel"
    
    # Test relations (simulating old world)
    # Since our bridge currently returns the raw model, 
    # and our models use @property for relations, 
    # term.supers should return a list of objects.
    print(f"Parents: {[p.id for p in term.supers]}")
    assert "Place" in [p.id for p in term.supers]
    
    # Test getAllTerms
    all_terms = SdoTermSource.getAllTerms()
    print(f"All terms: {all_terms}")
    assert "Hotel" in all_terms
    assert "Place" in all_terms

if __name__ == "__main__":
    test_bridge()
