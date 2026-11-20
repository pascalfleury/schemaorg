"""Floating Git repository wrapper and commit-history helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
import subprocess

CmdRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class GitCommit:
    """Raw metadata and changed file paths for one git commit."""

    sha: str
    subject: str
    body: str
    files: tuple[str, ...]


def normalize_github_url(remote_url: str) -> str:
    """Normalize SSH/HTTPS GitHub remote URLs into a browsable HTTPS URL."""
    url = remote_url.strip()
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.removeprefix("git@github.com:")
    elif url.startswith("ssh://git@github.com/"):
        url = "https://github.com/" + url.removeprefix("ssh://git@github.com/")
    return url.removesuffix(".git").rstrip("/")


class GitRepo:
    """Floating interface to a local Git checkout."""

    def __init__(
        self,
        root: Path,
        run_cmd: CmdRunner = subprocess.run,
    ) -> None:
        self.root: Path = Path(root)
        self._run_cmd: CmdRunner = run_cmd

    def run(
        self, args: Sequence[str], check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return self._run_cmd(
            ["git", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=check,
        )

    def remote_url(
        self, remotes: Sequence[str] = ("upstream", "origin")
    ) -> tuple[str, str] | None:
        """Return (remote_name, normalized_url) for the first configured remote."""
        for remote in remotes:
            proc = self.run(["remote", "get-url", remote], check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                return remote, normalize_github_url(proc.stdout)
        return None

    def resolve_tag(self, tag_name: str) -> str | None:
        """Return full commit SHA for a local tag, or None if missing."""
        proc = self.run(
            ["rev-parse", "--verify", "--quiet", f"refs/tags/{tag_name}"],
            check=False,
        )
        return (
            proc.stdout.strip()
            if proc.returncode == 0 and proc.stdout.strip()
            else None
        )

    def last_commit_for(self, rel_path: str) -> str | None:
        """Return full SHA of the latest commit touching rel_path, or None."""
        proc = self.run(
            ["log", "-n", "1", "--format=%H", "--", rel_path],
            check=False,
        )
        return (
            proc.stdout.strip()
            if proc.returncode == 0 and proc.stdout.strip()
            else None
        )

    def short_rev(self, rev: str = "HEAD") -> str:
        """Return abbreviated commit SHA for rev."""
        return self.run(["rev-parse", "--short", rev]).stdout.strip()

    def dirty_tracked_files(self) -> list[str]:
        """Return git status porcelain lines for modified tracked files."""
        proc = self.run(["status", "--porcelain", "--untracked-files=no"])
        return [line for line in proc.stdout.splitlines() if line.strip()]

    def commits_since(self, baseline_sha: str) -> tuple[GitCommit, ...]:
        """Return non-merge commits in <baseline_sha>..HEAD with touched paths."""
        log_out = self.run([
            "log",
            "--no-merges",
            "--format=%x1e%h%x1f%s%x1f%b%x1f",
            "--name-only",
            f"{baseline_sha}..HEAD",
        ]).stdout

        commits: list[GitCommit] = []
        for record in log_out.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            fields = record.split("\x1f", maxsplit=3)
            if len(fields) < 4:
                continue
            sha, subject, body, files_blob = fields
            files = tuple(
                line.strip()
                for line in files_blob.splitlines()
                if line.strip()
            )
            commits.append(
                GitCommit(
                    sha=sha.strip(),
                    subject=subject.strip(),
                    body=body.strip(),
                    files=files,
                )
            )
        return tuple(commits)

    def commit_tag_and_push(
        self,
        files: Sequence[str],
        message: str,
        tag_name: str,
    ) -> subprocess.CompletedProcess[str]:
        """Stage files, create commit and annotated tag, then push HEAD and tag."""
        self.run(["add", *files])
        self.run(["commit", "-m", message])
        self.run(["tag", "-a", tag_name, "-m", message])
        return self.run(["push", "origin", "HEAD", tag_name], check=False)
