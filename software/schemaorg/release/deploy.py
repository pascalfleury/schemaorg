"""Floating Google Cloud App Engine staging and deployment domain."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Any

from schemaorg.sdo_uri import SdoUri

CmdRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class AppEngineTarget:
    """App Engine deployment target metadata."""

    name: str
    project: str
    yaml_file: str
    url: str


TARGETS: dict[str, AppEngineTarget] = {
    "staging": AppEngineTarget(
        name="staging",
        project="schemaorg-staging",
        yaml_file="stagingschemaorg.yaml",
        url=str(SdoUri.for_layer("staging")),
    ),
    "prod": AppEngineTarget(
        name="prod",
        project="schemaorgae",
        yaml_file="schemaorg.yaml",
        url=str(SdoUri.for_layer()),
    ),
}


def appengine_version_id(version: str) -> str:
    """Convert a dotted release version into an App Engine version ID."""
    return version.strip().replace(".", "-").replace(" ", "")


def is_gcloud_available() -> bool:
    """Return True if the gcloud CLI is discoverable on PATH."""
    return shutil.which("gcloud") is not None


def list_live_version_urls(
    project: str, run_cmd: CmdRunner = subprocess.run
) -> tuple[list[str], list[str]]:
    """Return (command, live_urls) for versions currently serving traffic."""
    cmd = [
        "gcloud",
        "app",
        "versions",
        "list",
        "--hide-no-traffic",
        "--project",
        project,
        "--uri",
    ]
    proc = run_cmd(cmd, capture_output=True, text=True, check=True)
    return cmd, proc.stdout.splitlines()


def deploy(
    target: AppEngineTarget,
    site_dir: Path,
    releases_src_dir: Path,
    version: str,
    migrate: bool,
    confirm_overwrite: Callable[[str], bool],
    run_cmd: CmdRunner = subprocess.run,
) -> list[list[str]]:
    """Stage YAML + releases into site_dir, deploy via gcloud, and always clean up."""
    ae_version = appengine_version_id(version)
    gcloud_dir = site_dir / "gcloud"
    if not site_dir.is_dir() or not gcloud_dir.is_dir():
        raise FileNotFoundError(
            f"Built site with gcloud/ configs not found at {site_dir}"
        )
    if not releases_src_dir.is_dir():
        raise FileNotFoundError(
            f"Releases directory not found at {releases_src_dir}"
        )

    staged_yamls: list[Path] = []
    staged_releases = site_dir / "releases"
    executed: list[list[str]] = []

    def _exec(
        cmd: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        executed.append(cmd)
        kwargs: dict[str, Any] = {"check": True, "text": True}
        if cwd is not None:
            kwargs["cwd"] = str(cwd)
        return run_cmd(cmd, **kwargs)

    try:
        for yaml_file in sorted(gcloud_dir.glob("*.yaml")):
            dest = site_dir / yaml_file.name
            shutil.copy2(yaml_file, dest)
            staged_yamls.append(dest)

        if staged_releases.exists():
            shutil.rmtree(staged_releases)
        shutil.copytree(releases_src_dir, staged_releases)

        list_cmd, live_urls = list_live_version_urls(
            target.project, run_cmd=run_cmd
        )
        executed.append(list_cmd)
        live_url = f"https://{ae_version}-dot-{target.project}.appspot.com"
        if live_url in live_urls:
            if not confirm_overwrite(
                f"Version {ae_version} is already serving traffic on "
                f"{target.project}. Overwrite?"
            ):
                return executed

        _exec(
            [
                "gcloud",
                "app",
                "deploy",
                "--quiet",
                "--no-promote",
                "--project",
                target.project,
                f"--version={ae_version}",
                target.yaml_file,
            ],
            cwd=site_dir,
        )

        if migrate:
            _exec(
                [
                    "gcloud",
                    "app",
                    "services",
                    "--quiet",
                    "--project",
                    target.project,
                    "set-traffic",
                    f"--splits={ae_version}=1",
                ]
            )
    finally:
        for dest in staged_yamls:
            if dest.exists():
                dest.unlink()
        if staged_releases.exists():
            shutil.rmtree(staged_releases)

    return executed
