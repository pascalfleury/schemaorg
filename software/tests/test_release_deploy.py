from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from typing import Any

from schemaorg.release.deploy import (
    TARGETS,
    appengine_version_id,
    deploy,
)


class TestReleaseDeploy(unittest.TestCase):
    def test_appengine_version_id(self) -> None:
        self.assertEqual(appengine_version_id("30.2"), "30-2")
        self.assertEqual(appengine_version_id(" 31.0 "), "31-0")

    def test_deploy_stages_runs_and_cleans_up_even_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_dir = root / "site"
            (site_dir / "gcloud").mkdir(parents=True)
            (site_dir / "gcloud/schemaorg.yaml").write_text(
                "service: default\n", encoding="utf-8"
            )
            releases_src = root / "data/releases"
            (releases_src / "30.2").mkdir(parents=True)
            (releases_src / "30.2/schemaorg.owl").write_text(
                "<owl/>", encoding="utf-8"
            )

            calls: list[list[str]] = []

            def ok_runner(
                cmd: list[str], **kwargs: Any
            ) -> subprocess.CompletedProcess[str]:
                calls.append(cmd)
                if "deploy" in cmd:
                    self.assertTrue((site_dir / "schemaorg.yaml").is_file())
                    self.assertTrue(
                        (site_dir / "releases/30.2/schemaorg.owl").is_file()
                    )
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            deploy(
                target=TARGETS["prod"],
                site_dir=site_dir,
                releases_src_dir=releases_src,
                version="30.2",
                migrate=True,
                confirm_overwrite=lambda _msg: True,
                run_cmd=ok_runner,
            )
            self.assertEqual(len(calls), 3)
            self.assertIn("--version=30-2", calls[1])
            self.assertIn("--splits=30-2=1", calls[2])
            self.assertFalse((site_dir / "schemaorg.yaml").exists())
            self.assertFalse((site_dir / "releases").exists())

            def failing_runner(
                cmd: list[str], **kwargs: Any
            ) -> subprocess.CompletedProcess[str]:
                if "deploy" in cmd:
                    raise subprocess.CalledProcessError(1, cmd)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with self.assertRaises(subprocess.CalledProcessError):
                deploy(
                    target=TARGETS["prod"],
                    site_dir=site_dir,
                    releases_src_dir=releases_src,
                    version="30.2",
                    migrate=True,
                    confirm_overwrite=lambda _msg: True,
                    run_cmd=failing_runner,
                )
            self.assertFalse((site_dir / "schemaorg.yaml").exists())
            self.assertFalse((site_dir / "releases").exists())

    def test_deploy_aborts_on_unconfirmed_live_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site_dir = root / "site"
            (site_dir / "gcloud").mkdir(parents=True)
            (site_dir / "gcloud/schemaorg.yaml").write_text(
                "service: default\n", encoding="utf-8"
            )
            releases_src = root / "data/releases"
            releases_src.mkdir(parents=True)

            def live_conflict_runner(
                cmd: list[str], **kwargs: Any
            ) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout="https://30-2-dot-schemaorgae.appspot.com\n",
                    stderr="",
                )

            executed = deploy(
                target=TARGETS["prod"],
                site_dir=site_dir,
                releases_src_dir=releases_src,
                version="30.2",
                migrate=True,
                confirm_overwrite=lambda _msg: False,
                run_cmd=live_conflict_runner,
            )
            self.assertEqual(len(executed), 1)
            self.assertFalse((site_dir / "schemaorg.yaml").exists())
            self.assertFalse((site_dir / "releases").exists())


if __name__ == "__main__":
    unittest.main()
