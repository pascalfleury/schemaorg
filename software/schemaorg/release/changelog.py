"""Release changelog domain: data computation, Jinja2 rendering, and releases.html."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

import jinja2

from schemaorg import constants
from schemaorg.layout import Domain
from schemaorg.release.git_repo import GitRepo
from schemaorg.tasks.compare_vocabulary import VocabularyDiffReport

_PR_RE: re.Pattern[str] = re.compile(r"\(#(\d+)\)")
_DATA_PREFIX: str = f"{Domain.DATA}/"
_RELEASES_PREFIX: str = f"{Domain.DATA}/{Domain.RELEASE}/"
_SEMANTIC_DATA_SUFFIXES: tuple[str, ...] = (".ttl", ".txt")
_MAX_VOCAB_DIFF_LINES: int = 120
_CANONICAL_REPO_URL: str = "https://github.com/schemaorg/schemaorg"

_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"
BRIEF_TEMPLATE: str = "changelog_brief.md.j2"
ROW_TEMPLATE: str = "changelog_row.html.j2"


@dataclass(frozen=True)
class CommitChange:
    """Classified commit entry with precomputed display fields."""

    sha: str
    subject: str
    clean_subject: str
    body: str
    first_body_line: str
    pr_number: str | None
    files: tuple[str, ...]
    data_files: tuple[str, ...]
    is_mixed: bool = False


@dataclass(frozen=True)
class ReleaseChanges:
    """Commits since the last release split into schema/data vs. infra/software."""

    baseline_sha: str
    head_sha: str
    schema_commits: tuple[CommitChange, ...]
    infra_commits: tuple[CommitChange, ...]


@dataclass(frozen=True)
class VocabDelta:
    """Capped vocabulary diff view for changelog templates."""

    previous_count: int
    current_count: int
    added: tuple[str, ...]
    dropped: tuple[str, ...]
    changed_count: int
    report_lines: tuple[str, ...]
    truncated_count: int


@dataclass(frozen=True)
class ChangelogData:
    """Complete structured payload fed to release changelog templates."""

    sitename: str
    repo_url: str
    previous_version: str
    next_version: str
    release_date: str
    changes: ReleaseChanges
    vocab_delta: VocabDelta | None

    @property
    def infra_pr_numbers(self) -> tuple[str, ...]:
        return tuple(
            c.pr_number for c in self.changes.infra_commits if c.pr_number
        )


def canonical_repo_url(repo: GitRepo) -> str:
    """Resolve canonical GitHub repo URL (prefers upstream; avoids personal forks)."""
    found = repo.remote_url()
    if found is None:
        return _CANONICAL_REPO_URL
    remote, normalized = found
    if (
        remote == "origin"
        and normalized.startswith("https://github.com/")
        and normalized.endswith("/schemaorg")
    ):
        return _CANONICAL_REPO_URL
    return normalized


def find_baseline(repo: GitRepo, previous_version: str) -> str:
    """Locate baseline commit via v<prev>-release tag or latest versions.json edit."""
    sha = repo.resolve_tag(
        f"v{previous_version}-release"
    ) or repo.last_commit_for(constants.VERSIONS_FILE)
    if sha is None:
        raise RuntimeError(
            f"Cannot locate baseline commit for release {previous_version}"
        )
    return sha


def classify_commit(
    files: Sequence[str],
) -> tuple[Literal["schema", "infra"], bool]:
    """Classify changed paths into ('schema'|'infra', is_mixed).

    Generated data/releases/** paths are ignored so exporter refreshes do not
    masquerade as schema edits.
    """
    non_generated = [
        f for f in files if f and not f.startswith(_RELEASES_PREFIX)
    ]
    if not non_generated:
        return "infra", False

    data_files = [f for f in non_generated if f.startswith(_DATA_PREFIX)]
    other_files = [f for f in non_generated if not f.startswith(_DATA_PREFIX)]

    if data_files and not other_files:
        return "schema", False
    if not data_files:
        return "infra", False

    # Mixed commit: surface under schema if semantic data files changed or dominate.
    has_semantic_data = any(
        f.endswith(_SEMANTIC_DATA_SUFFIXES) for f in data_files
    )
    if has_semantic_data or len(data_files) >= len(other_files):
        return "schema", True
    return "infra", True


def collect_changes(repo: GitRepo, baseline_sha: str) -> ReleaseChanges:
    """Collect and classify commits in <baseline_sha>..HEAD into schema vs. infra."""
    head_sha = repo.short_rev("HEAD")
    base_short = repo.short_rev(baseline_sha)

    schema_commits: list[CommitChange] = []
    infra_commits: list[CommitChange] = []

    for commit in repo.commits_since(baseline_sha):
        pr_match = _PR_RE.search(commit.subject)
        group, is_mixed = classify_commit(commit.files)
        data_files = tuple(
            f
            for f in commit.files
            if f.startswith(_DATA_PREFIX) and not f.startswith(_RELEASES_PREFIX)
        )
        first_line = commit.body.splitlines()[0].strip() if commit.body else ""
        if first_line == commit.subject:
            first_line = ""
        change = CommitChange(
            sha=commit.sha,
            subject=commit.subject,
            clean_subject=_PR_RE.sub("", commit.subject).strip(),
            body=commit.body,
            first_body_line=first_line,
            pr_number=pr_match.group(1) if pr_match else None,
            files=commit.files,
            data_files=data_files,
            is_mixed=is_mixed,
        )
        if group == "schema":
            schema_commits.append(change)
        else:
            infra_commits.append(change)

    return ReleaseChanges(
        baseline_sha=base_short,
        head_sha=head_sha,
        schema_commits=tuple(schema_commits),
        infra_commits=tuple(infra_commits),
    )


def prepare_changelog_data(
    repo_url: str,
    previous_version: str,
    next_version: str,
    release_date: str,
    changes: ReleaseChanges,
    vocab_diff: VocabularyDiffReport | None,
) -> ChangelogData:
    """Assemble structured ChangelogData ready for template rendering."""
    vocab_delta: VocabDelta | None = None
    if vocab_diff is not None:
        all_lines = vocab_diff.formatted_report.strip().splitlines()
        capped = tuple(all_lines[:_MAX_VOCAB_DIFF_LINES])
        truncated = max(0, len(all_lines) - _MAX_VOCAB_DIFF_LINES)
        vocab_delta = VocabDelta(
            previous_count=vocab_diff.previous_count,
            current_count=vocab_diff.current_count,
            added=vocab_diff.added,
            dropped=vocab_diff.dropped,
            changed_count=vocab_diff.changed_count,
            report_lines=capped,
            truncated_count=truncated,
        )
    return ChangelogData(
        sitename=constants.SITENAME,
        repo_url=repo_url,
        previous_version=previous_version,
        next_version=next_version,
        release_date=release_date,
        changes=changes,
        vocab_delta=vocab_delta,
    )


def _jinja_env(templates_dir: Path) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_dir),
        autoescape=lambda name: bool(name and ".html" in name),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_changelog_brief(
    data: ChangelogData, templates_dir: Path = _TEMPLATES_DIR
) -> str:
    """Render the frontier-model Markdown brief from ChangelogData."""
    return _jinja_env(templates_dir).get_template(BRIEF_TEMPLATE).render(data=data)


def render_default_row(
    data: ChangelogData, templates_dir: Path = _TEMPLATES_DIR
) -> str:
    """Render the starter docs/releases.html <tr> block from ChangelogData."""
    return _jinja_env(templates_dir).get_template(ROW_TEMPLATE).render(data=data)


def insert_release_row(releases_html_path: Path, row_html: str) -> None:
    """Prepend a curated <tr> release block to the table in docs/releases.html."""
    trimmed = row_html.strip()
    if not (trimmed.startswith("<tr") and trimmed.endswith("</tr>")):
        raise ValueError("Changelog entry must be a well-formed <tr>...</tr> block")

    content = releases_html_path.read_text(encoding="utf-8")
    anchor_patterns = (
        r"(<!--\s*note:.*?-->\s*\n)",
        r"(<tbody>\s*\n)",
    )
    for pat in anchor_patterns:
        match = re.search(pat, content, flags=re.IGNORECASE)
        if match:
            idx = match.end()
            updated = f"{content[:idx]}\n{trimmed}\n\n{content[idx:].lstrip()}"
            releases_html_path.write_text(updated, encoding="utf-8")
            return

    raise ValueError(
        f"Could not find <tbody> insertion marker in {releases_html_path}"
    )
