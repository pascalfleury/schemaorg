#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Import standard python libraries

import argparse
import logging
import os
import sys
import typing
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Sequence, Set, Tuple, Union

if os.getcwd() not in sys.path:
    sys.path.insert(1, os.getcwd())
import software

from software.data_model.models import SdoTerm
from software.data_model.type_map import SdoTermType
from software.data_model.registry import TermRegistry
import util.pretty_logger as pretty_logger


# Import schema.org libraries




log: logging.Logger = logging.getLogger(__name__)


def generateTerms(tags: bool = False) -> Generator[str, None, None]:
    terms = TermRegistry.get_instance().get_all_terms()
    for term in terms:
        if not isinstance(term, SdoTerm):
            continue
        label: str = ""
        if tags:
            if getattr(term, "termType", None) == SdoTermType.PROPERTY:
                label = " p"
            elif getattr(term, "termType", None) == SdoTermType.TYPE:
                label = " t"
            elif getattr(term, "termType", None) == SdoTermType.DATATYPE:
                label = " d"
            elif getattr(term, "termType", None) == SdoTermType.ENUMERATION:
                label = " e"
            elif getattr(term, "termType", None) == SdoTermType.ENUMERATIONVALUE:
                label = " v"
        yield term.id + label + "\n"


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument(
        "-t",
        "--tagtype",
        default=False,
        action="store_true",
        help="Add a termtype to name",
    )
    parser.add_argument("-o", "--output", required=True, help="output file")
    args_parsed: argparse.Namespace = parser.parse_args()
    filename: str = args_parsed.output
    with pretty_logger.BlockLog(
        logger=log, message=f"Writing term list to file {filename}"
    ):
        with open(filename, "w") as handle:
            for term_line in generateTerms(tags=args_parsed.tagtype):
                handle.write(term_line)
