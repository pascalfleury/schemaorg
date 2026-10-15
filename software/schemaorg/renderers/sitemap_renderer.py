#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""XML sitemap renderer."""

from typing import List, Sequence

from schemaorg import constants
from schemaorg.model import Vocabulary
from schemaorg.version import VersionItem

SITEMAP_STATIC_PAGES: Sequence[str] = (
    "docs/schemas.html",
    "docs/full.html",
    "docs/gs.html",
    "docs/about.html",
    "docs/howwework.html",
    "docs/releases.html",
    "docs/faq.html",
    "docs/datamodel.html",
    "docs/developers.html",
    "docs/extension.html",
    "docs/meddocs.html",
    "docs/hotels.html",
)


class SitemapRenderer:
    """sitemap.xml listing every term page plus the static docs pages."""

    def __init__(self, vocab: Vocabulary, version: VersionItem) -> None:
        self.vocab = vocab
        self.version = version

    def render(self) -> str:
        version_date: str = str(self.version.date() or "")

        def node(t: str) -> str:
            return f""" <url>
   <loc>{constants.SCHEMA_URI}{t}</loc>
   <lastmod>{version_date}</lastmod>
 </url>
"""

        output: List[str] = [
            '<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        ]
        for term_id in sorted(t.id for t in self.vocab.all_terms().values()):
            output.append(node(term_id))
        for p in SITEMAP_STATIC_PAGES:
            output.append(node(p))
        output.append("</urlset>\n")
        return "".join(output)
