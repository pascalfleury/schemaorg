#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Writes the ALL/https turtle snapshot used by test_snapshot.py."""

import logging
from pathlib import Path
from typing import Optional, Union

from schemaorg import constants
from schemaorg.graph_loader import GraphLoader
from schemaorg.layout import Issues
from schemaorg.renderers import RdfRenderer
import scripts.buildfiles as buildfiles
import util.paths as paths

log: logging.Logger = logging.getLogger(__name__)

SNAPSHOT_FILENAME = "schemaorg-all-https.ttl"


def snapshot_ttl(output_dir: Optional[Union[str, Path]] = None) -> Path:
    out_dir = Path(output_dir or constants.PROJECT_ROOT / "software/tests/snapshot")
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Building snapshot file...")
    source_graph = GraphLoader().load(
        Issues(paths.DefaultInputLayout()).get_ttl_files()
    )
    all_graph, _ = buildfiles.split_release_graphs(source_graph)
    path = out_dir / SNAPSHOT_FILENAME
    path.write_text(RdfRenderer(all_graph).render("turtle"), encoding="utf-8")
    log.info(f"Snapshot file created in {path}")
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    snapshot_ttl()
