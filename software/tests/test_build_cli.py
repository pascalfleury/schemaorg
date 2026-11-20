from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from schemaorg.executor import SequentialExecutor, default_worker_count
from schemaorg.layout import Domain, InputLayout
from schemaorg.progress import NullProgressReporter
import scripts.build as build_cli

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


def _create_mini_repo(root: Path, test_passes: bool = True) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "versions.json").write_text(
        json.dumps({
            "schemaversion": "30.1",
            "releaseLog": {"30.1": "2026-09-16"},
        }),
        encoding="utf-8",
    )
    data_dir = root / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "schema.ttl").write_text(_MINI_TTL, encoding="utf-8")
    (data_dir / "examples.txt").write_text(_MINI_EXAMPLE, encoding="utf-8")

    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "about.html").write_text("<html>about</html>", encoding="utf-8")

    gcloud_dir = root / "software/gcloud"
    gcloud_dir.mkdir(parents=True)
    (gcloud_dir / "handlers-template.yaml").write_text(
        "ver: {{ver}}\n", encoding="utf-8"
    )

    templates_dir = root / "templates"
    (templates_dir / "static-doc-inserts").mkdir(parents=True)
    (templates_dir / "terms").mkdir(parents=True)
    (templates_dir / "terms/TermPage.j2").write_text(
        "<h1>{{ term.id }}</h1>", encoding="utf-8"
    )
    docs_tpl = templates_dir / "docs"
    docs_tpl.mkdir(parents=True)
    for tpl_name in _DOCS_TEMPLATES:
        (docs_tpl / tpl_name).write_text("<html>{{ title|default('') }}</html>", encoding="utf-8")

    tests_dir = root / "software/tests"
    tests_dir.mkdir(parents=True)
    body = "self.assertTrue(True)" if test_passes else "self.fail('boom')"
    mod_name = f"test_mini_{'pass' if test_passes else 'fail'}_{abs(hash(root))}"
    (tests_dir / f"{mod_name}.py").write_text(
        "import unittest\n"
        "class MiniTest(unittest.TestCase):\n"
        f"    def test_one(self):\n        {body}\n",
        encoding="utf-8",
    )
    return root / "software/site", tests_dir


class TestBuildCliParsing(unittest.TestCase):
    def test_defaults_enable_all_four_stages(self) -> None:
        opts = build_cli.parse_args([])
        self.assertTrue(opts.schema)
        self.assertTrue(opts.site)
        self.assertTrue(opts.tests)
        self.assertTrue(opts.validate)
        self.assertIsNone(opts.output_dir)
        self.assertEqual(opts.version, "next")
        self.assertTrue(opts.clean)
        self.assertEqual(opts.terms, ())
        self.assertEqual(opts.pages, ())
        self.assertEqual(opts.jobs, default_worker_count())

    def test_boolean_toggles_and_custom_flags(self) -> None:
        opts = build_cli.parse_args([
            "--no-schema",
            "--no-site",
            "--no-tests",
            "--no-validate",
            "-o",
            "/tmp/custom-sdo",
            "--version",
            "30.1",
            "--no-clean",
            "--terms",
            "Person",
            "Event",
            "--pages",
            "Home",
            "-j",
            "2",
        ])
        self.assertFalse(opts.schema)
        self.assertFalse(opts.site)
        self.assertFalse(opts.tests)
        self.assertFalse(opts.validate)
        self.assertEqual(opts.output_dir, Path("/tmp/custom-sdo"))
        self.assertEqual(opts.version, "30.1")
        self.assertFalse(opts.clean)
        self.assertEqual(opts.terms, ("Person", "Event"))
        self.assertEqual(opts.pages, ("Home",))
        self.assertEqual(opts.jobs, 2)


class TestBuildCliExecution(unittest.TestCase):
    def test_custom_output_dir_redirects_schema_and_site_without_self_wipe(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            out_dir = Path(tmp) / "custom_out"
            default_site, tests_dir = _create_mini_repo(root)

            out_dir.mkdir()
            (out_dir / ".gitkeep").write_text("", encoding="utf-8")
            stale = out_dir / "stale.txt"
            stale.write_text("old", encoding="utf-8")

            opts = build_cli.parse_args(["-o", str(out_dir), "-j", "1"])
            seq = SequentialExecutor()
            rc = build_cli.run_build(
                options=opts,
                input_layout=InputLayout(root),
                default_site_dir=default_site,
                tests_dir=tests_dir,
                progress=NullProgressReporter(),
                cpu_executor=seq,
                io_executor=seq,
            )

            self.assertEqual(rc, 0)
            self.assertFalse(stale.exists())
            self.assertTrue((out_dir / ".gitkeep").is_file())
            # Schema artifacts landed in custom_out/releases/next/ and survived Stage 4.
            self.assertTrue(
                (out_dir / "releases/next/schemaorg-all-https.ttl").is_file()
            )
            self.assertTrue(
                (out_dir / "releases/next/schemaorgcontext.jsonld").is_file()
            )
            # Site artifacts landed in custom_out/ using fresh context/OWL.
            self.assertTrue((out_dir / "docs/home.html").is_file())
            self.assertTrue((out_dir / "docs/jsonldcontext.jsonld").is_file())
            self.assertTrue((out_dir / "terms/types/T/Thing.html").is_file())
            # Source repo data/releases and software/site stayed untouched.
            self.assertFalse((root / "data/releases").exists())
            self.assertFalse(default_site.exists())

    def test_default_layout_writes_data_releases_and_software_site(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            default_site, tests_dir = _create_mini_repo(root)

            opts = build_cli.parse_args(["--no-tests", "-j", "1"])
            seq = SequentialExecutor()
            rc = build_cli.run_build(
                options=opts,
                input_layout=InputLayout(root),
                default_site_dir=default_site,
                tests_dir=tests_dir,
                progress=NullProgressReporter(),
                cpu_executor=seq,
                io_executor=seq,
            )

            self.assertEqual(rc, 0)
            self.assertTrue(
                (root / "data/releases/next/schemaorg-all-https.ttl").is_file()
            )
            self.assertTrue((default_site / "docs/home.html").is_file())
            self.assertTrue(
                (default_site / "terms/types/T/Thing.html").is_file()
            )

    def test_partial_terms_preserves_existing_site_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            default_site, tests_dir = _create_mini_repo(root)
            seq = SequentialExecutor()

            # Build schema once into data/releases/next/.
            rc0 = build_cli.run_build(
                options=build_cli.parse_args(
                    ["--no-site", "--no-tests", "--no-validate", "-j", "1"]
                ),
                input_layout=InputLayout(root),
                default_site_dir=default_site,
                tests_dir=tests_dir,
                progress=NullProgressReporter(),
                cpu_executor=seq,
                io_executor=seq,
            )
            self.assertEqual(rc0, 0)

            default_site.mkdir(parents=True)
            keep_file = default_site / "existing.html"
            keep_file.write_text("keep", encoding="utf-8")

            rc = build_cli.run_build(
                options=build_cli.parse_args([
                    "--no-schema",
                    "--no-tests",
                    "--no-validate",
                    "--no-clean",
                    "--terms",
                    "Thing",
                    "-j",
                    "1",
                ]),
                input_layout=InputLayout(root),
                default_site_dir=default_site,
                tests_dir=tests_dir,
                progress=NullProgressReporter(),
                cpu_executor=seq,
                io_executor=seq,
            )
            self.assertEqual(rc, 0)
            self.assertTrue(keep_file.is_file())
            self.assertTrue(
                (default_site / "terms/types/T/Thing.html").is_file()
            )
            self.assertFalse((default_site / "docs/home.html").exists())

    def test_failing_unit_tests_stops_build_early(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            default_site, tests_dir = _create_mini_repo(root, test_passes=False)
            seq = SequentialExecutor()

            with self.assertLogs("scripts.build", level="ERROR"):
                rc = build_cli.run_build(
                    options=build_cli.parse_args(
                        ["--no-schema", "--no-validate", "-j", "1"]
                    ),
                    input_layout=InputLayout(root),
                    default_site_dir=default_site,
                    tests_dir=tests_dir,
                    progress=NullProgressReporter(),
                    cpu_executor=seq,
                    io_executor=seq,
                )
            self.assertEqual(rc, 1)
            self.assertFalse((default_site / "docs/home.html").exists())

    def test_missing_shacl_files_returns_ex_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            default_site, tests_dir = _create_mini_repo(root)
            seq = SequentialExecutor()

            with self.assertLogs("scripts.build", level="ERROR"):
                rc = build_cli.run_build(
                    options=build_cli.parse_args(
                        ["--no-schema", "--no-site", "--no-tests", "-j", "1"]
                    ),
                    input_layout=InputLayout(root),
                    default_site_dir=default_site,
                    tests_dir=tests_dir,
                    progress=NullProgressReporter(),
                    cpu_executor=seq,
                    io_executor=seq,
                )
            self.assertEqual(rc, os.EX_CONFIG)


if __name__ == "__main__":
    unittest.main()
