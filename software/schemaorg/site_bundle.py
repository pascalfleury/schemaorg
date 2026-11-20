"""Immutable read-only data bundle loaded once for Stage 2 site tasks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rdflib

from schemaorg import constants
from schemaorg.collaborators import CollaboratorRegistry
from schemaorg.executor import TaskExecutor
from schemaorg.graph_loader import GraphLoader
from schemaorg.jsonld_slice import TermJsonLdIndex
from schemaorg.layout import (
    Domain,
    InputLayout,
    OutputLayout,
    Releases,
    StatsLayout,
    StatsProvider,
)
from schemaorg.model import Vocabulary, VocabularyLoader
from schemaorg.progress import ProgressReporter
from schemaorg.term_view import TermViewCatalog
from schemaorg.version import Version, VersionItem
from SchemaExamples.schemaexamples import SchemaExamples


@dataclass(frozen=True)
class SiteBundle:
    """All read-only inputs shared across site-rendering tasks."""

    input_layout: InputLayout
    target_version: VersionItem
    current_version: VersionItem
    release_file: Path
    graph: rdflib.Graph
    vocab: Vocabulary
    collaborators: CollaboratorRegistry
    catalog: TermViewCatalog
    jsonld_index: TermJsonLdIndex
    examples: SchemaExamples
    stats_providers: tuple[StatsProvider, ...]

    @classmethod
    def from_release(
        cls,
        input_layout: InputLayout,
        releases_layout: InputLayout | OutputLayout,
        target_version: VersionItem,
        progress: ProgressReporter,
        executor: TaskExecutor,
    ) -> SiteBundle:
        version_registry = Version(
            input_layout.file(Domain.ROOT, constants.VERSIONS_FILE)
        )
        current_version = version_registry.current()
        releases = Releases(releases_layout, version_registry)
        release_file = releases.file(target_version)
        if not release_file.is_file():
            raise FileNotFoundError(
                f"Release file not found: {release_file}. "
                "Please run --buildrelease first."
            )
        release_jsonld = releases.file(target_version, extension=".jsonld")

        with progress.task(
            f"Loading site bundle ({target_version.number()})",
            total=6,
            unit="steps",
        ) as p:
            p.step("release graph, examples, usage stats")
            loaded: list[Any] = executor.run_all([
                lambda: GraphLoader.load([release_file]),
                lambda: SchemaExamples.from_layout(input_layout),
                lambda: tuple(StatsLayout(input_layout).get_stats()),
            ])
            graph: rdflib.Graph = loaded[0]
            examples: SchemaExamples = loaded[1]
            stats_providers: tuple[StatsProvider, ...] = loaded[2]
            p.advance(3)

            p.step("vocabulary")
            vocab = VocabularyLoader(graph, version=target_version).load()
            p.advance(1)

            p.step("collaborators and json-ld slices")

            def _load_catalog() -> tuple[CollaboratorRegistry, TermViewCatalog]:
                collabs = CollaboratorRegistry.from_layout(input_layout, vocab)
                return collabs, TermViewCatalog.from_graph(
                    graph, vocab, collabs
                )

            derived: list[Any] = executor.run_all([
                _load_catalog,
                lambda: TermJsonLdIndex.from_graph(
                    graph,
                    jsonld_file=(
                        release_jsonld if release_jsonld.is_file() else None
                    ),
                ),
            ])
            collaborators: CollaboratorRegistry = derived[0][0]
            catalog: TermViewCatalog = derived[0][1]
            jsonld_index: TermJsonLdIndex = derived[1]
            p.advance(2)

        return cls(
            input_layout=input_layout,
            target_version=target_version,
            current_version=current_version,
            release_file=release_file,
            graph=graph,
            vocab=vocab,
            collaborators=collaborators,
            catalog=catalog,
            jsonld_index=jsonld_index,
            examples=examples,
            stats_providers=stats_providers,
        )
