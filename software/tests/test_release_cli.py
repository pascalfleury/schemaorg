from __future__ import annotations

import contextlib
from datetime import date
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from typing import Any

from rich.console import Console

from schemaorg.executor import SequentialExecutor, default_worker_count
from schemaorg.progress import NullProgressReporter
import scripts.release as release_cli

_MINI_TTL = """
@prefix : <https://schema.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
:Thing a rdfs:Class ; rdfs:label "Thing" ; rdfs:comment "Generic item." .
:DataType a rdfs:Class ; rdfs:label "DataType" ; rdfs:subClassOf rdfs:Class .
:Text a :DataType, rdfs:Class ; rdfs:label "Text" .
:name a rdf:Property ; rdfs:label "name" ; :domainIncludes :Thing ; :rangeIncludes :Text .
"""

_MINI_EXAMPLE = """TYPES: #eg-1 Thing
PRE-MARKUP:
A thing.
JSON:
{
  "@context": "https://schema.org/",
  "@type": "Thing",
  "name": "Widget"
}
"""

_DOCS_TEMPLATES = (
    "Home.j2",
    "PendingHome.j2",
    "AtticHome.j2",
    "AutoHome.j2",
    "BibHome.j2",
    "Health-lifesciHome.j2",
    "MetaHome.j2",
    "Schemas.j2",
    "Full.j2",
    "FullRelease.j2",
    "Collabs.j2",
    "Collab.j2",
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


def _make_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=120), buf


def _create_mini_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Tester")
    _git(
        repo,
        "remote",
        "add",
        "origin",
        "https://github.com/schemaorg/schemaorg.git",
    )

    (repo / "versions.json").write_text(
        json.dumps({
            "schemaversion": "30.1",
            "releaseLog": {"30.1": "2026-09-16"},
        }),
        encoding="utf-8",
    )
    (repo / "software").mkdir(parents=True)
    (repo / "software/pyproject.toml").write_text(
        '[project]\nname = "schemaorg"\nversion = "30.1"\n',
        encoding="utf-8",
    )
    (repo / "data/releases/30.1").mkdir(parents=True)
    (repo / "data/releases/30.1/schemaorg-all-https.ttl").write_text(
        _MINI_TTL, encoding="utf-8"
    )
    (repo / "data/schema.ttl").write_text(_MINI_TTL, encoding="utf-8")
    (repo / "data/examples.txt").write_text(_MINI_EXAMPLE, encoding="utf-8")

    (repo / "docs").mkdir(parents=True)
    (repo / "docs/releases.html").write_text(
        "<html><body><table><tbody>\n"
        "<!-- note: please keep this file well-formed -->\n\n"
        "<tr><td>30.1</td></tr>\n"
        "</tbody></table></body></html>\n",
        encoding="utf-8",
    )

    (repo / "software/gcloud").mkdir(parents=True)
    (repo / "software/gcloud/handlers-template.yaml").write_text(
        "ver: {{ver}}\n", encoding="utf-8"
    )
    (repo / "software/gcloud/schemaorg.yaml").write_text(
        "service: default\n", encoding="utf-8"
    )
    (repo / "software/gcloud/stagingschemaorg.yaml").write_text(
        "service: default\n", encoding="utf-8"
    )

    tpl = repo / "templates"
    (tpl / "static-doc-inserts").mkdir(parents=True)
    (tpl / "terms").mkdir(parents=True)
    (tpl / "terms/TermPage.j2").write_text("<h1>{{ term.id }}</h1>", encoding="utf-8")
    (tpl / "docs").mkdir(parents=True)
    for name in _DOCS_TEMPLATES:
        (tpl / "docs" / name).write_text("<html>ok</html>", encoding="utf-8")

    tests_dir = repo / "software/tests"
    tests_dir.mkdir(parents=True)
    mod_name = f"test_rel_ok_{abs(hash(repo))}"
    (tests_dir / f"{mod_name}.py").write_text(
        "import unittest\n"
        "class OkTest(unittest.TestCase):\n"
        "    def test_ok(self):\n        self.assertTrue(True)\n",
        encoding="utf-8",
    )

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Release 30.1")

    # Add one schema commit and one infra commit after baseline.
    (repo / "data/schema.ttl").write_text(
        _MINI_TTL
        + ':Widget a rdfs:Class ; rdfs:label "Widget" ; rdfs:subClassOf :Thing .\n',
        encoding="utf-8",
    )
    _git(repo, "add", "data/schema.ttl")
    _git(repo, "commit", "-m", "Add Widget class (#5001)")

    (repo / "software/note.txt").write_text("infra tweak\n", encoding="utf-8")
    _git(repo, "add", "software/note.txt")
    _git(repo, "commit", "-m", "Improve build script (#5002)")


class TestReleaseCli(unittest.TestCase):
    def test_parse_args_defaults_and_rejects_output_dir(self) -> None:
        defaults = release_cli.parse_args([])
        self.assertFalse(defaults.dry_run)
        self.assertEqual(defaults.date, date.today().isoformat())
        self.assertEqual(defaults.jobs, default_worker_count())

        args = release_cli.parse_args(["--dry-run", "--date", "2026-11-20", "-j", "2"])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.date, "2026-11-20")
        self.assertEqual(args.jobs, 2)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                release_cli.parse_args(["-o", "/tmp/nope"])

    def test_update_pyproject_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            pyproject.write_text(
                '[build-system]\nrequires = ["setuptools"]\n\n'
                '[project]\nname = "schemaorg"\nversion = "30.1"\n'
                'dependencies = ["rdflib>=7.0"]\n',
                encoding="utf-8",
            )
            release_cli.update_pyproject_version(pyproject, "30.2")
            self.assertIn(
                'version = "30.2"\n', pyproject.read_text(encoding="utf-8")
            )

    def test_dry_run_prints_plan_without_modifying_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _create_mini_git_repo(repo)
            console, buf = _make_console()

            # Inputs: [1] Minor (30.2), print brief? n, proceed? y
            seq = SequentialExecutor()
            rc = release_cli.run_release(
                repo_root=repo,
                dry_run=True,
                release_date="2026-11-20",
                progress=NullProgressReporter(),
                cpu_executor=seq,
                io_executor=seq,
                console=console,
                input_stream=io.StringIO("1\nn\ny\n"),
                editor_fn=lambda t: t,
                brief_dir=Path(tmp),
            )
            self.assertEqual(rc, 0)
            transcript = buf.getvalue()
            self.assertIn('Would run: git commit -m "Release 30.2"', transcript)
            self.assertIn("Would run: git push origin HEAD v30.2-release", transcript)
            self.assertIn("as version 30-2", transcript)
            self.assertFalse((repo / "data/releases/30.2").exists())
            self.assertIn(
                '"30.1"', (repo / "versions.json").read_text(encoding="utf-8")
            )

    def test_aborts_on_dirty_tracked_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _create_mini_git_repo(repo)
            (repo / "versions.json").write_text("dirty\n", encoding="utf-8")
            console, buf = _make_console()

            seq = SequentialExecutor()
            rc = release_cli.run_release(
                repo_root=repo,
                dry_run=True,
                release_date="2026-11-20",
                progress=NullProgressReporter(),
                cpu_executor=seq,
                io_executor=seq,
                console=console,
                input_stream=io.StringIO("1\n"),
                editor_fn=lambda t: t,
                brief_dir=Path(tmp),
            )
            self.assertEqual(rc, 1)
            self.assertIn("not clean", buf.getvalue())

    def test_declining_pre_generation_confirmation_leaves_repo_untouched(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _create_mini_git_repo(repo)
            console, buf = _make_console()

            # Inputs: [2] Major (31.0), print brief? n, proceed? n
            seq = SequentialExecutor()
            rc = release_cli.run_release(
                repo_root=repo,
                dry_run=False,
                release_date="2026-11-20",
                progress=NullProgressReporter(),
                cpu_executor=seq,
                io_executor=seq,
                console=console,
                input_stream=io.StringIO("2\nn\nn\n"),
                editor_fn=lambda t: t,
                brief_dir=Path(tmp),
            )
            self.assertEqual(rc, 0)
            transcript = buf.getvalue()
            self.assertIn("[1] Minor bump -> 30.2", transcript)
            self.assertIn("[2] Major bump -> 31.0", transcript)
            self.assertIn("30.1 -> 31.0 (major)", transcript)
            self.assertIn("Aborted before making any changes.", transcript)
            self.assertFalse((repo / "data/releases/31.0").exists())
            self.assertIn(
                '"30.1"', (repo / "versions.json").read_text(encoding="utf-8")
            )

    def test_full_release_flow_commits_tags_pushes_and_deploys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            _create_mini_git_repo(repo)
            console, buf = _make_console()

            external_cmds: list[list[str]] = []

            def hybrid_runner(
                cmd: list[str], **kwargs: Any
            ) -> subprocess.CompletedProcess[str]:
                if cmd[0] == "gcloud" or (cmd[:2] == ["git", "push"]):
                    external_cmds.append(cmd)
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                kwargs.setdefault("capture_output", True)
                kwargs.setdefault("text", True)
                return subprocess.run(cmd, **kwargs)

            # Inputs: [1] Minor (30.2), print brief? n, proceed build? y,
            # commit/tag/push? y, gcloud target [3] prod only, migrate? y
            seq = SequentialExecutor()
            rc = release_cli.run_release(
                repo_root=repo,
                dry_run=False,
                release_date="2026-11-20",
                progress=NullProgressReporter(),
                cpu_executor=seq,
                io_executor=seq,
                console=console,
                input_stream=io.StringIO("1\nn\ny\ny\n3\ny\n"),
                editor_fn=lambda t: t,
                run_cmd=hybrid_runner,
                brief_dir=Path(tmp),
            )

            self.assertEqual(rc, 0, buf.getvalue())
            self.assertIn(
                '"schemaversion": "30.2"',
                (repo / "versions.json").read_text(encoding="utf-8"),
            )
            self.assertIn(
                'version = "30.2"',
                (repo / "software/pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertIn(
                '<span id="v30.2"></span>',
                (repo / "docs/releases.html").read_text(encoding="utf-8"),
            )
            self.assertTrue(
                (repo / "data/releases/30.2/schemaorg-all-https.ttl").is_file()
            )
            self.assertTrue(
                (repo / "software/site/terms/types/W/Widget.html").is_file()
            )
            self.assertFalse((repo / "software/site/releases").exists())
            self.assertFalse((repo / "software/site/schemaorg.yaml").exists())

            head_msg = subprocess.run(
                ["git", "log", "-1", "--format=%s"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            self.assertEqual(head_msg, "Release 30.2")
            tags = subprocess.run(
                ["git", "tag", "-l"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                check=True,
            ).stdout.splitlines()
            self.assertIn("v30.2-release", tags)

            self.assertEqual(
                external_cmds[0],
                ["git", "push", "origin", "HEAD", "v30.2-release"],
            )
            self.assertTrue(
                any(
                    "deploy" in c and "--version=30-2" in c
                    for c in external_cmds
                )
            )
            self.assertTrue(
                any(
                    "set-traffic" in c and "--splits=30-2=1" in c
                    for c in external_cmds
                )
            )


if __name__ == "__main__":
    unittest.main()
