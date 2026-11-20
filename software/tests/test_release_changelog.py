from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from schemaorg.release.changelog import (
    CommitChange,
    ReleaseChanges,
    canonical_repo_url,
    classify_commit,
    collect_changes,
    find_baseline,
    insert_release_row,
    prepare_changelog_data,
    render_changelog_brief,
    render_default_row,
)
from schemaorg.release.git_repo import GitRepo
from schemaorg.tasks.compare_vocabulary import VocabularyDiffReport


class TestReleaseChangelog(unittest.TestCase):
    def test_classify_commit_ignores_generated_releases(self) -> None:
        self.assertEqual(
            classify_commit([
                "data/schema.ttl",
                "data/releases/next/schemaorg-all-https.ttl",
            ]),
            ("schema", False),
        )
        # Exporter edit refreshing data/releases/next/ must stay infra.
        self.assertEqual(
            classify_commit([
                "software/schemaorg/renderers/owl_renderer.py",
                "data/releases/next/schemaorg.owl",
            ]),
            ("infra", False),
        )
        # Mixed schema + test commit surfaces under schema with mixed flag.
        self.assertEqual(
            classify_commit([
                "data/ext/pending/issue-1.ttl",
                "software/tests/test_basics.py",
            ]),
            ("schema", True),
        )
        self.assertEqual(
            classify_commit([
                "data/collab/x.md",
                "software/a.py",
                "software/b.py",
                "software/c.py",
            ]),
            ("infra", True),
        )

    def test_baseline_repo_url_and_two_group_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = GitRepo(root)
            repo.run(["init"])
            repo.run(["config", "user.email", "test@example.com"])
            repo.run(["config", "user.name", "Tester"])
            repo.run([
                "remote",
                "add",
                "origin",
                "git@github.com:somefork/schemaorg.git",
            ])

            (root / "versions.json").write_text(
                '{"schemaversion": "30.1"}\n', encoding="utf-8"
            )
            repo.run(["add", "versions.json"])
            repo.run(["commit", "-m", "Release 30.1"])

            base = find_baseline(repo, "30.1")
            self.assertTrue(len(base) >= 7)

            (root / "data/ext/pending").mkdir(parents=True)
            (root / "data/ext/pending/issue-9.ttl").write_text(
                "# ttl\n", encoding="utf-8"
            )
            (root / "data/releases/next").mkdir(parents=True)
            (root / "data/releases/next/schemaorg-all-https.ttl").write_text(
                "# gen\n", encoding="utf-8"
            )
            repo.run(["add", "data"])
            repo.run(["commit", "-m", "Add JainDiet (#4975)"])

            (root / "software/scripts").mkdir(parents=True)
            (root / "software/scripts/build.py").write_text(
                "# tool\n", encoding="utf-8"
            )
            (root / "data/releases/next/schemaorg-all-https.ttl").write_text(
                "# gen2\n", encoding="utf-8"
            )
            repo.run(["add", "software", "data/releases/next"])
            repo.run(["commit", "-m", "Refactor exporters (#4973)"])

            self.assertEqual(
                canonical_repo_url(repo),
                "https://github.com/schemaorg/schemaorg",
            )
            changes = collect_changes(repo, base)
            self.assertEqual(len(changes.schema_commits), 1)
            self.assertEqual(changes.schema_commits[0].pr_number, "4975")
            self.assertEqual(changes.schema_commits[0].clean_subject, "Add JainDiet")
            self.assertEqual(
                changes.schema_commits[0].data_files,
                ("data/ext/pending/issue-9.ttl",),
            )
            self.assertEqual(len(changes.infra_commits), 1)
            self.assertEqual(changes.infra_commits[0].pr_number, "4973")

            repo.run(["tag", "v30.1-release", base])
            self.assertEqual(find_baseline(repo, "30.1"), base)

    def test_prepare_data_and_jinja2_templates(self) -> None:
        changes = ReleaseChanges(
            baseline_sha="aaaa111",
            head_sha="bbbb222",
            schema_commits=(
                CommitChange(
                    sha="cccc333",
                    subject="Add JainDiet & <tag> (#4975)",
                    clean_subject="Add JainDiet & <tag>",
                    body="Adds JainDiet to RestrictedDiet.",
                    first_body_line="Adds JainDiet to RestrictedDiet.",
                    pr_number="4975",
                    files=("data/schema.ttl",),
                    data_files=("data/schema.ttl",),
                ),
            ),
            infra_commits=(
                CommitChange(
                    sha="dddd444",
                    subject="Split exporters (#4973)",
                    clean_subject="Split exporters",
                    body="",
                    first_body_line="",
                    pr_number="4973",
                    files=("software/scripts/buildfiles.py",),
                    data_files=(),
                ),
            ),
        )
        diff = VocabularyDiffReport(
            current_count=3029,
            previous_count=3028,
            added=("https://schema.org/JainDiet",),
            dropped=(),
            changed_count=1,
            formatted_report="\n".join(f"line {i}" for i in range(130)),
        )
        data = prepare_changelog_data(
            repo_url="https://github.com/schemaorg/schemaorg",
            previous_version="30.1",
            next_version="30.2",
            release_date="2026-11-20",
            changes=changes,
            vocab_diff=diff,
        )
        assert data.vocab_delta is not None
        self.assertEqual(len(data.vocab_delta.report_lines), 120)
        self.assertEqual(data.vocab_delta.truncated_count, 10)
        self.assertEqual(data.infra_pr_numbers, ("4973",))

        brief = render_changelog_brief(data)
        self.assertIn("https://github.com/schemaorg/schemaorg", brief)
        self.assertIn("Group 1: Schema & Examples Changes", brief)
        self.assertIn("Group 2: Infrastructure & Tooling Changes", brief)
        self.assertIn("Vocabulary Term Diff", brief)
        self.assertIn("https://schema.org/JainDiet", brief)
        self.assertIn("10 more lines truncated", brief)
        self.assertIn("## Instructions", brief)
        # Markdown template must NOT HTML-escape raw HTML snippets.
        self.assertIn('<span id="v30.2"></span>', brief)
        self.assertIn('<a href="/TermName">TermName</a>', brief)

        row = render_default_row(data)
        self.assertTrue(row.startswith("<tr>"))
        self.assertIn("PR #4975</a>", row)
        self.assertIn("PR #4973</a>", row)
        # HTML template must autoescape untrusted commit subjects.
        self.assertIn("Add JainDiet &amp; &lt;tag&gt;", row)

    def test_insert_release_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            releases_html = Path(tmp) / "releases.html"
            releases_html.write_text(
                "<tbody>\n"
                "<!-- note: please keep this file well-formed -->\n\n"
                "<tr><td>30.1</td></tr>\n"
                "</tbody>\n",
                encoding="utf-8",
            )
            insert_release_row(releases_html, "<tr><td>30.2</td></tr>")
            updated = releases_html.read_text(encoding="utf-8")
            self.assertLess(updated.index("30.2"), updated.index("30.1"))

            with self.assertRaises(ValueError):
                insert_release_row(releases_html, "<div>not a row</div>")


if __name__ == "__main__":
    unittest.main()
