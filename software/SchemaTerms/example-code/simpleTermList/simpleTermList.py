#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

import rdflib

if os.getcwd() not in sys.path:
    sys.path.insert(1, os.getcwd())
import software

from SchemaTerms.localmarkdown import Markdown
from software.util.paths import DefaultInputLayout
from software.data_model.loader import GraphLoader
from software.data_model.registry import TermRegistry
from software.data_model.type_map import SdoTermType


Markdown.setWikilinkCssClass("localLink")
Markdown.setWikilinkPrePath("/")

layout = DefaultInputLayout()
loader = GraphLoader.from_layout(layout)
loader.load_all()
registry = TermRegistry.get_instance()
print("Types Count: %s" % len(registry.get_all_types()))
print("Properties Count: %s" % len(registry.get_all_properties()))


for termname in ["acceptedAnswer", "Book"]:
    term = registry.get_by_id(termname)
    if not term: continue

    print("")
    print("TYPE: %s" % term.termType)
    print("URI: %s" % term.uri)
    print("ID: %s" % term.id)
    print("LABEL: %s" % term.label)
    print("")
    print("superPaths: %s" % term.superPaths)
    print("comment: %s" % term.comment)
    print("equivalents: %s" % term.equivalents)
    print("examples: %s" % term.examples)
    print("pending: %s" % term.pending)
    print("retired: %s" % term.retired)
    print("sources: %s" % term.sources)
    print("acknowledgements:" % term.acknowledgements)
    print("subs: %s" % term.subs)
    print("supers: %s" % term.supers)
    print("supersededBy: %s" % term.supersededBy)
    print("supersedes: %s" % term.supersedes)
    print("termStack: %s" % term.termStack)

    for stackElement in term.termStack:
        print("Element: %s" % stackElement)

    if term.termType == SdoTermType.TYPE or term.termType == SdoTermType.ENUMERATION:
        print("Properties: %s" % term.properties)
        print("All Properties: %s" % term.allproperties)
        print("Expected Type for: %s" % term.expectedTypeFor)

    if term.termType == SdoTermType.PROPERTY:
        print("Domain includes: %s" % term.domainIncludes)
        print("Range includes: %s" % term.rangeIncludes)
    else:
        if term.termType == SdoTermType.ENUMERATION:
            print("Enumeration Members: %s" % term.enumerationMembers)


        if term.termType == SdoTermType.ENUMERATIONVALUE:
            print("Parent Enumeration: %s" % term.enumerationParent)

        for p in term.properties:
            prop = registry.get_by_id(p)
            if not prop: continue
            print("Prop: %s.  Pending: %s" % (prop.id, prop.pending))
            print("   Expected Types: %s" % prop.rangeIncludes)
            print("   Comment: %s" % prop.comment)
