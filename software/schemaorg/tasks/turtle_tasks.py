"""Floating tasks that lint, merge, and annotate schema.org Turtle files."""

from __future__ import annotations

from collections.abc import Sequence
import itertools
from pathlib import Path

import rdflib

from schemaorg.executor import TaskExecutor
from schemaorg.progress import ProgressReporter
from schemaorg.publish.turtle import CustomTurtleSerializer
from schemaorg.sdo_uri import SdoUri
import util.schema_graph as graph

VALID_PARTS: tuple[str, ...] = ("pending", "attic", "meta", "GA")


def _write_turtle(g: graph.SchemaOrgGraph, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        CustomTurtleSerializer(g.g).serialize(stream)


class LintTurtleTask:
    """Reformats Turtle file(s) deterministically and verifies round-trip parity."""

    def __init__(
        self,
        files: Sequence[Path],
        output: Path | None,
        progress: ProgressReporter,
        executor: TaskExecutor,
    ) -> None:
        if not files:
            raise ValueError("LintTurtleTask requires at least one file.")
        if output is not None and len(files) > 1:
            raise ValueError("Cannot use output path with multiple files.")
        self.files: tuple[Path, ...] = tuple(files)
        self.output: Path | None = output
        self.progress: ProgressReporter = progress
        self.executor: TaskExecutor = executor

    def run(self) -> list[Path]:
        def _lint_one(source_path: Path) -> Path:
            target_path = (
                self.output if self.output is not None else source_path
            )
            g = graph.SchemaOrgGraph([source_path])
            _write_turtle(g, target_path)
            if not g.IdenticalTo(graph.SchemaOrgGraph([target_path])):
                raise ValueError(
                    f"Linting file {source_path} lost information."
                )
            return target_path

        written: list[Path] = []
        with self.progress.task(
            "Linting Turtle files",
            total=len(self.files),
            unit="files",
        ) as p:
            for target_path in self.executor.map(_lint_one, self.files):
                p.step(target_path.name)
                written.append(target_path)
                p.advance(1)
        return written


class MergeTurtleTask:
    """Merges multiple Turtle files into one deterministic Turtle file."""

    def __init__(
        self,
        files: Sequence[Path],
        output: Path,
        progress: ProgressReporter,
        executor: TaskExecutor,
    ) -> None:
        if not files:
            raise ValueError("MergeTurtleTask requires at least one file.")
        self.files: tuple[Path, ...] = tuple(files)
        self.output: Path = output
        self.progress: ProgressReporter = progress
        self.executor: TaskExecutor = executor

    def run(self) -> Path:
        with self.progress.task(
            f"Merging Turtle files ({self.output.name})",
            total=len(self.files),
            unit="files",
        ) as p:
            p.step(self.output.name)
            # SchemaOrgGraph loads the whole sequence into a single graph.
            merged = graph.SchemaOrgGraph(self.files)
            _write_turtle(merged, self.output)

            written = graph.SchemaOrgGraph([self.output])

            def _verify_one(path: Path) -> str:
                if not written.FullyContains(graph.SchemaOrgGraph([path])):
                    raise ValueError(
                        f"Merging files into {self.output} lost information "
                        f"from {path}."
                    )
                return path.name

            for name in self.executor.map(_verify_one, self.files):
                p.step(name)
                p.advance(1)
        return self.output


class AnnotateTurtleTask:
    """Sets or clears schema:isPartOf annotations on types and properties."""

    def __init__(
        self,
        files: Sequence[Path],
        output: Path | None,
        part_of: str,
        progress: ProgressReporter,
        executor: TaskExecutor,
    ) -> None:
        if not files:
            raise ValueError("AnnotateTurtleTask requires at least one file.")
        if output is not None and len(files) > 1:
            raise ValueError("Cannot use output path with multiple files.")
        if part_of not in VALID_PARTS:
            raise ValueError(
                f"PartOf annotation {part_of!r} is not valid: "
                f"select one of {list(VALID_PARTS)}"
            )
        self.files: tuple[Path, ...] = tuple(files)
        self.output: Path | None = output
        self.part_of: str = part_of
        self.progress: ProgressReporter = progress
        self.executor: TaskExecutor = executor

    def run(self) -> list[Path]:
        # GA is the unannotated state.
        new_part: rdflib.URIRef | None = (
            SdoUri.for_layer(self.part_of).uri if self.part_of != "GA" else None
        )

        def _annotate_one(source_path: Path) -> Path:
            target_path = (
                self.output if self.output is not None else source_path
            )
            g = graph.SchemaOrgGraph([source_path])
            g.remove((None, graph.SCHEMAORG.isPartOf, None))
            if new_part is not None:
                for sub in itertools.chain(g.Types(), g.Properties()):
                    g.add((sub, graph.SCHEMAORG.isPartOf, new_part))
            _write_turtle(g, target_path)
            return target_path

        written: list[Path] = []
        with self.progress.task(
            f"Annotating Turtle files ({self.part_of})",
            total=len(self.files),
            unit="files",
        ) as p:
            for target_path in self.executor.map(_annotate_one, self.files):
                p.step(target_path.name)
                written.append(target_path)
                p.advance(1)
        return written
