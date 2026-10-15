#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
from pathlib import Path
import tempfile
import unittest

import rdflib
from schemaorg.layout import Domain, InputLayout, OutputLayout, Releases, Scope
from schemaorg.model import SDO, VocabularyLoader
from schemaorg.renderers import (
    Artifact,
    CountsRenderer,
    CsvRenderer,
    RdfRenderer,
    ShapesRenderer,
    protocol_swap,
    uriwrap,
    write_artifact,
)
from schemaorg.version import Version, VersionItem
import scripts.buildfiles as buildfiles
import util.textutils as textutils

FIXTURE_TTL = """
@prefix : <https://schema.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
:Thing a rdfs:Class ; rdfs:label "Thing" ; rdfs:comment "Generic item." .
:Person a rdfs:Class ; rdfs:label "Person" ; rdfs:subClassOf :Thing ;
    rdfs:comment "A person, a kind of [[Thing]]." ;
    owl:equivalentClass <http://xmlns.com/foaf/0.1/Person> .
:OldThing a rdfs:Class ; rdfs:label "OldThing" ; rdfs:subClassOf :Thing ;
    :isPartOf <https://attic.schema.org> .
:DataType a rdfs:Class ; rdfs:label "DataType" ; rdfs:subClassOf rdfs:Class .
:Text a :DataType, rdfs:Class ; rdfs:label "Text" .
:name a rdf:Property ; rdfs:label "name" ; :domainIncludes :Thing ; :rangeIncludes :Text .
"""


def _fixture_graph() -> rdflib.Graph:
    g = rdflib.Graph(bind_namespaces="none")
    g.parse(data=FIXTURE_TTL, format="turtle")
    return g


class TestPostProcess(unittest.TestCase):
    def testProtocolSwap(self):
        swap = protocol_swap()
        self.assertEqual(swap(""), "")
        self.assertEqual(
            swap("Defined in https://schema.org and https://bib.schema.org."),
            "Defined in http://schema.org and http://bib.schema.org.",
        )
        self.assertEqual(
            swap(
                "https://health-lifesci.schema.org https://schema.org/Thing "
                "https://devices.schema.org/x https://schema.organic.example/x"
            ),
            "http://health-lifesci.schema.org http://schema.org/Thing "
            "http://devices.schema.org/x https://schema.organic.example/x",
        )

    def testProtocolSwapPreservesWebsites(self):
        text = (
            "https://blog.schema.org/post https://dev.schema.org/ "
            "https://myblog.schema.org/y"
        )
        self.assertEqual(
            protocol_swap()(text),
            "https://blog.schema.org/post https://dev.schema.org/ "
            "http://myblog.schema.org/y",
        )

    def testWriteArtifactAppliesPostProcessorsInOrder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.txt"
            write_artifact(
                Artifact(
                    "x",
                    path,
                    lambda: "https://schema.org/Thing",
                    (protocol_swap(), str.upper),
                )
            )
            self.assertEqual(path.read_text(encoding="utf-8"), "HTTP://SCHEMA.ORG/THING")


class TestRenderers(unittest.TestCase):
    def setUp(self):
        self.graph = _fixture_graph()
        self.all_graph, self.current_graph = buildfiles.split_release_graphs(self.graph)
        self.vocab = VocabularyLoader(
            self.all_graph, version=VersionItem("30.1", "2026-09-16")
        ).load()

    def testArrayToStr(self):
        self.assertEqual(textutils.Array2String([]), "")
        self.assertEqual(textutils.Array2String(["one"]), "one")
        self.assertEqual(
            textutils.Array2String(["one", "two", "three"]), "one, two, three"
        )

    def testUriWrap(self):
        self.assertEqual(uriwrap("Credential"), "https://schema.org/Credential")
        self.assertEqual(
            uriwrap("https://example.com/Bogus"), "https://example.com/Bogus"
        )
        self.assertEqual(
            uriwrap(["Person", "Thing"]),
            "https://schema.org/Person, https://schema.org/Thing",
        )

    def testSplitReleaseGraphs(self):
        foaf_person = rdflib.URIRef("http://xmlns.com/foaf/0.1/Person")
        self.assertIn((foaf_person, rdflib.RDF.type, rdflib.RDFS.Class), self.all_graph)
        self.assertNotIn((rdflib.RDFS.Class, rdflib.RDF.type, rdflib.RDFS.Class), self.all_graph)
        self.assertIn((SDO.OldThing, rdflib.RDFS.label, rdflib.Literal("OldThing")), self.all_graph)
        self.assertNotIn((SDO.OldThing, None, None), self.current_graph)

    def testShapesRendererUsesHttpGraph(self):
        renderer = ShapesRenderer(self.all_graph)
        http = renderer.http_graph
        self.assertIn(
            (rdflib.URIRef("http://schema.org/Person"), rdflib.RDFS.subClassOf, rdflib.URIRef("http://schema.org/Thing")),
            http,
        )
        self.assertNotIn((SDO.Person, None, None), http)
        self.assertIn("ValidSchemaPerson", renderer.shex())

    def testRdfRendererRequiresDatasetUriForNquads(self):
        renderer = RdfRenderer(self.all_graph)
        with self.assertRaises(ValueError):
            renderer.render("nquads")
        nq = renderer.render("nquads", dataset_uri=SDO["30.1"])
        self.assertIn("<https://schema.org/30.1> .", nq)
        self.assertEqual(nq, "".join(sorted(nq.splitlines(keepends=True))))
        self.assertIs(renderer.canonical, renderer.canonical)

    def testCsvRendererFiltersRetired(self):
        renderer = CsvRenderer(self.vocab)
        all_rows = renderer.types(include_retired=True)
        current_rows = renderer.types(include_retired=False)
        retired_row = '"https://schema.org/OldThing","OldThing"'
        self.assertIn(retired_row, all_rows)
        self.assertNotIn(retired_row, current_rows)
        self.assertIn("https://attic.schema.org", all_rows)

        props = renderer.properties(include_retired=True)
        self.assertEqual(props.count("\n"), 2)
        self.assertIn('"https://schema.org/name","name"', props)

    def testCsvRendererWikilinksAreSiteRelative(self):
        rows = CsvRenderer(self.vocab).types(include_retired=True)
        self.assertIn('<a class=""localLink"" href=""/Thing"">Thing</a>', rows)
        absolute = CsvRenderer(self.vocab, wikilink_prefix="https://schema.org/")
        self.assertIn(
            'href=""https://schema.org/Thing""', absolute.types(include_retired=True)
        )

    def testCountsRenderer(self):
        renderer = CountsRenderer(self.vocab, VersionItem("30.1", "2026-09-16"))
        self.assertEqual(renderer.counts["Property"], 1)
        self.assertEqual(renderer.counts["schemaorgversion"], "30.1")
        self.assertIn(renderer.json(), renderer.jsonp())


class TestPlan(unittest.TestCase):
    def testExportScopedAndUnscopedPlanCompleteSet(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions_path = Path(tmp) / "versions.json"
            versions_path.write_text(
                json.dumps({"schemaversion": "30.1", "releaseLog": {"30.1": "2026-09-16"}}),
                encoding="utf-8",
            )
            version = Version(versions_path)
            current_version = version.current()
            output_layout = OutputLayout(Path(tmp) / "out")
            releases = Releases(output_layout, version)
            all_graph, current_graph = buildfiles.split_release_graphs(_fixture_graph())
            vocab = VocabularyLoader(all_graph, version=current_version).load()

            all_scoped = buildfiles.export_scoped(
                Scope.ALL, all_graph, vocab, current_version, releases
            )
            current_scoped = buildfiles.export_scoped(
                Scope.CURRENT, current_graph, vocab, current_version, releases
            )
            unscoped = buildfiles.export_unscoped(
                all_graph, vocab, current_version, releases, output_layout, ()
            )
            self.assertEqual(len(all_scoped), 14)
            self.assertEqual(len(current_scoped), 14)
            self.assertEqual(len(unscoped), 15)

            artifacts = [*all_scoped, *current_scoped, *unscoped]
            paths = [a.path for a in artifacts]
            self.assertEqual(len(paths), len(set(paths)), "duplicate artifact paths")
            self.assertEqual(len(artifacts), 43)
            http = [a for a in artifacts if a.path.name.endswith(("-http.nt", "-http-types.csv"))]
            self.assertEqual(len(http), 4)
            self.assertTrue(all(a.post for a in http))

    def testExportFilesWithLayouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            in_dir = root / "in"
            out_dir = root / "out"
            (in_dir / "data").mkdir(parents=True)
            (in_dir / "versions.json").write_text(
                json.dumps({
                    "schemaversion": "30.1",
                    "releaseLog": {"30.1": "2026-09-16"},
                }),
                encoding="utf-8",
            )
            (in_dir / "data" / "schema.ttl").write_text(FIXTURE_TTL, encoding="utf-8")
            input_layout = InputLayout(in_dir)
            output_layout = OutputLayout(out_dir)

            buildfiles.export_files(input_layout=input_layout, output_layout=output_layout)

            for name in ("jsoncounts.json", "jsonpcounts.js", "sitemap.xml", "tree.jsonld", "schemaorg.owl", "jsonldcontext.jsonld"):
                self.assertTrue(output_layout.file(Domain.DOCS, name).is_file(), name)

            releases = Releases(output_layout, Version(in_dir / "versions.json"))
            self.assertTrue(releases.file(filename="httpequivs.ttl").is_file())
            for name in (
                "schemaorg-all-https-types.csv",
                "schemaorg-all-http-types.csv",
                "schemaorg-current-https-properties.csv",
                "schemaorg-current-http-properties.csv",
                "schemaorg-shapes.shexj",
                "schemaorg-shapes.shacl",
                "schemaorg-subclasses.shacl",
            ):
                self.assertTrue(releases.file(filename=name).is_file(), name)

            https_nt = releases.file(filename="schemaorg-all-https.nt").read_text(encoding="utf-8")
            http_nt = releases.file(filename="schemaorg-all-http.nt").read_text(encoding="utf-8")
            self.assertIn("<https://schema.org/Person>", https_nt)
            self.assertNotIn("https://schema.org", http_nt)
            self.assertEqual(protocol_swap()(https_nt), http_nt)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()
