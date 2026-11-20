#!/usr/bin/env python3
"""CLI orchestrator that builds the schema.org release files and website."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import logging
import os
from pathlib import Path
import sys

from schemaorg import constants
from schemaorg.executor import ProcessTaskExecutor, default_worker_count
from schemaorg.layout import (
    Domain,
    InputLayout,
    NEXT_VERSION,
    OutputLayout,
    Releases,
    checkDataDirectories,
)
from schemaorg.progress import LogProgressReporter
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
from schemaorg.version import Version, VersionItem
from SchemaExamples.schemaexamples import SchemaExamples
import util.pretty_logger as pretty_logger

log: logging.Logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _parse_args(args_list: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-a",
        "--autobuild",
        action="store_true",
        help="clear output directory and build all components - overrides all other settings",
    )
    parser.add_argument(
        "-c",
        "--clearfirst",
        action="store_true",
        help="clear output directory before creating contents",
    )
    parser.add_argument(
        "-d",
        "--docspages",
        default=[],
        action="extend",
        nargs="*",
        help="create docs page(repeatable) - ALL = all pages",
    )
    parser.add_argument(
        "-f",
        "--files",
        default=[],
        action="extend",
        nargs="*",
        help="create the release files (always the complete set; any value such as ALL triggers it)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="output site directory (default: ./software/site)",
    )
    parser.add_argument(
        "-r",
        "--runtests",
        action="store_true",
        help="run test scripts before creating contents",
    )
    parser.add_argument(
        "-s",
        "--static",
        action="store_true",
        help="Refresh static docs in site image",
    )
    parser.add_argument(
        "-t",
        "--terms",
        default=[],
        action="extend",
        nargs="*",
        help="create page for term (repeatable) - ALL = all terms",
    )
    parser.add_argument(
        "-b",
        "--buildoption",
        default=[],
        action="extend",
        nargs="*",
        help="build option(repeatable) - flags to be passed to build code",
    )
    parser.add_argument(
        "--shacltests",
        action="store_true",
        help="run the post generation SHACL tests",
    )
    parser.add_argument(
        "-release",
        "--release",
        action="store_true",
        help="Build the release files into the releases data directory",
    )
    parser.add_argument(
        "--buildrelease",
        action="store_true",
        help="Build the release files and save them into the releases data directory",
    )
    parser.add_argument(
        "--buildsite",
        action="store_true",
        help="Build the website from the releases directory + static content + stats",
    )
    parser.add_argument(
        "--version",
        default=NEXT_VERSION,
        help="Target release version ('next', 'latest', or declared X.Y)",
    )
    return parser.parse_args(args_list)


def _run_unit_tests(tests_dir: Path, progress: LogProgressReporter) -> None:
    summary = RunUnitTestsTask(
        tests_dir=tests_dir,
        skip_basics=False,
        progress=progress,
        executor=ProcessTaskExecutor(default_worker_count()),
    ).run()
    if not summary.ok:
        failures = (
            summary.failure_count
            + summary.error_count
            + summary.unexpected_success_count
        )
        log.error("Unit tests failed (%d errors/failures)", failures)
        sys.exit(1)


def _run_shacl_validation(
    input_layout: InputLayout,
    releases_layout: InputLayout | OutputLayout,
    version_registry: Version,
    target_version: VersionItem,
    examples: SchemaExamples | None,
    progress: LogProgressReporter,
) -> None:
    loaded_examples = examples or SchemaExamples.from_layout(input_layout)
    jsonld_examples = [
        ex for ex in loaded_examples.allExamples() if ex.hasJsonld()
    ]
    releases = Releases(releases_layout, version_registry)
    try:
        summary = ValidateExamplesTask(
            releases=releases,
            version=target_version,
            examples=jsonld_examples,
            invalid_only=True,
            source_output=False,
            progress=progress,
            executor=ProcessTaskExecutor(default_worker_count()),
        ).run()
    except ShaclConfigError as exc:
        log.error("SHACL validation reported errors: %s", exc)
        sys.exit(os.EX_CONFIG)

    if summary.error_count:
        log.error(
            "SHACL validation reported errors (%d invalid examples). Failing build.",
            summary.error_count,
        )
        sys.exit(1)


def main(argv: Sequence[str] | None = None) -> None:
    pretty_logger.MakeRootLogPretty()
    args = _parse_args(argv)
    checkDataDirectories()

    input_layout = InputLayout(constants.PROJECT_ROOT)
    version_registry = Version(
        input_layout.file(Domain.ROOT, constants.VERSIONS_FILE)
    )
    target = version_registry.resolve(args.version)
    tests_dir = constants.PROJECT_ROOT / "software/tests"
    progress = LogProgressReporter(logger=log, log_steps=False)

    build_all = bool(
        args.autobuild or args.release or args.shacltests or args.buildrelease
    )
    term_ids = ("ALL",) if build_all else tuple(args.terms)
    page_names = ("ALL",) if build_all else tuple(args.docspages)
    want_files = bool(build_all or args.files or args.buildsite)
    build_opts = tuple(args.buildoption)

    log.info(
        "Version: %s Released: %s",
        target.number(),
        target.date() or "unreleased",
    )

    tests_ran = False
    shacl_ran = False

    if args.buildrelease or args.release:
        log.info("=== STAGE 1: BUILDING RELEASE VERSION ===")
        if args.runtests or args.autobuild:
            _run_unit_tests(tests_dir, progress)
            tests_ran = True

        releases_out = OutputLayout(input_layout.dir(Domain.DATA))
        ExportReleaseFilesTask(
            input_layout=input_layout,
            output_layout=releases_out,
            version=target,
            progress=progress,
            executor=ProcessTaskExecutor(default_worker_count()),
        ).run()

        _run_shacl_validation(
            input_layout=input_layout,
            releases_layout=releases_out,
            version_registry=version_registry,
            target_version=target,
            examples=None,
            progress=progress,
        )
        shacl_ran = True
        log.info("=== STAGE 1: RELEASE BUILD COMPLETED SUCCESSFULLY ===")

    build_site_requested = bool(
        args.buildsite
        or args.autobuild
        or args.static
        or args.files
        or args.docspages
        or args.terms
    )
    if build_site_requested:
        log.info("=== STAGE 2: BUILDING SITE ===")
        bundle = SiteBundle.from_release(
            input_layout=input_layout,
            releases_layout=input_layout,
            target_version=target,
            progress=progress,
        )
        site_dir = (
            Path(args.output)
            if args.output
            else constants.PROJECT_ROOT / "software/site"
        )
        site_output = OutputLayout(site_dir)
        log.info('Building site in "%s" directory', site_dir)

        PrepareSiteStaticTask(
            input_layout=input_layout,
            output_layout=site_output,
            target_version=target,
            current_version=bundle.current_version,
            clear_first=bool(args.clearfirst or args.autobuild),
            progress=progress,
        ).run()

        if (args.runtests or args.autobuild) and not tests_ran:
            _run_unit_tests(tests_dir, progress)
            tests_ran = True

        RenderTermPagesTask(
            bundle=bundle,
            output_layout=site_output,
            build_opts=build_opts,
            term_ids=term_ids,
            progress=progress,
        ).run()

        RenderDocsPagesTask(
            bundle=bundle,
            output_layout=site_output,
            build_opts=build_opts,
            page_names=page_names,
            progress=progress,
        ).run()

        if want_files:
            ExportSiteMetadataTask(
                input_layout=input_layout,
                output_layout=site_output,
                version=target,
                vocab=bundle.vocab,
                progress=progress,
                executor=ProcessTaskExecutor(default_worker_count()),
            ).run()

        if args.shacltests and not shacl_ran:
            _run_shacl_validation(
                input_layout=input_layout,
                releases_layout=input_layout,
                version_registry=version_registry,
                target_version=target,
                examples=bundle.examples,
                progress=progress,
            )
            shacl_ran = True

        log.info("=== STAGE 2: SITE BUILD COMPLETED SUCCESSFULLY ===")

    if (args.runtests or args.shacltests) and not (
        build_site_requested or args.buildrelease or args.release
    ):
        log.info("=== RUNNING SCRIBED TEST SUITES ===")
        if args.runtests and not tests_ran:
            _run_unit_tests(tests_dir, progress)
        if args.shacltests and not shacl_ran:
            _run_shacl_validation(
                input_layout=input_layout,
                releases_layout=input_layout,
                version_registry=version_registry,
                target_version=target,
                examples=None,
                progress=progress,
            )


if __name__ == "__main__":
    main()
