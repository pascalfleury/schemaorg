#!/usr/bin/env python3
"""Unified development and CI builder for Schema.org artifacts, site, and checks."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
import sys

from schemaorg import constants
from schemaorg.executor import (
    ProcessTaskExecutor,
    SequentialExecutor,
    TaskExecutor,
    ThreadTaskExecutor,
    default_worker_count,
)
from schemaorg.layout import (
    Domain,
    InputLayout,
    NEXT_VERSION,
    OutputLayout,
    Releases,
    checkDataDirectories,
)
from schemaorg.progress import LogProgressReporter, ProgressReporter
from schemaorg.site_bundle import SiteBundle
from schemaorg.tasks.export_release_files import ExportReleaseFilesTask
from schemaorg.tasks.export_site_metadata import ExportSiteMetadataTask
from schemaorg.tasks.prepare_site_static import PrepareSiteStaticTask
from schemaorg.tasks.render_docs_pages import RenderDocsPagesTask
from schemaorg.tasks.render_term_pages import RenderTermPagesTask
from schemaorg.tasks.run_unit_tests import RunUnitTestsTask
from schemaorg.tasks.validate_examples import (
    ShaclConfigError,
    ValidateExamplesTask,
)
from schemaorg.version import Version
from SchemaExamples.schemaexamples import SchemaExamples
import util.pretty_logger as pretty_logger

log: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuildOptions:
    """Resolved flags driving a single build run."""

    schema: bool
    site: bool
    tests: bool
    validate: bool
    output_dir: Path | None
    version: str
    clean: bool
    terms: tuple[str, ...]
    pages: tuple[str, ...]
    jobs: int


def parse_args(argv: Sequence[str] | None = None) -> BuildOptions:
    parser = argparse.ArgumentParser(
        prog="build",
        description=(
            f"Build {constants.SITENAME} schema release files and static site, "
            "run unit tests, and validate JSON-LD examples. All four stages are "
            "enabled by default; pass --no-<stage> to skip any stage."
        ),
    )
    parser.add_argument(
        "--schema",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate schema release artifacts (default: %(default)s).",
    )
    parser.add_argument(
        "--site",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Build static site pages and metadata (default: %(default)s).",
    )
    parser.add_argument(
        "--tests",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run the unit test suite (default: %(default)s).",
    )
    parser.add_argument(
        "--validate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Validate JSON-LD examples against SHACL shapes (default: %(default)s).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Redirect all generated outputs (releases/ and site files) into "
            "PATH instead of the standard layout (data/releases/<ver>/ and "
            "software/site/)."
        ),
    )
    parser.add_argument(
        "--version",
        default=NEXT_VERSION,
        help="Target version: 'next', 'latest', or declared X.Y (default: %(default)s).",
    )
    parser.add_argument(
        "--clean",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Clear output directory before building (default: %(default)s).",
    )
    parser.add_argument(
        "--terms",
        nargs="+",
        default=[],
        metavar="ID",
        help="Render only the specified term page IDs (implies partial site build).",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        default=[],
        metavar="NAME",
        help="Render only the specified docs page names (implies partial site build).",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=default_worker_count(),
        metavar="N",
        help="Number of parallel workers; 1 = sequential (default: %(default)s).",
    )
    ns = parser.parse_args(argv)
    if ns.jobs < 1:
        parser.error("--jobs must be >= 1")
    return BuildOptions(
        schema=bool(ns.schema),
        site=bool(ns.site),
        tests=bool(ns.tests),
        validate=bool(ns.validate),
        output_dir=ns.output_dir,
        version=ns.version,
        clean=bool(ns.clean),
        terms=tuple(ns.terms),
        pages=tuple(ns.pages),
        jobs=ns.jobs,
    )


def _clear_dir(target_dir: Path) -> None:
    if not target_dir.is_dir():
        return
    for item in target_dir.iterdir():
        if item.name == ".gitkeep":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _make_executors(jobs: int) -> tuple[TaskExecutor, TaskExecutor]:
    if jobs <= 1:
        seq = SequentialExecutor()
        return seq, seq
    return ProcessTaskExecutor(jobs), ThreadTaskExecutor(min(8, jobs))


def run_build(
    options: BuildOptions,
    input_layout: InputLayout,
    default_site_dir: Path,
    tests_dir: Path,
    progress: ProgressReporter,
    cpu_executor: TaskExecutor,
    io_executor: TaskExecutor,
) -> int:
    """Execute selected build stages; returns process exit code (0 on success)."""
    version_registry = Version(
        input_layout.file(Domain.ROOT, constants.VERSIONS_FILE)
    )
    target = version_registry.resolve(options.version)

    log.info(
        "Version: %s Released: %s",
        target.number(),
        target.date() or "unreleased",
    )

    if options.output_dir is None:
        releases_out = OutputLayout(input_layout.dir(Domain.DATA))
        site_out = OutputLayout(default_site_dir)
        releases_in: InputLayout | OutputLayout = input_layout
    else:
        unified_out = OutputLayout(options.output_dir)
        releases_out = unified_out
        site_out = unified_out
        releases_in = unified_out if options.schema else input_layout

    is_partial_site = bool(options.terms or options.pages)
    if options.clean and (
        options.site or (options.output_dir is not None and options.schema)
    ):
        # Clean once before Stage 1 so unified -o never wipes freshly built releases/.
        _clear_dir(site_out.output_dir)

    if options.schema:
        ExportReleaseFilesTask(
            input_layout=input_layout,
            output_layout=releases_out,
            version=target,
            progress=progress,
            executor=cpu_executor,
        ).run()

    if options.tests:
        summary = RunUnitTestsTask(
            tests_dir=tests_dir,
            skip_basics=False,
            progress=progress,
            executor=cpu_executor,
        ).run()
        if not summary.ok:
            failures = (
                summary.failure_count
                + summary.error_count
                + summary.unexpected_success_count
            )
            log.error("Unit tests failed (%d errors/failures)", failures)
            return 1

    if options.validate:
        examples = SchemaExamples.from_layout(input_layout)
        jsonld_examples = [
            ex for ex in examples.allExamples() if ex.hasJsonld()
        ]
        try:
            val_summary = ValidateExamplesTask(
                releases=Releases(releases_in, version_registry),
                version=target,
                examples=jsonld_examples,
                invalid_only=True,
                source_output=False,
                progress=progress,
                executor=cpu_executor,
            ).run()
        except ShaclConfigError as exc:
            log.error("SHACL validation configuration error: %s", exc)
            return os.EX_CONFIG
        if val_summary.error_count:
            log.error(
                "SHACL validation failed (%d invalid examples)",
                val_summary.error_count,
            )
            return 1

    if options.site:
        bundle = SiteBundle.from_release(
            input_layout=input_layout,
            releases_layout=releases_in,
            target_version=target,
            progress=progress,
            executor=io_executor,
        )
        PrepareSiteStaticTask(
            input_layout=input_layout,
            output_layout=site_out,
            target_version=target,
            current_version=bundle.current_version,
            clear_first=False,
            progress=progress,
            executor=io_executor,
        ).run()

        if is_partial_site:
            term_ids = options.terms
            page_names = options.pages
        else:
            term_ids = ("ALL",)
            page_names = ("ALL",)

        RenderTermPagesTask(
            bundle=bundle,
            output_layout=site_out,
            build_opts=(),
            term_ids=term_ids,
            progress=progress,
            executor=cpu_executor,
        ).run()

        RenderDocsPagesTask(
            bundle=bundle,
            output_layout=site_out,
            build_opts=(),
            page_names=page_names,
            progress=progress,
            executor=cpu_executor,
        ).run()

        ExportSiteMetadataTask(
            input_layout=input_layout,
            output_layout=site_out,
            version=target,
            vocab=bundle.vocab,
            progress=progress,
            executor=cpu_executor,
            releases_layout=releases_in,
        ).run()

    return 0


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    pretty_logger.MakeRootLogPretty()
    options = parse_args(argv)
    checkDataDirectories()

    cpu_executor, io_executor = _make_executors(options.jobs)
    exit_code = run_build(
        options=options,
        input_layout=InputLayout(constants.PROJECT_ROOT),
        default_site_dir=constants.PROJECT_ROOT / "software/site",
        tests_dir=constants.PROJECT_ROOT / "software/tests",
        progress=LogProgressReporter(logger=log, log_steps=False),
        cpu_executor=cpu_executor,
        io_executor=io_executor,
    )
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
