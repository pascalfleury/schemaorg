#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Artifact description and writer for release exports."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Tuple

from schemaorg.renderers.postprocess import PostProcessor


@dataclass(frozen=True)
class Artifact:
    """One output file: its renderer, destination, and text post-processors."""

    name: str
    path: Path
    render: Callable[[], str]
    post: Tuple[PostProcessor, ...] = ()


def write_artifact(artifact: Artifact) -> None:
    content = artifact.render()
    for step in artifact.post:
        content = step(content)
    artifact.path.write_text(content, encoding="utf-8")
