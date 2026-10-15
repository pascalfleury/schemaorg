#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""OWL/XML ontology renderer."""

import functools
from typing import Dict, FrozenSet, List, Optional, Set
from xml.dom import minidom
from xml.etree import ElementTree

import rdflib
from rdflib.namespace import RDF, RDFS
from rdflib.term import URIRef
from schemaorg import constants
from schemaorg.sdo_uri import SDO, SdoUri
from schemaorg.version import VersionItem
from SchemaTerms.localmarkdown import Markdown, MarkdownTool

NAMESPACES: Dict[str, str] = {
    "xml:base": constants.SCHEMA_URI,
    "xmlns": constants.SCHEMA_URI,
    "xmlns:schema": constants.SCHEMA_URI,
    "xmlns:rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmlns:rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xmlns:owl": "http://www.w3.org/2002/07/owl#",
    "xmlns:dcterms": "http://purl.org/dc/terms/",
    "xmlns:xsd": "http://www.w3.org/2001/XMLSchema#",
}

DEFAULTRANGES: FrozenSet[str] = frozenset(
    str(t) for t in (SDO.Text, SDO.URL, SDO.Role)
)
DATATYPES: FrozenSet[str] = frozenset(
    str(t)
    for t in (
        SDO.Boolean,
        SDO.Date,
        SDO.DateTime,
        SDO.Number,
        SDO.Float,
        SDO.Integer,
        SDO.Time,
    )
)


def _pretty_comment(text: str) -> ElementTree.Comment:
    """XML comment framed with slash banners."""
    inner_text = f"/ {text}"
    bar = "/" * len(inner_text)
    return ElementTree.Comment(f"\n\t{bar}\n\t{inner_text}\n\t{bar}\n\n\t")


def _defined_by(uri: str, ext: Optional[str] = None) -> ElementTree.Element:
    root = SdoUri.for_layer(SdoUri(ext).layer() if ext else None)
    defn = ElementTree.Element("rdfs:isDefinedBy")
    defn.set("rdf:resource", f"{root}/{SdoUri(uri).term_name()}")
    return defn


class OwlRenderer:
    """OWL/XML ontology of the graph."""

    def __init__(self, graph: rdflib.Graph, version: VersionItem) -> None:
        self.graph = graph
        self.version = version

    @functools.cache
    def render(self) -> str:
        old_pre = MarkdownTool.WPRE
        MarkdownTool.setWikilinkPrePath("/")
        try:
            dom = self._create_dom()
            self._populate(dom)
        finally:
            MarkdownTool.setWikilinkPrePath(old_pre)
        doc = minidom.parseString(ElementTree.tostring(dom))
        return doc.toprettyxml(encoding="UTF-8").decode("utf-8")

    def _create_dom(self) -> ElementTree.Element:
        dom = ElementTree.Element("rdf:RDF")
        for k, v in sorted(NAMESPACES.items()):
            dom.set(k, v)

        version = self.version.number()
        version_date = self.version.date()
        dom.append(
            _pretty_comment(
                f"Generated from Schema.org version: {version} released: {version_date}"
            )
        )
        ont = ElementTree.SubElement(dom, "owl:Ontology")
        ont.set("rdf:about", constants.SCHEMA_URI)
        info = ElementTree.SubElement(ont, "owl:versionInfo")
        info.set("rdf:datatype", "http://www.w3.org/2001/XMLSchema#string")
        info.text = version
        label = ElementTree.SubElement(ont, "rdfs:label")
        label.text = "Schema.org Vocabulary"
        modified = ElementTree.SubElement(ont, "dcterms:modified")
        modified.set("rdf:datatype", "http://www.w3.org/2001/XMLSchema#date")
        modified.text = version_date
        dom.append(_pretty_comment("Definitions"))
        return dom

    def _populate(self, dom: ElementTree.Element) -> None:
        graph = self.graph

        dom.append(_pretty_comment("Class Definitions"))
        types: Set[rdflib.term.Node] = {
            s
            for s, _, _ in graph.triples((None, RDF.type, RDFS.Class))
            if SdoUri(s).is_sdo()
        }
        for t in sorted(types, key=str):
            self._add_type(dom, str(t))

        dom.append(_pretty_comment("Property Definitions"))
        props: Set[rdflib.term.Node] = {
            s
            for s, _, _ in graph.triples((None, RDF.type, RDF.Property))
            if SdoUri(s).is_sdo()
        }
        for p in sorted(props, key=str):
            self._add_prop(dom, str(p))

        dom.append(_pretty_comment("Named Individuals Definitions"))
        self._add_enums(dom)
        self._add_named_individual(dom, str(SDO["True"]))
        self._add_named_individual(dom, str(SDO["False"]))

    def _add_type(self, dom: ElementTree.Element, uri: str) -> None:
        typ = ElementTree.SubElement(dom, "owl:Class")
        typ.set("rdf:about", uri)
        ext: Optional[str] = None
        for p, o in sorted(
            self.graph.predicate_objects(URIRef(uri)),
            key=lambda x: (str(x[0]), str(x[1])),
        ):
            if p == RDFS.label:
                elem = ElementTree.SubElement(typ, "rdfs:label")
                elem.set("xml:lang", "en")
                elem.text = str(o)
            elif p == RDFS.comment:
                elem = ElementTree.SubElement(typ, "rdfs:comment")
                elem.set("xml:lang", "en")
                elem.text = Markdown.parse(str(o))
            elif p == RDFS.subClassOf:
                elem = ElementTree.SubElement(typ, "rdfs:subClassOf")
                elem.set("rdf:resource", str(o))
            elif p == SDO.isPartOf:
                ext = str(o)
            elif p == RDF.type and o == SDO.DataType:
                elem = ElementTree.SubElement(typ, "rdfs:subClassOf")
                elem.set("rdf:resource", str(SDO.DataType))

        typ.append(_defined_by(uri, ext))

    def _add_prop(self, dom: ElementTree.Element, uri: str) -> None:
        children: List[ElementTree.Element] = []
        domains: Set[rdflib.term.Node] = set()
        ranges: List[str] = []
        datatypeonly = True
        ext: Optional[str] = None
        for p, o in sorted(
            self.graph.predicate_objects(URIRef(uri)),
            key=lambda x: (str(x[0]), str(x[1])),
        ):
            if p == RDFS.label:
                elem = ElementTree.Element("rdfs:label")
                elem.set("xml:lang", "en")
                elem.text = str(o)
                children.append(elem)
            elif p == RDFS.comment:
                elem = ElementTree.Element("rdfs:comment")
                elem.set("xml:lang", "en")
                elem.text = Markdown.parse(str(o))
                children.append(elem)
            elif p == RDFS.subPropertyOf:
                sub = ElementTree.Element("rdfs:subPropertyOf")
                subval = str(o)
                # Fixes a special case with schema:additionalType.
                if subval == "rdf:type":
                    subval = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
                sub.set("rdf:resource", subval)
                children.append(sub)
            elif p == SDO.inverseOf:
                sub = ElementTree.Element("owl:inverseOf")
                sub.set("rdf:resource", str(o))
                children.append(sub)
            elif p == SDO.supersededBy:
                sub = ElementTree.Element("schema:supersededBy")
                sub.set("rdf:resource", str(o))
                children.append(sub)
            elif p == SDO.domainIncludes:
                domains.add(o)
            elif p == SDO.rangeIncludes:
                ranges.append(str(o))
                if str(o) not in DATATYPES:
                    datatypeonly = False
            elif p == SDO.isPartOf:
                ext = str(o)

        children.append(_defined_by(uri, ext))

        if not datatypeonly:
            ranges.extend(r for r in sorted(DEFAULTRANGES) if r not in ranges)

        if domains:
            d = ElementTree.Element("rdfs:domain")
            children.append(d)
            cl = ElementTree.SubElement(d, "owl:Class")
            u = ElementTree.SubElement(cl, "owl:unionOf")
            u.set("rdf:parseType", "Collection")
            for target in sorted(domains, key=str):
                targ = ElementTree.SubElement(u, "owl:Class")
                targ.set("rdf:about", str(target))

        if ranges:
            r_elem = ElementTree.Element("rdfs:range")
            children.append(r_elem)
            cl_elem = ElementTree.SubElement(r_elem, "owl:Class")
            u_elem = ElementTree.SubElement(cl_elem, "owl:unionOf")
            u_elem.set("rdf:parseType", "Collection")
            for target_range in sorted(ranges):
                targ_elem = ElementTree.SubElement(u_elem, "owl:Class")
                targ_elem.set("rdf:about", target_range)

        tag = "owl:DatatypeProperty" if datatypeonly else "owl:ObjectProperty"
        prop = ElementTree.SubElement(dom, tag)
        prop.set("rdf:about", uri)
        prop.extend(children)

    def _add_enums(self, dom: ElementTree.Element) -> None:
        query = f""" prefix schema: <{constants.SCHEMA_URI}>
        select Distinct ?enum ?parent where{{
        ?parent rdfs:subClassOf schema:Enumeration.
            ?enum rdfs:subClassOf ?parent.
        }}
        """
        enums = list(self.graph.query(query))
        for row in sorted(enums, key=lambda r: (str(r.enum), str(r.parent))):
            self._add_named_individual(
                dom, str(row.enum), parent=str(row.parent)
            )

    def _add_named_individual(
        self,
        dom: ElementTree.Element,
        individual: str,
        parent: Optional[str] = None,
    ) -> None:
        typ = ElementTree.SubElement(dom, "owl:NamedIndividual")
        typ.set("rdf:about", individual)
        ext: Optional[str] = None
        for p, o in sorted(
            self.graph.predicate_objects(URIRef(individual)),
            key=lambda x: (str(x[0]), str(x[1])),
        ):
            if p == RDFS.label:
                elem = ElementTree.SubElement(typ, "rdfs:label")
                elem.set("xml:lang", "en")
                elem.text = str(o)
            elif p == RDFS.comment:
                elem = ElementTree.SubElement(typ, "rdfs:comment")
                elem.set("xml:lang", "en")
                elem.text = Markdown.parse(str(o))
            elif p == SDO.isPartOf:
                ext = str(o)

        typ.append(_defined_by(individual, ext))

        if parent:
            sub = ElementTree.SubElement(typ, "rdfs:subClassOf")
            sub.set("rdf:resource", parent)
