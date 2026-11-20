#!/usr/bin/env python3
"""Guided interactive wizard for cutting and deploying a Schema.org release."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date, datetime
import logging
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import textwrap
from typing import TextIO

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from schemaorg import constants
from schemaorg.executor import (
    ProcessTaskExecutor,
    SequentialExecutor,
    TaskExecutor,
    ThreadTaskExecutor,
    default_worker_count,
)
from schemaorg.layout import (
    Domain,
    InputLayout,
    OutputLayout,
    Releases,
    checkDataDirectories,
)
from schemaorg.progress import (
    ProgressReporter,
    RichProgressReporter,
    configure_rich_logging,
)
from schemaorg.release.changelog import (
    ReleaseChanges,
    canonical_repo_url,
    collect_changes,
    find_baseline,
    insert_release_row,
    prepare_changelog_data,
    render_changelog_brief,
    render_default_row,
)
from schemaorg.release.deploy import (
    AppEngineTarget,
    TARGETS,
    appengine_version_id,
    deploy,
    is_gcloud_available,
)
from schemaorg.release.git_repo import CmdRunner, GitRepo
from schemaorg.site_bundle import SiteBundle
from schemaorg.tasks.compare_vocabulary import (
    CompareVocabularyTask,
    VocabularyDiffReport,
)
from schemaorg.tasks.export_release_files import ExportReleaseFilesTask
from schemaorg.tasks.export_site_metadata import ExportSiteMetadataTask
from schemaorg.tasks.prepare_site_static import PrepareSiteStaticTask
from schemaorg.tasks.render_docs_pages import RenderDocsPagesTask
from schemaorg.tasks.render_term_pages import RenderTermPagesTask
from schemaorg.tasks.run_unit_tests import RunUnitTestsTask
from schemaorg.tasks.validate_examples import (
    ShaclConfigError,
    ValidateExamplesTask,
)
from schemaorg.version import Version, VersionItem
from SchemaExamples.schemaexamples import SchemaExamples

EditorFn = Callable[[str], str]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="release",
        description=(
            f"Guided wizard to cut a {constants.SITENAME} release: selects minor/major "
            "bump, computes date and two-group LLM changelog brief, builds and "
            "validates canonical release artifacts, commits/tags/pushes after "
            "confirmation, and uploads to GCloud."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery, prompts, and summary without modifying files, git, or GCloud.",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        metavar="YYYY-MM-DD",
        help="Release date in YYYY-MM-DD format (default: %(default)s).",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=default_worker_count(),
        metavar="N",
        help="Parallel worker count for release/site builds (default: %(default)s).",
    )
    ns = parser.parse_args(argv)
    try:
        datetime.strptime(ns.date, "%Y-%m-%d")
    except ValueError:
        parser.error("--date must be in YYYY-MM-DD format")
    if ns.jobs < 1:
        parser.error("--jobs must be >= 1")
    return ns


def update_pyproject_version(pyproject_path: Path, new_version: str) -> None:
    """Update the [project] version field in software/pyproject.toml in place."""
    lines = pyproject_path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_project = False
    updated = False
    out: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
        elif in_project and not updated and re.match(r'^version\s*=\s*"[^"]*"', stripped):
            out.append(f'version = "{new_version}"\n')
            updated = True
            continue
        out.append(line)

    if not updated:
        raise ValueError(
            f"Could not find [project] version field in {pyproject_path}"
        )
    pyproject_path.write_text("".join(out), encoding="utf-8")


def _prompt_version_choice(
    current: VersionItem,
    console: Console,
    input_stream: TextIO | None,
) -> tuple[str, str]:
    minor_ver = current.next_minor()
    major_ver = current.next_major()
    date_label = f" ({current.date()})" if current.date() else ""
    console.print(
        Panel(
            textwrap.dedent(
                f"""\
                Current published release: [bold]{current.number()}[/bold]{date_label}

                  [bold cyan][1][/bold cyan] Minor bump -> [bold green]{minor_ver}[/bold green]
                  [bold cyan][2][/bold cyan] Major bump -> [bold green]{major_ver}[/bold green]"""
            ),
            title="Select Next Release Version",
            border_style="cyan",
        )
    )
    choice = Prompt.ask(
        "Choice",
        choices=["1", "2"],
        console=console,
        stream=input_stream,
    )
    return (minor_ver, "minor") if choice == "1" else (major_ver, "major")


def _edit_text_in_editor(initial_text: str) -> str:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        return initial_text
    with tempfile.NamedTemporaryFile(
        mode="w+",
        suffix=".html",
        prefix="sdo-release-row-",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(initial_text)
        tmp_path = Path(tmp.name)
    try:
        subprocess.run([*shlex.split(editor), str(tmp_path)], check=True)
        return tmp_path.read_text(encoding="utf-8")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _make_executors(jobs: int) -> tuple[TaskExecutor, TaskExecutor]:
    if jobs <= 1:
        seq = SequentialExecutor()
        return seq, seq
    return ProcessTaskExecutor(jobs), ThreadTaskExecutor(min(8, jobs))


def _render_release_summary(
    console: Console,
    current: VersionItem,
    new_version: str,
    bump_kind: str,
    release_date: str,
    changes: ReleaseChanges,
    vocab_diff: VocabularyDiffReport | None,
    tag_name: str,
    ae_version: str,
    curated_row: str,
) -> None:
    vocab_line = (
        f"+{len(vocab_diff.added)} added, -{len(vocab_diff.dropped)} dropped, "
        f"{vocab_diff.changed_count} changed"
        if vocab_diff is not None
        else "skipped"
    )
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column()
    table.add_row(
        "Version",
        f"{current.number()} -> [bold green]{new_version}[/bold green] ({bump_kind})",
    )
    table.add_row("Release date", release_date)
    table.add_row(
        "Baseline commit",
        (
            f"{changes.baseline_sha} "
            f"({len(changes.schema_commits)} schema/data, "
            f"{len(changes.infra_commits)} infra/software)"
        ),
    )
    table.add_row("Vocab delta", vocab_line)
    table.add_row("Git tag", tag_name)
    table.add_row("App Engine ID", ae_version)
    table.add_row(
        "Will update",
        textwrap.dedent(
            f"""\
            - versions.json
            - software/pyproject.toml (version = "{new_version}")
            - docs/releases.html"""
        ),
    )
    table.add_row(
        "Will generate & verify",
        textwrap.dedent(
            f"""\
            - data/releases/{new_version}/
            - Run unit tests + SHACL validation against {new_version}
            - software/site/ (full site targeting {new_version})"""
        ),
    )
    console.print()
    console.print(Panel(table, title="Release Summary", border_style="cyan"))
    console.print(
        Panel(
            Syntax(curated_row.rstrip(), "html", word_wrap=True),
            title="Changelog Preview",
            border_style="blue",
        )
    )


def _prompt_gcloud_targets(
    console: Console, input_stream: TextIO | None
) -> list[AppEngineTarget]:
    console.print()
    console.print(
        Panel(
            textwrap.dedent(
                f"""\
                  [bold cyan][1][/bold cyan] Staging then Prod (with QA pause)
                  [bold cyan][2][/bold cyan] Staging only ({TARGETS["staging"].url})
                  [bold cyan][3][/bold cyan] Prod only ({TARGETS["prod"].url})
                  [bold cyan][4][/bold cyan] Skip GCloud upload"""
            ),
            title="Select GCloud Deployment Target",
            border_style="cyan",
        )
    )
    choice = Prompt.ask(
        "Target",
        choices=["1", "2", "3", "4"],
        console=console,
        stream=input_stream,
    )
    if choice == "1":
        return [TARGETS["staging"], TARGETS["prod"]]
    if choice == "2":
        return [TARGETS["staging"]]
    if choice == "3":
        return [TARGETS["prod"]]
    return []


def run_release(
    repo_root: Path,
    dry_run: bool,
    release_date: str,
    progress: ProgressReporter,
    cpu_executor: TaskExecutor,
    io_executor: TaskExecutor,
    console: Console | None = None,
    input_stream: TextIO | None = None,
    editor_fn: EditorFn = _edit_text_in_editor,
    run_cmd: CmdRunner = subprocess.run,
    include_vocab_diff: bool = True,
    brief_dir: Path | None = None,
) -> int:
    """Execute the guided Schema.org release flow against canonical repo paths."""
    out = console if console is not None else Console()
    input_layout = InputLayout(repo_root)
    versions_path = input_layout.file(Domain.ROOT, constants.VERSIONS_FILE)
    pyproject_path = repo_root / "software/pyproject.toml"
    releases_html_path = input_layout.file(Domain.DOCS, "releases.html")
    site_dir = repo_root / "software/site"
    tests_dir = repo_root / "software/tests"
    repo = GitRepo(repo_root, run_cmd=run_cmd)

    dirty = repo.dirty_tracked_files()
    if dirty:
        out.print("[bold red]Aborting: tracked working tree is not clean:[/bold red]")
        for line in dirty:
            out.print(f"  {line}", markup=False)
        return 1

    version_registry = Version(versions_path)
    current = version_registry.current()

    new_version, bump_kind = _prompt_version_choice(current, out, input_stream)
    ae_version = appengine_version_id(new_version)
    tag_name = f"v{new_version}-release"

    baseline_sha = find_baseline(repo, current.number())
    repo_url = canonical_repo_url(repo)
    changes = collect_changes(repo, baseline_sha)

    vocab_diff: VocabularyDiffReport | None = None
    if include_vocab_diff:
        releases = Releases(input_layout, version_registry)
        # Prefer checked-in 'next' release graph so external URI stubs match previous release.
        current_spec = (
            "next"
            if releases.file(version_registry.next()).is_file()
            else "source"
        )
        try:
            vocab_diff = CompareVocabularyTask(
                input_layout=input_layout,
                previous_spec=current.number(),
                current_spec=current_spec,
                exclude_layers=(),
                include_layers=(),
                show_names=True,
                show_triples=False,
                progress=progress,
                executor=cpu_executor,
            ).run()
        except FileNotFoundError as exc:
            out.print(f"[yellow]Note:[/yellow] skipping vocabulary diff ({exc})")

    changelog_data = prepare_changelog_data(
        repo_url=repo_url,
        previous_version=current.number(),
        next_version=new_version,
        release_date=release_date,
        changes=changes,
        vocab_diff=vocab_diff,
    )
    brief_text = render_changelog_brief(changelog_data)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix=f"sdo-release-{new_version}-brief-",
        dir=str(brief_dir) if brief_dir is not None else None,
        delete=False,
        encoding="utf-8",
    ) as brief_file:
        brief_file.write(brief_text)
        brief_path = Path(brief_file.name)

    out.print(f"\n[bold]Wrote LLM-ready changelog brief to:[/bold] {brief_path}")
    out.print(
        f"Commits since [cyan]{changes.baseline_sha}[/cyan]: "
        f"[bold]{len(changes.schema_commits)}[/bold] schema/data, "
        f"[bold]{len(changes.infra_commits)}[/bold] infra/software"
    )
    if Confirm.ask(
        "Print changelog brief to terminal now?",
        default=False,
        console=out,
        stream=input_stream,
    ):
        # Print raw text without markup/boxes so it copy-pastes verbatim into an LLM.
        out.print()
        out.print(brief_text, markup=False, highlight=False)

    starter_row = render_default_row(changelog_data)
    out.print(
        "\nOpening starter [cyan]docs/releases.html[/cyan] <tr> entry in editor "
        "(paste LLM-summarized <tr> or edit directly)..."
    )
    curated_row = editor_fn(starter_row).strip() + "\n"

    # Pre-generation summary & confirmation gate (zero mutations before this point).
    _render_release_summary(
        console=out,
        current=current,
        new_version=new_version,
        bump_kind=bump_kind,
        release_date=release_date,
        changes=changes,
        vocab_diff=vocab_diff,
        tag_name=tag_name,
        ae_version=ae_version,
        curated_row=curated_row,
    )

    if not Confirm.ask(
        "\nProceed with updating version and generating all release artifacts?",
        default=False,
        console=out,
        stream=input_stream,
    ):
        out.print("[yellow]Aborted before making any changes.[/yellow]")
        return 0

    if dry_run:
        out.print()
        out.print(
            Panel(
                textwrap.dedent(
                    f"""\
                    Skipping writes, builds, git push, and GCloud upload.
                    Would run: git add versions.json software/pyproject.toml docs/releases.html data/releases/{new_version}/
                    Would run: git commit -m "Release {new_version}"
                    Would run: git tag -a {tag_name} -m "Release {new_version}"
                    Would run: git push origin HEAD {tag_name}
                    Would deploy software/site/ to GCloud as version {ae_version}"""
                ),
                title="Dry Run",
                border_style="yellow",
            )
        )
        return 0

    # Update canonical metadata files.
    version_registry.add_version(new_version, release_date)
    update_pyproject_version(pyproject_path, new_version)
    insert_release_row(releases_html_path, curated_row)

    target_version = version_registry.resolve(new_version)
    releases_out = OutputLayout(input_layout.dir(Domain.DATA))
    site_output = OutputLayout(site_dir)

    def _run_stages() -> tuple[int, str | None]:
        with progress.task(
            f"Releasing {constants.SITENAME} ({new_version})",
            total=4,
            unit="stages",
        ) as overall:
            overall.step("release files")
            ExportReleaseFilesTask(
                input_layout=input_layout,
                output_layout=releases_out,
                version=target_version,
                progress=progress,
                executor=cpu_executor,
            ).run()
            overall.advance(1)

            overall.step("unit tests")
            test_summary = RunUnitTestsTask(
                tests_dir=tests_dir,
                skip_basics=False,
                progress=progress,
                executor=cpu_executor,
            ).run()
            if not test_summary.ok:
                return (
                    1,
                    "[bold red]Unit tests failed; stopping before commit/deploy.[/bold red]",
                )
            overall.advance(1)

            overall.step("SHACL validation")
            examples = SchemaExamples.from_layout(input_layout)
            jsonld_examples = [
                ex for ex in examples.allExamples() if ex.hasJsonld()
            ]
            try:
                val_summary = ValidateExamplesTask(
                    releases=Releases(releases_out, version_registry),
                    version=target_version,
                    examples=jsonld_examples,
                    invalid_only=False,
                    source_output=False,
                    progress=progress,
                    executor=cpu_executor,
                ).run()
            except ShaclConfigError as exc:
                return (
                    os.EX_CONFIG,
                    f"[bold red]SHACL configuration error:[/bold red] {exc}",
                )
            if val_summary.error_count:
                return (
                    1,
                    f"[bold red]SHACL validation failed "
                    f"({val_summary.error_count} invalid examples); "
                    "stopping before commit/deploy.[/bold red]",
                )
            overall.advance(1)

            overall.step("site")
            site_prep = io_executor.run_all([
                lambda: SiteBundle.from_release(
                    input_layout=input_layout,
                    releases_layout=input_layout,
                    target_version=target_version,
                    progress=progress,
                    executor=io_executor,
                ),
                lambda: PrepareSiteStaticTask(
                    input_layout=input_layout,
                    output_layout=site_output,
                    target_version=target_version,
                    current_version=target_version,
                    clear_first=True,
                    progress=progress,
                    executor=io_executor,
                ).run(),
            ])
            bundle = site_prep[0]
            assert isinstance(bundle, SiteBundle)
            RenderTermPagesTask(
                bundle=bundle,
                output_layout=site_output,
                build_opts=(),
                term_ids=("ALL",),
                progress=progress,
                executor=cpu_executor,
            ).run()
            RenderDocsPagesTask(
                bundle=bundle,
                output_layout=site_output,
                build_opts=(),
                page_names=("ALL",),
                progress=progress,
                executor=cpu_executor,
            ).run()
            ExportSiteMetadataTask(
                input_layout=input_layout,
                output_layout=site_output,
                version=target_version,
                vocab=bundle.vocab,
                progress=progress,
                executor=cpu_executor,
            ).run()
            overall.advance(1)
        return 0, None

    stage_rc, stage_err = _run_stages()
    if stage_rc != 0:
        if stage_err:
            out.print(stage_err)
        return stage_rc

    # Git commit, tag, and push gate.
    git_files = [
        "versions.json",
        "software/pyproject.toml",
        "docs/releases.html",
        f"data/releases/{new_version}",
    ]
    out.print()
    out.print(
        Panel(
            textwrap.dedent(
                f"""\
                Files:  {", ".join(git_files)}
                Commit: Release {new_version}
                Tag:    {tag_name}"""
            ),
            title="Git Release Step",
            border_style="cyan",
        )
    )
    if Confirm.ask(
        f"Commit, tag {tag_name}, and push to origin?",
        default=False,
        console=out,
        stream=input_stream,
    ):
        push_proc = repo.commit_tag_and_push(
            files=git_files,
            message=f"Release {new_version}",
            tag_name=tag_name,
        )
        if push_proc.returncode != 0:
            out.print(
                "[bold yellow]Warning: git push failed "
                "(local commit and tag are preserved):[/bold yellow]"
            )
            if push_proc.stderr:
                out.print(push_proc.stderr.strip(), markup=False)
            return 1

    # GCloud upload gate.
    targets = _prompt_gcloud_targets(out, input_stream)
    if targets:
        if run_cmd is subprocess.run and not is_gcloud_available():
            out.print("[bold red]Error: 'gcloud' CLI not found on PATH.[/bold red]")
            return 1
        migrate = Confirm.ask(
            "Migrate live traffic immediately after upload?",
            default=True,
            console=out,
            stream=input_stream,
        )
        for idx, gcloud_target in enumerate(targets):
            if idx > 0:
                if not Confirm.ask(
                    f"Staging QA complete ({targets[idx - 1].url}/docs/qa.html)? "
                    f"Proceed to deploy {gcloud_target.url}?",
                    default=False,
                    console=out,
                    stream=input_stream,
                ):
                    out.print("[yellow]Stopped before production upload.[/yellow]")
                    break
            deploy(
                target=gcloud_target,
                site_dir=site_dir,
                releases_src_dir=input_layout.dir(Domain.RELEASE),
                version=new_version,
                migrate=migrate,
                confirm_overwrite=lambda msg: Confirm.ask(
                    msg, default=False, console=out, stream=input_stream
                ),
                run_cmd=run_cmd,
            )
            out.print(
                f"[bold green]Deployed {ae_version}[/bold green] to "
                f"{gcloud_target.project} ({gcloud_target.url})."
            )

    return 0


def main(argv: Sequence[str] | None = None) -> None:
    console = Console()
    configure_rich_logging(console, level=logging.WARNING)
    args = parse_args(argv)
    checkDataDirectories()

    cpu_executor, io_executor = _make_executors(args.jobs)
    exit_code = run_release(
        repo_root=constants.PROJECT_ROOT,
        dry_run=bool(args.dry_run),
        release_date=args.date,
        progress=RichProgressReporter(console=console),
        cpu_executor=cpu_executor,
        io_executor=io_executor,
        console=console,
    )
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
