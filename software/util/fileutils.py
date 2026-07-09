#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import enum
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Set, Union

import software


EXTENSIONS_FOR_FORMAT: Dict[str, str] = {
    "xml": "xml",
    "rdf": "rdf",
    "nquads": "nq",
    "nt": "nt",
    "json-ld": "jsonld",
    "turtle": "ttl",
    "csv": "csv",
}


class FileSelector(str, enum.Enum):
    """Enumeration describing the type of an SdoTerm."""

    ALL = "all"
    CURRENT = "current"

    def __str__(self) -> str:
        return str(self.value)


CHECKEDPATHS: Set[Path] = set()
FILESET_SELECTORS: FrozenSet[str] = frozenset([s.value for s in FileSelector])
FILESET_PROTOCOLS: FrozenSet[str] = frozenset(["http", "https"])




def isAll(selector: Union[str, FileSelector]) -> bool:
    """Check if a selector string is a variation of the 'All' token."""
    return str(selector).lower() == FileSelector.ALL


def checkFilePath(path: Union[str, Path]) -> None:
    full_path: Path = Path(path).resolve()
    if full_path not in CHECKEDPATHS:
        full_path.mkdir(parents=True, exist_ok=True)
        CHECKEDPATHS.add(full_path)




def mycopytree(src: str, dst: str, symlinks: bool = False, ignore: Optional[Callable[[str, List[str]], Iterable[str]]] = None) -> None:
    """Copy a file-system tree, copes with already existing directories."""
    try:
        shutil.copytree(src, dst, symlinks=symlinks, ignore=ignore, dirs_exist_ok=True)
    except shutil.Error as err:
        raise Exception(err.args[0])
