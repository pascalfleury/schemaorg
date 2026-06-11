#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import sys
if os.getcwd() not in sys.path:
    sys.path.insert(1, os.getcwd())
import software

from software.util.paths import DefaultInputLayout
from software.data_model.loader import GraphLoader
from software.data_model.registry import TermRegistry
from SchemaTerms.localmarkdown import Markdown

Markdown.setWikilinkCssClass("localLink")
Markdown.setWikilinkPrePath("/")


layout = DefaultInputLayout()
loader = GraphLoader.from_layout(layout)
loader.load_all()
registry = TermRegistry.get_instance()
terms = [t.id for t in registry.all_terms().values() if t.id]
print("Terms Count: %s" % len(terms))

from schematermsprotobuf import sdotermToProtobuf, sdotermToProtobufMsg, sdotermToProtobufText, protobufToMsg, protobufToText

import time,datetime

start = datetime.datetime.now() #debug
for t in terms:
    tic = datetime.datetime.now() #debug

    term = registry.get_by_id(t)
    if not term: continue
    buf = sdotermToProtobuf(term)
    msg = protobufToMsg(buf)
    txt = protobufToText(buf)
    mfilename = os.path.join(os.path.dirname(__file__), "out-protomsgs", t + ".msg")
    tfilename = os.path.join(os.path.dirname(__file__), "out-protomsgs", t + ".txt")
    f = open(mfilename,"wb")
    f.write(msg)
    f.close()
    f = open(tfilename,"w")
    f.write(txt)
    f.close()

    print("Term: %s - %s" % (t, str(datetime.datetime.now()-tic))) #debug
print ("All terms took %s seconds" % str(datetime.datetime.now()-start)) #debug
