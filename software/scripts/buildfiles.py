#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""CLI and orchestrator for generating schema.org release files.

Owns everything that is not rendering: command line, layouts, version, the
ALL/CURRENT graphs, the vocabulary, and the list of files to produce. A build
always produces the complete set. Renderers in ``schemaorg.renderers`` only
ever see a graph or a vocabulary.
"""

import argparse
from functools import partial
import logging
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Set, Tuple

import rdflib
from schemaorg import constants
from schemaorg.graph_loader import GraphLoader
from schemaorg.layout import (
    Domain,
    InputLayout,
    Issues,
    OutputLayout,
    Protocol,
    Releases,
    Scope,
)
from schemaorg.model import Vocabulary, VocabularyLoader
from schemaorg.renderers import (
    Artifact,
    CountsRenderer,
    CsvRenderer,
    ExamplesRenderer,
    HttpEquivsRenderer,
    JsonLdRenderer,
    OwlRenderer,
    RdfRenderer,
    ShapesRenderer,
    SitemapRenderer,
    protocol_swap,
    write_artifact,
)
from schemaorg.sdo_uri import SDO, SdoUri
from schemaorg.version import Version, VersionItem
import SchemaTerms.sdotermsource as sdotermsource
import util.pretty_logger as pretty_logger
import util.schema as schema

log: logging.Logger = logging.getLogger(__name__)


# -- graphs ----------------------------------------------------------------


def _bind_namespaces(graph: rdflib.Graph) -> None:
    graph.bind("schema", constants.SCHEMA_URI)
    sdotermsource.bindNameSpaces(graph)


def split_release_graphs(source_graph: rdflib.Graph) -> Tuple[rdflib.Graph, rdflib.Graph]:
    """ALL graph (schema.org subjects plus foreign type stubs) and CURRENT graph (no attic)."""
    all_graph = rdflib.Graph()
    _bind_namespaces(all_graph)
    current_graph = rdflib.Graph()
    _bind_namespaces(current_graph)

    # Keep all SDO statements
    for s, p, o in source_graph:
        if isinstance(s, rdflib.URIRef) and SdoUri(s).is_sdo():
            all_graph.add((s, p, o))

    # Foreign classes and properties referenced by schema.org terms get a bare
    # type declaration so consumers can resolve them (skipping W3C meta-terms).
    meta_classes = {rdflib.RDFS.Class, rdflib.OWL.Class, rdflib.RDF.Property}
    meta_props = {rdflib.RDF.Property, rdflib.OWL.ObjectProperty, rdflib.OWL.DatatypeProperty}

    def is_foreign(o: rdflib.term.Node) -> bool:
        return isinstance(o, rdflib.URIRef) and not SdoUri(o).is_sdo()

    for pred in (rdflib.RDFS.subClassOf, rdflib.OWL.equivalentClass):
        for _, o in list(all_graph.subject_objects(pred)):
            if is_foreign(o) and o not in meta_classes:
                all_graph.add((o, rdflib.RDF.type, rdflib.RDFS.Class))
    for pred in (rdflib.RDFS.subPropertyOf, rdflib.OWL.equivalentProperty):
        for _, o in list(all_graph.subject_objects(pred)):
            if is_foreign(o) and o not in meta_props:
                all_graph.add((o, rdflib.RDF.type, rdflib.RDF.Property))

    retired: Set[rdflib.term.Node] = {
        s for s, o in all_graph.subject_objects(SDO.isPartOf) if SdoUri(o).is_retired()
    }
    for s, p, o in all_graph:
        if s not in retired:
            current_graph.add((s, p, o))

    return all_graph, current_graph


# -- plan ------------------------------------------------------------------


# Each (https, http) file pair shares one render; only post-processing differs.
PROTOCOL_VARIANTS: Tuple[Tuple[Protocol, Tuple[Callable[[str], str], ...]], ...] = (
    (Protocol.HTTPS, ()),
    (Protocol.HTTP, (protocol_swap(),)),
)


def export_scoped(
    scope: Scope,
    graph: rdflib.Graph,
    vocab: Vocabulary,
    version: VersionItem,
    releases: Releases,
) -> List[Artifact]:
    """RDF and CSV release artifacts for one scope (no file I/O)."""
    rdf = RdfRenderer(graph)
    csv = CsvRenderer(vocab)
    include_retired = scope == Scope.ALL
    artifacts: List[Artifact] = []
    for protocol, finisher in PROTOCOL_VARIANTS:
        def release_file(extension: str) -> Path:
            return releases.file(protocol=protocol, scope=scope, extension=extension)

        artifacts.extend([
            Artifact("RDFExport.json-ld", release_file(".jsonld"), partial(rdf.render, "json-ld"), finisher),
            Artifact("RDFExport.nquads", release_file(".nq"), partial(rdf.render, "nquads", SDO[version.number()]), finisher),
            Artifact("RDFExport.nt", release_file(".nt"), partial(rdf.render, "nt"), finisher),
            Artifact("RDFExport.rdf", release_file(".rdf"), partial(rdf.render, "rdf"), finisher),
            Artifact("RDFExport.turtle", release_file(".ttl"), partial(rdf.render, "turtle"), finisher),
            Artifact("CSVExports", release_file("-types.csv"), partial(csv.types, include_retired), finisher),
            Artifact("CSVExports", release_file("-properties.csv"), partial(csv.properties, include_retired), finisher),
        ])
    return artifacts


def export_unscoped(
    graph: rdflib.Graph,
    vocab: Vocabulary,
    version: VersionItem,
    releases: Releases,
    output_layout: OutputLayout,
    example_files: Sequence[Path],
) -> List[Artifact]:
    """Vocabulary-wide docs and release artifacts (no file I/O)."""
    def docs_file(filename: str) -> Path:
        return output_layout.file(Domain.DOCS, filename)

    jsonld = JsonLdRenderer(graph, vocab)
    counts = CountsRenderer(vocab, version)
    owl = OwlRenderer(graph, version)
    shapes = ShapesRenderer(graph)
    return [
        Artifact("Context", docs_file("jsonldcontext.jsonld"), jsonld.context),
        Artifact("Context", docs_file("jsonldcontext.json"), jsonld.context),
        Artifact("Context", docs_file("jsonldcontext.json.txt"), jsonld.context),
        Artifact("Context", releases.file(filename="schemaorgcontext.jsonld"), jsonld.context),
        Artifact("Tree", docs_file("tree.jsonld"), jsonld.tree),
        Artifact("jsoncounts", docs_file("jsoncounts.json"), counts.json),
        Artifact("jsonpcounts", docs_file("jsonpcounts.js"), counts.jsonp),
        Artifact("Owl", docs_file("schemaorg.owl"), owl.render),
        Artifact("Owl", releases.file(filename="schemaorg.owl"), owl.render),
        Artifact("Httpequivs", releases.file(filename="httpequivs.ttl"), HttpEquivsRenderer(vocab).render),
        Artifact("Sitemap", docs_file("sitemap.xml"), SitemapRenderer(vocab, version).render),
        Artifact("Shex_Shacl", releases.file(protocol="", scope="shapes", extension=".shexj"), shapes.shex),
        Artifact("Shex_Shacl", releases.file(protocol="", scope="shapes", extension=".shacl"), shapes.shacl),
        Artifact("Shex_Shacl", releases.file(protocol="", scope="subclasses", extension=".shacl"), shapes.subclasses),
        Artifact("Examples", releases.file(filename="schemaorg-all-examples.txt"), ExamplesRenderer(example_files).render),
    ]


# -- orchestration ---------------------------------------------------------


def export_files(
    input_layout: InputLayout,
    output_layout: OutputLayout,
) -> None:
    """Loads the source graph, plans, and writes every release artifact."""
    version = Version(input_layout.file(Domain.ROOT, constants.VERSIONS_FILE))
    current_version = version.current()
    releases = Releases(output_layout, version)
    issues = Issues(input_layout)

    with pretty_logger.BlockLog(message="Loading source graph", logger=log):
        source_graph = GraphLoader().load(issues.get_ttl_files())
    with pretty_logger.BlockLog(message="Preparing export graphs", logger=log):
        all_graph, current_graph = split_release_graphs(source_graph)
        vocab = VocabularyLoader(all_graph, version=current_version).load()

    artifacts = [
        *export_scoped(Scope.ALL, all_graph, vocab, current_version, releases),
        *export_scoped(Scope.CURRENT, current_graph, vocab, current_version, releases),
        *export_unscoped(all_graph, vocab, current_version, releases, output_layout, issues.get_example_files()),
    ]
    for artifact in artifacts:
        with pretty_logger.BlockLog(message=f"Exporting {artifact.name}: {artifact.path}", logger=log):
            write_artifact(artifact)


def main(argv: Optional[Sequence[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Generate all vocabulary/schema release files."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=constants.PROJECT_ROOT,
        help="Root directory of the schema.org input layout.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(schema.config.OUTPUTDIR),
        help="Root directory of the output site layout.",
    )

    args = parser.parse_args(argv)
    export_files(InputLayout(args.input_dir), OutputLayout(args.output_dir))


if __name__ == "__main__":
    main()
