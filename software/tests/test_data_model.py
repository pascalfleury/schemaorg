#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# Setup path
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
import software

from rdflib import Graph, RDF, RDFS, URIRef, Namespace, Literal
from software.data_model.models import SdoType, SdoProperty, SdoEnumeration
from software.util.schema import URI
from software.data_model.loader import GraphLoader
from software.data_model.registry import TermRegistry
from software.data_model.bridge import wrap_term
from software.data_model.compat import LegacySdoTermAdapter

def test_uri_centric_model():
    # Reset registry for fresh test
    TermRegistry.reset()
    registry = TermRegistry.get_instance()
    
    g = Graph()
    g.bind("schema", URI)
    
    # Define a hierarchy
    thing = URI.Thing
    g.add((thing, RDF.type, RDFS.Class))
    g.add((thing, RDFS.label, Literal("Thing")))
    
    place = URI.Place
    g.add((place, RDF.type, RDFS.Class))
    g.add((place, RDFS.label, Literal("Place")))
    g.add((place, RDFS.subClassOf, thing))
    
    hotel = URI.Hotel
    g.add((hotel, RDF.type, RDFS.Class))
    g.add((hotel, RDFS.label, Literal("Hotel")))
    g.add((hotel, RDFS.subClassOf, place))
    
    # Define an enumeration
    status = URI.Status
    g.add((status, RDF.type, RDFS.Class))
    g.add((status, RDFS.subClassOf, URI.Enumeration))
    g.add((status, RDFS.label, Literal("Status")))
    
    active = URI.Active
    g.add((active, RDF.type, status))
    g.add((active, RDFS.label, Literal("Active")))
    
    # Define a property
    checkin = URI.checkinTime
    g.add((checkin, RDF.type, RDF.Property))
    g.add((checkin, RDFS.label, Literal("checkinTime")))
    g.add((checkin, URI.domainIncludes, hotel))
    g.add((checkin, URI.rangeIncludes, URI.DateTime))
    
    loader = GraphLoader(g)
    loader.load_all()
    
    print(f"Registry size: {len(registry)}")
    
    # Test lookup and lazy loading
    hotel_obj = wrap_term(registry.get(hotel))
    assert hotel_obj is not None
    print(f"Term: {hotel_obj.id} ({hotel_obj.uri})")
    
    # Lazy load parents
    parents = hotel_obj.supers
    print(f"  Parents: {[p.id for p in parents]}")
    assert "Place" in [p.id for p in parents]
    
    # Deep lazy load
    place_obj = parents[0]
    grandparents = place_obj.supers
    print(f"  Grandparents: {[p.id for p in grandparents]}")
    assert "Thing" in [p.id for p in grandparents]
    
    # Test Enumeration
    status_obj = wrap_term(registry.get(status))
    assert isinstance(status_obj, LegacySdoTermAdapter)
    members = status_obj.enumerationMembers
    print(f"  Enum Members: {[m.id for m in members]}")
    assert "Active" in [m.id for m in members]
    
    # Test Property
    prop_obj = wrap_term(registry.get(checkin))
    assert isinstance(prop_obj, LegacySdoTermAdapter)
    print(f"  Property: {prop_obj.id}")
    print(f"  Domains: {[d.id for d in prop_obj.domains]}")
    assert "Hotel" in [d.id for d in prop_obj.domains]

if __name__ == "__main__":
    test_uri_centric_model()
