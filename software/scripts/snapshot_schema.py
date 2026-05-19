import logging
import os
import shutil
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union
import typing

if os.getcwd() not in sys.path:
    sys.path.insert(1, os.getcwd())
import software

from software.util.paths import DefaultInputLayout
from software.data_model.loader import GraphLoader
import scripts.buildfiles as buildfiles
import util.fileutils as fileutils
import util.pretty_logger as pretty_logger
import util.schema as schema

log: logging.Logger = logging.getLogger(__name__)


def snapshot_ttl(output_dir: str = "software/tests/snapshot") -> None:
    outputdir_copy: str = schema.config.OUTPUTDIR
    selectors_copy: Set[str] = fileutils.FILESET_SELECTORS
    protocols_copy: Set[str] = fileutils.FILESET_PROTOCOLS
    schema.config.OUTPUTDIR = ""
    fileutils.FILESET_SELECTORS = {"all"}
    fileutils.FILESET_PROTOCOLS = {"https"}

    log.info("Building snapshot file...")
    layout = DefaultInputLayout()
    loader = GraphLoader.from_layout(layout)
    loader.load_all()
    buildfiles.exportrdf("RDFExport.turtle", subdirectory_path=output_dir)
    log.info(f"Snapshot file created in {output_dir}")

    # Put back the original values.
    schema.config.OUTPUTDIR = outputdir_copy
    fileutils.FILESET_SELECTORS = selectors_copy
    fileutils.FILESET_PROTOCOLS = protocols_copy


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    snapshot_ttl()
