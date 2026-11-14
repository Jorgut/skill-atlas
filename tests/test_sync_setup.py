from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sync_setup  # noqa: E402


def git(directory: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(directory), *args], check=True, stdout=subprocess.PIPE)


class SyncSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "Tests")
        (self.repo / "README.md").write_text("hello\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-qm", "init")

    def options(self, **overrides):
        params = dict(
            home=str(self.home),
            project=[str(self.repo)],
            interval=15,
            idle_minutes=30,
            min_interval=60,
            confirm=False,
            no_test=True,
            format="json",
        )
        params.update(overrides)
        return argparse.Namespace(**params)

    def test_preview_writes_nothing(self):
        result = sync_setup.setup(self.options())
        self.assertEqual(result["status"], "preview")
        self.assertFalse((self.home / ".config").exists())
        self.assertFalse((self.home / "Library").exists())
        self.assertEqual(result["projects"], [str(self.repo.resolve())])

    def test_confirm_writes_registry_and_plist(self):
        with patch.object(sync_setup.sys, "platform", "darwin"), \
             patch.object(sync_setup, "_run_launchctl", side_effect=[(False, "not loaded"), (True, "")]):
            result = sync_setup.setup(self.options(confirm=True))
        self.assertEqual(result["status"], "installed")
        self.assertTrue(result["launchctl_loaded"])
        registry = json.loads((self.home / ".config/skill-atlas/watch.json").read_text())
        self.assertEqual(registry["projects"], [str(self.repo.resolve())])
        plist_path = self.home / "Library/LaunchAgents/com.skill-atlas.sync-notify.plist"
        plist = plistlib.loads(plist_path.read_bytes())
        self.assertEqual(plist["Label"], sync_setup.LABEL)
        self.assertEqual(plist["StartInterval"], 900)
        self.assertIn("--idle-minutes", plist["ProgramArguments"])
        self.assertEqual(plist["ProgramArguments"][plist["ProgramArguments"].index("--idle-minutes") + 1], "30")

    def test_existing_registry_is_merged_and_backed_up(self):
        registry_path = self.home / ".config/skill-atlas/watch.json"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(json.dumps({"projects": ["/tmp/other"], "note": "keep"}))
        with patch.object(sync_setup.sys, "platform", "darwin"), \
             patch.object(sync_setup, "_run_launchctl", side_effect=[(False, ""), (True, "")]):
            result = sync_setup.setup(self.options(confirm=True))
        merged = json.loads(registry_path.read_text())
        self.assertEqual(merged["projects"], ["/tmp/other", str(self.repo.resolve())])
        self.assertEqual(merged["note"], "keep")
        self.assertTrue(result["backups"])

    def test_rejects_non_git_or_missing_project(self):
        not_repo = Path(self.temp.name) / "not-a-repo"
        not_repo.mkdir()
        with self.assertRaises(sync_setup.SetupError):
            sync_setup.setup(self.options(project=[str(not_repo)]))

    def test_invalid_existing_registry_is_refused(self):
        registry_path = self.home / ".config/skill-atlas/watch.json"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text("{broken")
        with self.assertRaises(sync_setup.SetupError):
            sync_setup.setup(self.options())

    def test_cli_wiring(self):
        import skill_atlas
        args = skill_atlas.parse_args([
            "sync", "setup", "--project", str(self.repo), "--confirm", "--no-test",
            "--home", str(self.home), "--format", "json",
        ])
        with patch.object(sync_setup.sys, "platform", "darwin"), \
             patch.object(sync_setup, "_run_launchctl", side_effect=[(False, ""), (True, "")]):
            out = __import__("io").StringIO()
            with __import__("contextlib").redirect_stdout(out):
                args.handler(args)
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "installed")


if __name__ == "__main__":
    unittest.main()
