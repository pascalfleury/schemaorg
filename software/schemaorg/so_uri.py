#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Schema.org URI namespace and manipulation helpers."""

import logging
from typing import Union
from urllib.parse import urlparse

from rdflib import Namespace, URIRef

from schemaorg import constants

log = logging.getLogger(__name__)

SDO = Namespace(constants.SCHEMA_URI)


class SoUri:
    """Wrapper around a URI or term identifier for schema.org URI operations."""

    __slots__ = ("_raw",)

    def __init__(self, uri: Union[URIRef, str]) -> None:
        raw = str(uri)
        if not raw.startswith(("http://", "https://")):
            raw = f"{constants.SCHEMA_URI}{raw}"
        elif raw.startswith("http://"):
            host = urlparse(raw).hostname or ""
            if host == "schema.org" or host.endswith(".schema.org"):
                log.warning(
                    "Upgrading http:// schema.org URI to https://: %s", raw
                )
                raw = "https://" + raw.removeprefix("http://")
        self._raw = raw

    @property
    def uri(self) -> URIRef:
        return URIRef(self._raw)

    def is_so(self) -> bool:
        return self._raw.startswith(constants.SCHEMA_URI)

    def term_name(self) -> str:
        return self._raw.removeprefix(constants.SCHEMA_URI)

    def layer(self) -> str:
        host = urlparse(self._raw).hostname or ""
        if host.endswith(".schema.org"):
            return host.removesuffix(".schema.org")
        return "core"

    def __str__(self) -> str:
        return self._raw
