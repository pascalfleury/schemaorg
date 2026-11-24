"""Floating task that generates all 35 schema.org release artifacts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import functools
from functools import partial
from pathlib import Path

import rdflib

from schemaorg import constants
from schemaorg.executor import TaskExecutor
from schemaorg.graph_loader import GraphLoader, split_release_graphs
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
from schemaorg.progress import ProgressReporter, TaskProgress
from schemaorg.renderers import (
    CsvRenderer,
    OwlRenderer,
    PostProcessor,
    RdfRenderer,
    ShapesRenderer,
    protocol_swap,
    render_examples,
    render_http_equivs,
    render_jsonld_context,
)
from schemaorg.sdo_uri import SDO
from schemaorg.version import Version, VersionItem


@dataclass(frozen=True)
class Artifact:
    """One output file: its renderer, destination, and text post-processors."""

    name: str
    path: Path
    render: Callable[[], str]
    post: tuple[PostProcessor, ...]


def write_artifact(artifact: Artifact) -> None:
    content = artifact.render()
    for step in artifact.post:
        content = step(content)
    artifact.path.write_text(content, encoding="utf-8")


def write_artifacts(
    artifacts: Sequence[Artifact],
    executor: TaskExecutor,
    progress: TaskProgress,
) -> list[Path]:
    """Write artifacts grouped by shared render closure via executor."""
    by_render: dict[int, list[Artifact]] = {}
    for artifact in artifacts:
        artifact.path.parent.mkdir(parents=True, exist_ok=True)
        by_render.setdefault(id(artifact.render), []).append(artifact)
    groups = list(by_render.values())

    def _write_group(group: list[Artifact]) -> list[tuple[str, str]]:
        done: list[tuple[str, str]] = []
        for artifact in group:
            write_artifact(artifact)
            done.append((artifact.name, artifact.path.name))
        return done

    for finished in executor.map(_write_group, groups):
        for name, filename in finished:
            progress.step(f"{name} ({filename})")
            progress.advance(1)

    return [a.path for a in artifacts]


# Each (https, http) file pair shares one render; only post-processing differs.
PROTOCOL_VARIANTS: tuple[tuple[Protocol, tuple[PostProcessor, ...]], ...] = (
    (Protocol.HTTPS, ()),
    (Protocol.HTTP, (protocol_swap(),)),
)


def export_scoped(
    scope: Scope,
    graph: rdflib.Graph,
    csv: CsvRenderer,
    version: VersionItem,
    releases: Releases,
) -> list[Artifact]:
    """RDF and CSV release artifacts for one scope (no file I/O)."""
    rdf = RdfRenderer(graph)
    include_retired = scope == Scope.ALL
    scoped_renders: tuple[tuple[str, str, Callable[[], str]], ...] = (
        (
            "RDFExport.json-ld",
            ".jsonld",
            functools.cache(partial(rdf.render, "json-ld")),
        ),
        (
            "RDFExport.nquads",
            ".nq",
            functools.cache(
                partial(rdf.render, "nquads", SDO[version.number()])
            ),
        ),
        ("RDFExport.nt", ".nt", functools.cache(partial(rdf.render, "nt"))),
        ("RDFExport.rdf", ".rdf", functools.cache(partial(rdf.render, "rdf"))),
        (
            "RDFExport.turtle",
            ".ttl",
            functools.cache(partial(rdf.render, "turtle")),
        ),
        (
            "CSVExports",
            "-types.csv",
            functools.cache(partial(csv.types, include_retired)),
        ),
        (
            "CSVExports",
            "-properties.csv",
            functools.cache(partial(csv.properties, include_retired)),
        ),
    )
    return [
        Artifact(
            name,
            releases.file(
                version=version,
                protocol=protocol,
                scope=scope,
                extension=ext,
            ),
            render,
            finisher,
        )
        for protocol, finisher in PROTOCOL_VARIANTS
        for name, ext, render in scoped_renders
    ]


def export_release_unscoped(
    graph: rdflib.Graph,
    vocab: Vocabulary,
    version: VersionItem,
    releases: Releases,
    example_files: Sequence[Path],
) -> list[Artifact]:
    """Vocabulary-wide schema release artifacts (no file I/O)."""
    owl = OwlRenderer(graph, version)
    shapes = ShapesRenderer(graph)

    examples_path = releases.file(
        version=version, filename="schemaorg-all-examples.txt"
    )
    return [
        Artifact(
            "Context",
            releases.file(
                version=version, filename="schemaorgcontext.jsonld"
            ),
            partial(render_jsonld_context, graph, vocab),
            (),
        ),
        Artifact(
            "Owl",
            releases.file(version=version, filename="schemaorg.owl"),
            owl.render,
            (),
        ),
        Artifact(
            "Httpequivs",
            releases.file(version=version, filename="httpequivs.ttl"),
            partial(render_http_equivs, vocab),
            (),
        ),
        Artifact(
            "Shex_Shacl",
            releases.file(
                version=version, protocol="", scope="shapes", extension=".shexj"
            ),
            shapes.shex,
            (),
        ),
        Artifact(
            "Shex_Shacl",
            releases.file(
                version=version, protocol="", scope="shapes", extension=".shacl"
            ),
            shapes.shacl,
            (),
        ),
        Artifact(
            "Shex_Shacl",
            releases.file(
                version=version,
                protocol="",
                scope="subclasses",
                extension=".shacl",
            ),
            shapes.subclasses,
            (),
        ),
        Artifact(
            "Examples",
            examples_path,
            partial(render_examples, example_files, output_path=examples_path),
            (),
        ),
    ]


class ExportReleaseFilesTask:
    """Loads source TTL/example files and writes all 35 release artifacts."""

    def __init__(
        self,
        input_layout: InputLayout,
        output_layout: OutputLayout,
        version: VersionItem,
        progress: ProgressReporter,
        executor: TaskExecutor,
    ) -> None:
        self.input_layout: InputLayout = input_layout
        self.output_layout: OutputLayout = output_layout
        self.version: VersionItem = version
        self.progress: ProgressReporter = progress
        self.executor: TaskExecutor = executor

    def run(self) -> list[Path]:
        version_obj = Version(
            self.input_layout.file(Domain.ROOT, constants.VERSIONS_FILE)
        )
        releases = Releases(self.output_layout, version_obj)
        issues = Issues(self.input_layout)

        with self.progress.task(
            f"Exporting release files ({self.version.number()})",
            total=35,
            unit="files",
        ) as p:
            p.step("loading source graph")
            source_graph = GraphLoader.load(issues.get_ttl_files())

            p.step("preparing export graphs")
            all_graph, current_graph = split_release_graphs(source_graph)
            vocab = VocabularyLoader(all_graph, version=self.version).load()

            csv = CsvRenderer(vocab)
            artifacts = [
                *export_scoped(
                    Scope.ALL, all_graph, csv, self.version, releases
                ),
                *export_scoped(
                    Scope.CURRENT, current_graph, csv, self.version, releases
                ),
                *export_release_unscoped(
                    all_graph,
                    vocab,
                    self.version,
                    releases,
                    issues.get_example_files(),
                ),
            ]
            expected_paths = {a.path for a in artifacts}
            target_dir = releases.dir(self.version)
            if target_dir.is_dir():
                for existing in target_dir.iterdir():
                    if existing.is_file() and existing not in expected_paths:
                        existing.unlink()

            written = write_artifacts(artifacts, self.executor, p)

        return written
