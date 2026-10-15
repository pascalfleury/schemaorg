#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Examples text-bundle renderer."""

import logging
from pathlib import Path
from typing import Sequence

import SchemaExamples.schemaexamples as schemaexamples

log: logging.Logger = logging.getLogger(__name__)


class ExamplesRenderer:
    """All examples concatenated into one release text file."""

    def __init__(self, example_files: Sequence[Path]) -> None:
        self.example_files = example_files

    def render(self) -> str:
        if not schemaexamples.SchemaExamples.EXAMPLESLOADED:
            if not self.example_files:
                log.warning("No example files given; writing an empty examples file")
                return ""
            schemaexamples.SchemaExamples.loadExamplesFiles(
                [str(p) for p in self.example_files]
            )
        return str(schemaexamples.SchemaExamples.allExamplesSerialised())
