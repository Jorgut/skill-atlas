from __future__ import annotations

import argparse
import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sync_helper  # noqa: E402


class SyncHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()

    def options(self, **overrides):
        params = dict(home=str(self.home), confirm=False, interval=900, no_open=True, format="json")
        params.update(overrides)
        return argparse.Namespace(**params)

    def fake_build(self, output: Path) -> Path:
        app = output / sync_helper.APP_NAME
        macos = app / "Contents" / "MacOS"
        macos.mkdir(parents=True)
        (macos / "SkillAtlasNotify").write_text("fake")
        return app

    def test_preview_writes_nothing(self):
        result = sync_helper.install(self.options())
        self.assertEqual(result["status"], "preview")
        self.assertFalse((self.home / "Applications").exists())
        self.assertFalse((self.home / "Library").exists())

    def test_confirm_installs_app_config_and_plist(self):
        with patch.object(sync_helper.sys, "platform", "darwin"), \
             patch.object(sync_helper, "build_app", side_effect=self.fake_build), \
             patch.object(sync_helper, "_launchctl", side_effect=[(False, ""), (True, "")]):
            result = sync_helper.install(self.options(confirm=True))
        self.assertEqual(result["status"], "installed")
        p = sync_helper.paths(self.home)
        self.assertTrue(p["app"].is_dir())
        config = json.loads(p["config"].read_text())
        self.assertEqual(config["interval"], 900)
        self.assertEqual(config["dirty_min_files"], 20)
        self.assertNotIn("cli", config)
        self.assertNotIn("state", config)
        self.assertNotIn("log", config)
        plist = plistlib.loads(p["plist"].read_bytes())
        self.assertEqual(plist["Label"], sync_helper.LABEL)
        self.assertTrue(plist["RunAtLoad"])

    def test_uninstall_removes_files(self):
        with patch.object(sync_helper.sys, "platform", "darwin"), \
             patch.object(sync_helper, "build_app", side_effect=self.fake_build), \
             patch.object(sync_helper, "_launchctl", side_effect=[(False, ""), (True, "")]):
            sync_helper.install(self.options(confirm=True))
        with patch.object(sync_helper, "_launchctl", return_value=(True, "")), \
             patch.object(sync_helper.subprocess, "run"):
            result = sync_helper.uninstall(self.options(confirm=True))
        self.assertEqual(result["status"], "removed")
        p = sync_helper.paths(self.home)
        self.assertFalse(p["app"].exists())
        self.assertFalse(p["plist"].exists())

    def test_status(self):
        result = sync_helper.status(self.options())
        self.assertEqual(result["status"], "not-installed")


if __name__ == "__main__":
    unittest.main()
