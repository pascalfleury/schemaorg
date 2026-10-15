#!/usr/bin/env python3
"""Writes the ALL/https Turtle snapshot of the full vocabulary."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import logging
from pathlib import Path

from schemaorg import constants
from schemaorg.graph_loader import GraphLoader
from schemaorg.layout import Issues
from schemaorg.renderers import RdfRenderer
import scripts.buildfiles as buildfiles
import util.paths as paths

log: logging.Logger = logging.getLogger(__name__)

SNAPSHOT_FILENAME: str = "schemaorg-all-https.ttl"


def snapshot_ttl(output_dir: str | Path | None = None) -> Path:
    out_dir = Path(output_dir or constants.PROJECT_ROOT / "software/tests/snapshot")
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Building snapshot file...")
    source_graph = GraphLoader().load(
        Issues(paths.DefaultInputLayout()).get_ttl_files()
    )
    all_graph, _ = buildfiles.split_release_graphs(source_graph)
    path = out_dir / SNAPSHOT_FILENAME
    path.write_text(RdfRenderer(all_graph).render("turtle"), encoding="utf-8")
    log.info("Snapshot file created in %s", path)
    return path


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory for snapshot Turtle file",
    )
    args = parser.parse_args(argv)
    snapshot_ttl(output_dir=args.output)


if __name__ == "__main__":
    main()
