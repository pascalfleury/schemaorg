#!/usr/bin/env python3
"""CLI for generating all schema.org release files."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import logging
from pathlib import Path

from schemaorg import constants
from schemaorg.layout import Domain, InputLayout, NEXT_VERSION, OutputLayout
from schemaorg.progress import LogProgressReporter
from schemaorg.tasks.export_release_files import ExportReleaseFilesTask
from schemaorg.version import Version

log: logging.Logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> None:
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
        default=constants.PROJECT_ROOT / "data",
        help="Root directory containing the releases/ output directory.",
    )
    parser.add_argument(
        "--version",
        default=NEXT_VERSION,
        help="Target release version ('next', 'latest', or declared X.Y).",
    )

    args = parser.parse_args(argv)
    input_layout = InputLayout(args.input_dir)
    version_registry = Version(
        input_layout.file(Domain.ROOT, constants.VERSIONS_FILE)
    )
    ExportReleaseFilesTask(
        input_layout=input_layout,
        output_layout=OutputLayout(args.output_dir),
        version=version_registry.resolve(args.version),
        progress=LogProgressReporter(logger=log, log_steps=True),
    ).run()


if __name__ == "__main__":
    main()
