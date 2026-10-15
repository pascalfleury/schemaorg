#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""CSV table renderer for the types and properties of a Vocabulary."""

import csv
import functools
import io
import logging
import operator
from typing import Any, Dict, List, Optional, Sequence, Tuple

import rdflib
from schemaorg.model import EnumerationValue, SchemaProperty, SchemaTerm, Vocabulary
from schemaorg.sdo_uri import SdoUri
import SchemaTerms.localmarkdown as localmarkdown
import SchemaTerms.sdoterm as sdoterm
import util.textutils as textutils

log: logging.Logger = logging.getLogger(__name__)

Row = Dict[str, str]

TYPE_FIELDS: Sequence[str] = (
    "id",
    "label",
    "comment",
    "subTypeOf",
    "enumerationtype",
    "equivalentClass",
    "properties",
    "subTypes",
    "supersedes",
    "supersededBy",
    "isPartOf",
)
PROPERTY_FIELDS: Sequence[str] = (
    "id",
    "label",
    "comment",
    "subPropertyOf",
    "equivalentProperty",
    "subproperties",
    "domainIncludes",
    "rangeIncludes",
    "inverseOf",
    "supersedes",
    "supersededBy",
    "isPartOf",
)


def uriwrap(thing: Any) -> str:
    """Convert various types into uris. Sorts items if they are a list."""
    if not thing:
        return ""
    if isinstance(thing, (str, rdflib.URIRef)):
        return str(SdoUri(thing))
    if isinstance(
        thing, (sdoterm.SdoTermSequence, sdoterm.SdoTermOrId, sdoterm.SdoTerm)
    ):
        return uriwrap(getattr(thing, "ids", getattr(thing, "id", None)))
    try:
        return textutils.Array2String(sorted(map(uriwrap, thing)))
    except (TypeError, ValueError) as e:
        log.fatal(f"Cannot uriwrap {thing}:{e}")
        return ""


def _render_comment(raw_comment: Optional[str], wikilink_prefix: str) -> str:
    if not raw_comment:
        return ""
    return localmarkdown.Markdown.parse(raw_comment, wpre=wikilink_prefix).strip()


def _to_csv(rows: Sequence[Row], fields: Sequence[str]) -> str:
    with io.StringIO() as buffer:
        writer = csv.DictWriter(
            buffer,
            fieldnames=fields,
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()


class CsvRenderer:
    """Type and property tables of one vocabulary; the rows are computed once.

    Term links inside comments are relative to the site root (``/Thing``),
    as in every published release.
    """

    def __init__(self, vocab: Vocabulary, wikilink_prefix: str = "/") -> None:
        self.vocab = vocab
        self.wikilink_prefix = wikilink_prefix

    def _row(self, uri: SdoUri, term: SchemaTerm) -> Row:
        vocab = self.vocab
        part_of = SdoUri(term.isPartOf[0]) if term.isPartOf else uri
        layer = part_of.layer()

        row: Row = {
            "id": str(uri),
            "label": term.label or "",
            "comment": _render_comment(term.comment, self.wikilink_prefix),
            "supersedes": uriwrap(vocab.supersedes.get(uri.uri, ())),
            "supersededBy": uriwrap(
                term.supersededBy[0] if term.supersededBy else ""
            ),
            "isPartOf": "" if layer == "core" else str(SdoUri.for_layer(layer)),
        }

        if isinstance(term, SchemaProperty):
            row.update({
                "subPropertyOf": uriwrap(term.supers),
                "equivalentProperty": uriwrap(term.equivalents),
                "subproperties": uriwrap(vocab.subs.get(uri.uri, ())),
                "domainIncludes": uriwrap(term.domainIncludes),
                "rangeIncludes": uriwrap(term.rangeIncludes),
                "inverseOf": uriwrap(
                    term.inverseOf[0] if term.inverseOf else ""
                ),
            })
        else:
            row.update({
                "subTypeOf": uriwrap(term.supers),
                "equivalentClass": uriwrap(term.equivalents),
                "subTypes": uriwrap(vocab.subs.get(uri.uri, ())),
            })
            if isinstance(term, EnumerationValue):
                enum_parents = sorted(
                    (rt for rt in term.rdf_types if rt in vocab.enumerations),
                    key=str,
                )
                row["enumerationtype"] = uriwrap(
                    enum_parents[0] if enum_parents else ""
                )
            else:
                row["properties"] = uriwrap(
                    vocab.all_properties.get(uri.uri, ())
                )
        return row

    @functools.cached_property
    def _rows(self) -> Tuple[Tuple[Row, ...], Tuple[Row, ...]]:
        typedata: List[Row] = []
        propdata: List[Row] = []

        for key, term in self.vocab.all_terms().items():
            row = self._row(SdoUri(key), term)
            if isinstance(term, SchemaProperty):
                propdata.append(row)
            else:
                typedata.append(row)

        by_id = operator.itemgetter("id")
        return (
            tuple(sorted(typedata, key=by_id)),
            tuple(sorted(propdata, key=by_id)),
        )

    @staticmethod
    def _select(rows: Sequence[Row], include_retired: bool) -> Sequence[Row]:
        if include_retired:
            return rows
        return [r for r in rows if not SdoUri(r["isPartOf"]).is_retired()]

    @functools.cache
    def types(self, include_retired: bool) -> str:
        types, _ = self._rows
        return _to_csv(self._select(types, include_retired), TYPE_FIELDS)

    @functools.cache
    def properties(self, include_retired: bool) -> str:
        _, properties = self._rows
        return _to_csv(self._select(properties, include_retired), PROPERTY_FIELDS)
