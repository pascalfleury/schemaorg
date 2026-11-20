"""Floating task that renders HTML definition pages for schema.org terms."""

from __future__ import annotations

from collections.abc import Sequence
import logging
from pathlib import Path
from typing import Any
import unicodedata

from schemaorg.executor import TaskExecutor, shard_sequence
from schemaorg.layout import Domain, OutputLayout
from schemaorg.progress import ProgressReporter
from schemaorg.site_bundle import SiteBundle
from schemaorg.template_renderer import TemplateRenderer
from schemaorg.term_view import TermKind

_MAX_SHARDS: int = 64


def _is_all(token: str) -> bool:
    return token.strip().upper() == "ALL"


def term_output_path(output_layout: OutputLayout, term_id: str) -> Path:
    """Resolve the destination HTML file path for a term identifier."""
    if not term_id:
        raise ValueError("Empty term_id")
    first = term_id[0]
    if first.islower():
        sub_dir = "properties"
    elif first.isupper() or first.isdigit():
        sub_dir = "types"
    else:
        raise ValueError(f"Invalid term_id: '{term_id}'")
    return output_layout.file(
        Domain.TERMS, f"{sub_dir}/{first}/{term_id}.html"
    )


class RenderTermPagesTask:
    """Renders term HTML pages from a SiteBundle into an OutputLayout."""

    def __init__(
        self,
        bundle: SiteBundle,
        output_layout: OutputLayout,
        build_opts: Sequence[str],
        term_ids: Sequence[str],
        progress: ProgressReporter,
        executor: TaskExecutor,
    ) -> None:
        self.bundle: SiteBundle = bundle
        self.output_layout: OutputLayout = output_layout
        self.build_opts: tuple[str, ...] = tuple(build_opts)
        self.term_ids: tuple[str, ...] = tuple(term_ids)
        self.progress: ProgressReporter = progress
        self.executor: TaskExecutor = executor

    def _stats_badges(self, uri: str) -> list[dict[str, str]]:
        if not uri:
            return []
        cleaned = unicodedata.normalize("NFC", uri.strip())
        badges: list[dict[str, str]] = []
        for provider in self.bundle.stats_providers:
            if badge := provider.stats_map.get(cleaned):
                badges.append({
                    "provider_name": provider.name,
                    "badge": badge,
                    "date": provider.date,
                    "description": provider.description,
                })
        return badges

    def run(self) -> int:
        if not self.term_ids:
            return 0
        term_list = (
            [v.id for v in self.bundle.catalog.all_views()]
            if any(_is_all(t) for t in self.term_ids)
            else list(self.term_ids)
        )
        if not term_list:
            return 0

        # Pre-create destination directories before concurrent workers write.
        for term_id in term_list:
            term = self.bundle.catalog.get(term_id)
            if term is not None and term.termType != TermKind.REFERENCE:
                term_output_path(self.output_layout, term.id)

        shards = shard_sequence(term_list, min(len(term_list), _MAX_SHARDS))

        def _render_shard(
            shard: tuple[str, ...],
        ) -> tuple[int, int, list[str], str]:
            renderer = TemplateRenderer(
                self.bundle.input_layout,
                self.bundle.target_version,
                self.build_opts,
            )
            template = renderer.get_template("terms/TermPage.j2")
            shard_written = 0
            missing: list[str] = []
            last_id = shard[-1]
            for term_id in shard:
                term = self.bundle.catalog.get(term_id)
                if term is None:
                    missing.append(term_id)
                    continue
                if term.termType == TermKind.REFERENCE:
                    continue

                try:
                    extra_vars: dict[str, Any] = {
                        "title": term.label,
                        "term": term,
                        "jsonldPayload": self.bundle.jsonld_index.render_for(
                            term
                        ),
                        "examples": self.bundle.examples.examplesForTerm(
                            term.id
                        ),
                        "stats_badges": self._stats_badges(term.uri),
                    }
                    html = renderer.render(template, extra_vars)
                    term_output_path(self.output_layout, term.id).write_text(
                        html, encoding="utf-8"
                    )
                    shard_written += 1
                except Exception as exc:
                    exc.add_note(f"While building term_id {term_id}")
                    raise
            return shard_written, len(shard), missing, last_id

        written = 0
        with self.progress.task(
            "Rendering term pages",
            total=len(term_list),
            unit="pages",
        ) as p:
            for shard_written, count, missing, last_id in self.executor.map(
                _render_shard, shards
            ):
                for term_id in missing:
                    p.log(f"No such term: {term_id}", logging.ERROR)
                p.step(last_id)
                written += shard_written
                p.advance(count)

        return written
