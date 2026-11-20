from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from typing import Any

from schemaorg.release.git_repo import GitRepo, normalize_github_url


class TestGitRepo(unittest.TestCase):
    def test_normalize_github_url(self) -> None:
        for raw in (
            "git@github.com:schemaorg/schemaorg.git",
            "ssh://git@github.com/schemaorg/schemaorg.git",
            "https://github.com/schemaorg/schemaorg.git",
            "https://github.com/schemaorg/schemaorg/",
        ):
            self.assertEqual(
                normalize_github_url(raw),
                "https://github.com/schemaorg/schemaorg",
            )

    def test_repo_inspection_and_commit_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = GitRepo(root)
            repo.run(["init"])
            repo.run(["config", "user.email", "test@example.com"])
            repo.run(["config", "user.name", "Tester"])
            self.assertIsNone(repo.remote_url())

            repo.run(["remote", "add", "origin", "git@github.com:fork/schemaorg.git"])
            self.assertEqual(
                repo.remote_url(),
                ("origin", "https://github.com/fork/schemaorg"),
            )
            repo.run([
                "remote",
                "add",
                "upstream",
                "https://github.com/schemaorg/schemaorg.git",
            ])
            self.assertEqual(
                repo.remote_url(),
                ("upstream", "https://github.com/schemaorg/schemaorg"),
            )

            (root / "versions.json").write_text('{"v": 1}\n', encoding="utf-8")
            repo.run(["add", "versions.json"])
            repo.run(["commit", "-m", "Release 1.0"])

            self.assertEqual(repo.dirty_tracked_files(), [])
            base = repo.last_commit_for("versions.json")
            self.assertIsNotNone(base)
            assert base is not None
            self.assertIsNone(repo.resolve_tag("v1.0-release"))
            repo.run(["tag", "v1.0-release", base])
            self.assertEqual(repo.resolve_tag("v1.0-release"), base)
            self.assertTrue(base.startswith(repo.short_rev(base)))

            (root / "a.txt").write_text("hello\n", encoding="utf-8")
            repo.run(["add", "a.txt"])
            repo.run(["commit", "-m", "Add a\n\nBody detail."])

            commits = repo.commits_since(base)
            self.assertEqual(len(commits), 1)
            self.assertEqual(commits[0].subject, "Add a")
            self.assertEqual(commits[0].body, "Body detail.")
            self.assertEqual(commits[0].files, ("a.txt",))

            # Tracked modification reported; untracked ignored.
            (root / "untracked.txt").write_text("u\n", encoding="utf-8")
            self.assertEqual(repo.dirty_tracked_files(), [])
            (root / "a.txt").write_text("changed\n", encoding="utf-8")
            self.assertEqual(len(repo.dirty_tracked_files()), 1)

    def test_commit_tag_and_push_executes_local_git_and_pushes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo = GitRepo(root)
            init_repo.run(["init"])
            init_repo.run(["config", "user.email", "test@example.com"])
            init_repo.run(["config", "user.name", "Tester"])
            (root / "f.txt").write_text("v1\n", encoding="utf-8")
            init_repo.run(["add", "f.txt"])
            init_repo.run(["commit", "-m", "init"])

            (root / "f.txt").write_text("v2\n", encoding="utf-8")
            pushed: list[list[str]] = []

            def runner(
                cmd: list[str], **kwargs: Any
            ) -> subprocess.CompletedProcess[str]:
                if cmd[:2] == ["git", "push"]:
                    pushed.append(cmd)
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                return subprocess.run(cmd, **kwargs)

            repo = GitRepo(root, run_cmd=runner)
            proc = repo.commit_tag_and_push(
                files=["f.txt"],
                message="Release 2.0",
                tag_name="v2.0-release",
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(
                pushed, [["git", "push", "origin", "HEAD", "v2.0-release"]]
            )
            self.assertIsNotNone(repo.resolve_tag("v2.0-release"))


if __name__ == "__main__":
    unittest.main()
