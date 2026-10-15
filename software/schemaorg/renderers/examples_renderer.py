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
        if not self.example_files:
            log.warning("No example files given; writing an empty examples file")
            return ""
        loaded = schemaexamples.SchemaExamples.from_files(self.example_files)
        return "\n".join(ex.serialize() for ex in loaded.allExamples())
