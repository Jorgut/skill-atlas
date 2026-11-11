from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import disk_scan  # noqa: E402
import skill_atlas  # noqa: E402

IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
SKIPPED_AS_ROOT = "PermissionError behaviour cannot be simulated as root"


def snapshot(root: Path) -> dict[str, tuple[int, int, int]]:
    items: dict[str, tuple[int, int, int]] = {}
    for path in sorted(root.rglob("*")):
        stat = path.lstat()
        items[path.relative_to(root).as_posix()] = (stat.st_mode, stat.st_size, stat.st_mtime_ns)
    return items


class DiskScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()

    def make_file(self, relative: str, size: int, base: Path | None = None) -> Path:
        path = (base or self.home) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            stream.truncate(size)
        return path

    def scan(self, **overrides):
        params = dict(
            home=self.home,
            roots=[],
            project=self.project,
            top_files=disk_scan.DEFAULT_TOP_FILES,
            min_file_mb=1.0,
            max_entries=disk_scan.DEFAULT_MAX_ENTRIES,
        )
        params.update(overrides)
        return disk_scan.scan(**params)

    def root_by_id(self, result, root_id: str):
        return next(item for item in result["roots"] if item["id"] == root_id)

    def entry(self, root, name: str):
        return next(item for item in root["entries"] if item["name"] == name)

    def test_known_agent_roots_are_classified(self) -> None:
        self.make_file(".codex/sessions/old.jsonl", 2 * 1024 * 1024)
        self.make_file(".codex/cache/blob.bin", 1024 * 1024)
        self.make_file(".codex/plugins/plugin.bin", 3 * 1024 * 1024)
        self.make_file(".codex/generated_images/image.png", 1024 * 1024)
        self.make_file(".claude/transcripts/session.jsonl", 2 * 1024 * 1024)
        result = self.scan()
        codex = self.root_by_id(result, "codex")
        kinds = {item["name"]: item["category"] for item in codex["entries"]}
        self.assertEqual(kinds["sessions"], "agent-session")
        self.assertEqual(kinds["cache"], "agent-cache")
        self.assertEqual(kinds["plugins"], "plugin-package")
        self.assertEqual(kinds["generated_images"], "agent-cache")
        claude = self.root_by_id(result, "claude-code")
        self.assertEqual(self.entry(claude, "transcripts")["category"], "agent-session")
        self.assertGreater(result["summary"]["total_bytes"], 0)
        self.assertEqual(result["summary"]["roots_scanned"], 3)

    def test_project_artifacts_and_git_objects(self) -> None:
        self.make_file("node_modules/pkg/index.js", 2 * 1024 * 1024, self.project)
        self.make_file("media/episode.wav", 3 * 1024 * 1024, self.project)
        self.make_file(".git/objects/pack/pack.pack", 4 * 1024 * 1024, self.project)
        result = self.scan()
        project = self.root_by_id(result, "project")
        kinds = {item["name"]: (item["category"], item["risk"]) for item in project["entries"]}
        self.assertEqual(kinds["node_modules"], ("build-artifact", "low"))
        self.assertEqual(kinds["media"], ("project-media", "medium"))
        self.assertEqual(kinds[".git"], ("git-object", "high"))
        self.assertGreater(result["summary"]["low_risk_bytes"], 0)
        self.assertGreater(result["summary"]["medium_risk_bytes"], 0)
        self.assertGreater(result["summary"]["high_risk_bytes"], 0)
        top_names = [Path(item["path"]).name for item in result["top_files"]]
        self.assertIn("pack.pack", top_names)
        self.assertIn("episode.wav", top_names)

    def test_top_file_limit_and_minimum_threshold(self) -> None:
        self.make_file("media/a.wav", 5 * 1024 * 1024, self.project)
        self.make_file("media/b.wav", 4 * 1024 * 1024, self.project)
        self.make_file("media/small.txt", 1024, self.project)
        result = self.scan(top_files=1, min_file_mb=1.0)
        self.assertEqual(len(result["top_files"]), 1)
        self.assertIn("a.wav", result["top_files"][0]["path"])
        result = self.scan(min_file_mb=100.0)
        self.assertEqual(result["top_files"], [])

    def test_top_files_inherit_parent_category(self) -> None:
        self.make_file(".codex/sessions/2026/01/big.jsonl", 2 * 1024 * 1024)
        self.make_file(".codex/cache/big.bin", 2 * 1024 * 1024)
        result = self.scan(min_file_mb=1.0)
        categories = {Path(item["path"]).name: item["category"] for item in result["top_files"]}
        self.assertEqual(categories["big.jsonl"], "agent-session")
        self.assertEqual(categories["big.bin"], "agent-cache")

    def test_reclaimable_candidates_carry_actions(self) -> None:
        self.make_file(".codex/cache/blob.bin", 2 * 1024 * 1024)
        self.make_file("media/episode.wav", 2 * 1024 * 1024, self.project)
        result = self.scan()
        reclaimable = {item["category"]: item for item in result["reclaimable"]}
        self.assertIn("agent-cache", reclaimable)
        self.assertIn("project-media", reclaimable)
        for item in result["reclaimable"]:
            self.assertTrue(item["suggested_action"])
            self.assertIn(item["risk"], ("low", "medium", "high"))

    def test_nested_roots_are_not_double_counted(self) -> None:
        self.make_file("node_modules/pkg/index.js", 2 * 1024 * 1024, self.project)
        result = self.scan(roots=[self.project, self.project / "node_modules"])
        paths = [item["path"] for item in result["roots"]]
        self.assertEqual(len(paths), 1)
        self.assertTrue(result["nested_roots_skipped"])

    def test_symlinks_are_not_followed(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        self.make_file("huge.bin", 5 * 1024 * 1024, outside)
        (self.project / "media").mkdir()
        (self.project / "media/link").symlink_to(outside, target_is_directory=True)
        result = self.scan()
        project = self.root_by_id(result, "project")
        self.assertGreater(project["symlinks_skipped"], 0)
        self.assertNotIn(str(outside), json.dumps(result["top_files"]))
        self.assertLess(project["size_bytes"], 4 * 1024 * 1024)

    @unittest.skipIf(IS_ROOT, SKIPPED_AS_ROOT)
    def test_unreadable_directory_is_skipped_without_crashing(self) -> None:
        locked = self.project / "locked"
        locked.mkdir()
        self.make_file("locked/file.bin", 2 * 1024 * 1024, self.project)
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        result = self.scan()
        project = self.root_by_id(result, "project")
        self.assertIsInstance(project["skipped"], int)

    def test_missing_home_and_roots_are_tolerated(self) -> None:
        result = disk_scan.scan(self.root / "missing", roots=[self.root / "missing-root"])
        self.assertEqual(result["roots"], [])
        self.assertEqual(result["summary"]["total_bytes"], 0)

    def test_scan_is_read_only(self) -> None:
        self.make_file(".codex/sessions/a.jsonl", 2 * 1024 * 1024)
        self.make_file("media/a.wav", 2 * 1024 * 1024, self.project)
        before = snapshot(self.root)
        self.scan()
        after = snapshot(self.root)
        self.assertEqual(before, after)

    def test_scan_is_deterministic_apart_from_timestamp(self) -> None:
        self.make_file("cache/blob.bin", 1024 * 1024)
        first = self.scan()
        second = self.scan()
        first["scan"].pop("generated_at")
        second["scan"].pop("generated_at")
        self.assertEqual(first, second)

    def test_result_contract_and_markdown(self) -> None:
        self.make_file("media/a.wav", 2 * 1024 * 1024, self.project)
        result = self.scan()
        for key in ("schema_version", "scan", "roots", "top_files", "reclaimable", "summary", "limitations"):
            self.assertIn(key, result)
        for key in ("roots_scanned", "total_bytes", "files", "low_risk_bytes", "medium_risk_bytes", "high_risk_bytes"):
            self.assertIn(key, result["summary"])
        buffer = StringIO()
        with redirect_stdout(buffer):
            disk_scan.emit_markdown(result)
        output = buffer.getvalue()
        self.assertIn("# Disk scan", output)
        self.assertIn("## Limitations", output)

    def test_max_entries_sets_truncation_flag(self) -> None:
        for index in range(1100):
            self.make_file(f"many/{index}.txt", 1, self.project)
        result = self.scan(max_entries=1000)
        project = self.root_by_id(result, "project")
        self.assertTrue(project["truncated"])

    def test_cli_wiring_returns_result(self) -> None:
        self.make_file("cache/blob.bin", 2 * 1024 * 1024)
        args = skill_atlas.parse_args(
            ["disk", "scan", "--home", str(self.home), "--root", str(self.project), "--format", "json"]
        )
        out = StringIO()
        with redirect_stdout(out):
            args.handler(args)
        result = json.loads(out.getvalue())
        self.assertEqual(result["schema_version"], 1)
        self.assertIn("summary", result)

    def test_manual_namespace_matches_arguments(self) -> None:
        namespace = argparse.Namespace(
            home=str(self.home),
            root=[str(self.project)],
            project=None,
            top=5,
            min_file_mb=1.0,
            max_entries=10000,
            format="json",
        )
        result = disk_scan.run(namespace)
        self.assertIn("roots", result)


if __name__ == "__main__":
    unittest.main()
