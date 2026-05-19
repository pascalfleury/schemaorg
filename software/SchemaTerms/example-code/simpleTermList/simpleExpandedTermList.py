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



def showTerm(term, ind=""):
    print("")
    print("%sID: %s" % (ind, term.id))
    print("%sExpanded %s" % (ind, term.expanded))
    print("%sTYPE: %s" % (ind, term.termType))
    print("%sURI: %s" % (ind, term.uri))
    print("%sLABEL: %s" % (ind, term.label))
    print("")
    print("%ssuperPaths: %s" % (ind, term.superPaths))
    print("%scomment: %s" % (ind, term.comment))
    print("%sequivalents: %s" % (ind, term.equivalents))
    print("%sexamples: %s" % (ind, term.examples))
    print("%spending: %s" % (ind, term.pending))
    print("%sretired: %s" % (ind, term.retired))
    print("%ssources: %s" % (ind, term.sources))
    print("%sacknowledgements: %s" % (ind, term.acknowledgements))
    print("%ssubs: %s" % (ind, term.subs))
    print("%ssupers: %s" % (ind, term.supers))
    print("%ssupersededBy: %s" % (ind, term.supersededBy))
    print("%ssupersedes: %s" % (ind, term.supersedes))

    if term.termType == SdoTermType.TYPE or term.termType == SdoTermType.ENUMERATION or term.termType == SdoTermType.DATATYPE:
        if term.expanded():
            print("%sProperties count %s" % (ind, len(term.properties)))
            for p in term.properties.terms:
                showTerm(p, ind=ind + "   ")
            print("%sExpected Type for count %s" % (ind, len(term.expectedTypeFor)))
            for t in term.expectedTypeFor.terms:
                showTerm(t, ind=ind + "   ")
        else:
            print("%sProperties: %s" % (ind, term.properties))
            print("%sExpected Type for: %s" % (ind, term.expectedTypeFor))

    if term.termType == SdoTermType.PROPERTY:
        print("%sDomain includes: %s" % (ind, term.domainIncludes))
        print("%sRange includes: %s" % (ind, term.rangeIncludes))

    if term.termType == SdoTermType.ENUMERATION:
        print("%sEnumeration Members: %s" % (ind, term.enumerationMembers))


    if term.termType == SdoTermType.ENUMERATIONVALUE:
        print("%sParent Enumeration: %s" % (ind, term.enumerationParent))

    if term.expanded():
        print("%stermStack count: %s " % (ind, len(term.termStack)))
        for t in term.termStack.terms:
            showTerm(t, ind=ind + "...")
    else:
        print("%stermStack: %s " % (ind, term.termStack))

for termname in ["acceptedAnswer", "Book"]:
    term = registry.get_by_id(termname)
    if not term: continue
    showTerm(term)
