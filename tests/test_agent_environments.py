from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import agent_environments  # noqa: E402
import skill_atlas  # noqa: E402

IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
SKIPPED_AS_ROOT = "PermissionError behaviour cannot be simulated as root"


def snapshot(root: Path) -> dict[str, tuple[int, int, int]]:
    items: dict[str, tuple[int, int, int]] = {}
    for path in sorted(root.rglob("*")):
        stat = path.lstat()
        items[path.relative_to(root).as_posix()] = (stat.st_mode, stat.st_size, stat.st_mtime_ns)
    return items


class AgentEnvironmentScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.resolved_home = self.home.resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.environ = {"PATH": str(self.bin)}

    def scan(self, environ: dict[str, str | None] | None = None, project: Path | None = None):
        values = dict(self.environ)
        values.update(environ or {})
        return agent_environments.scan(self.home, values, project)

    def tool(self, result: dict, tool_id: str) -> dict:
        return next(tool for tool in result["tools"] if tool["id"] == tool_id)

    def home_path(self, relative: str) -> str:
        return (self.resolved_home / relative).as_posix()

    def write(self, relative: str, content: str = "x", base: Path | None = None) -> Path:
        path = (base or self.home) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def make_dir(self, relative: str, base: Path | None = None) -> Path:
        path = (base or self.home) / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def make_skill(self, root_relative: str, name: str = "alpha") -> None:
        skill = self.home / root_relative / name
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text("# skill\n", encoding="utf-8")

    def make_copy(self, root_relative: str, version: str | None = None) -> Path:
        directory = self.home / root_relative / "skill-atlas"
        directory.mkdir(parents=True, exist_ok=True)
        if version is not None:
            (directory / "skill.json").write_text(
                json.dumps({"schema_version": 1, "name": "skill-atlas", "version": version}),
                encoding="utf-8",
            )
        return directory

    # 1. Empty home: every tool is reported not-detected without crashing.
    def test_empty_home_reports_every_tool_not_detected(self) -> None:
        result = agent_environments.scan(self.home, {})
        self.assertEqual(len(result["tools"]), len(agent_environments.CATALOG))
        for tool in result["tools"]:
            self.assertEqual(tool["level"], "not-detected", tool["id"])
            self.assertFalse(tool["detected"], tool["id"])
            self.assertEqual(tool["evidence_paths"], [])
            self.assertEqual(tool["level"], "not-detected")
        self.assertEqual(result["summary"]["tools_detected"], 0)
        self.assertEqual(result["summary"]["tools_configured"], 0)
        self.assertEqual(result["summary"]["skill_atlas_copies"], 0)
        self.assertFalse(result["summary"]["version_mismatch"])
        self.assertEqual(result["shared_skill_roots"], [])
        self.assertTrue(result["limitations"])
        # A missing home directory is also tolerated.
        missing = agent_environments.scan(self.home / "does-not-exist", {})
        self.assertTrue(all(tool["level"] == "not-detected" for tool in missing["tools"]))

    # 2. A documented rule entry marks that tool configured; a shared skill root does not.
    def test_documented_rule_entry_marks_tool_configured(self) -> None:
        self.write(".codex/AGENTS.md", "# rules\n")
        self.make_skill(".agents/skills")
        result = self.scan()
        codex = self.tool(result, "codex")
        self.assertTrue(codex["detected"])
        self.assertEqual(codex["level"], "configured")
        entry = next(
            item
            for item in codex["instruction_entries"]
            if item["path"] == self.home_path(".codex/AGENTS.md")
        )
        self.assertTrue(entry["exists"])
        self.assertEqual(entry["evidence"], "documented")
        self.assertIn(entry["path"], codex["evidence_paths"])
        # ~/.agents/skills is documented for Kimi, but it is shared evidence:
        # it must not mark Kimi installed or configured on its own.
        kimi = self.tool(result, "kimi-code")
        self.assertEqual(kimi["level"], "not-detected")
        self.assertFalse(kimi["detected"])
        self.assertEqual(result["summary"]["tools_configured"], 1)

    # 3. A fixture PATH entry is found but never executed.
    def test_executable_found_through_fixture_path_without_execution(self) -> None:
        marker = self.root / "executed-marker"
        script = self.bin / "codex"
        script.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
        script.chmod(0o755)
        result = self.scan()
        codex = self.tool(result, "codex")
        executable = next(item for item in codex["executables"] if item["name"] == "codex")
        self.assertTrue(executable["found"])
        self.assertEqual(Path(executable["path"]).resolve(), script.resolve())
        self.assertTrue(codex["detected"])
        self.assertEqual(codex["level"], "detected")
        self.assertFalse(marker.exists(), "the scanned agent executable must not run")
        self.assertTrue(any("not executed" in note for note in codex["notes"]))

    # 4. Symlinked and broken skill roots are reported accurately.
    def test_symlinked_and_broken_skill_roots_are_reported(self) -> None:
        self.make_skill(".agents/skills")
        (self.home / ".codex").mkdir()
        (self.home / ".codex/skills").symlink_to(Path("../.agents/skills"), target_is_directory=True)
        (self.home / ".kimi-code").mkdir()
        (self.home / ".kimi-code/skills").symlink_to(Path("../../missing-target"), target_is_directory=True)
        result = self.scan()
        codex = self.tool(result, "codex")
        linked = next(
            item for item in codex["skill_roots"] if item["path"] == self.home_path(".codex/skills")
        )
        self.assertTrue(linked["exists"])
        self.assertTrue(linked["is_symlink"])
        self.assertEqual(linked["skill_count"], 1)
        kimi = self.tool(result, "kimi-code")
        broken = next(
            item for item in kimi["skill_roots"] if item["path"] == self.home_path(".kimi-code/skills")
        )
        self.assertFalse(broken["exists"])
        self.assertTrue(broken["is_symlink"])
        self.assertIsNone(broken["skill_count"])
        self.assertTrue(
            any("broken symlink" in note and ".kimi-code/skills" in note for note in kimi["notes"])
        )

    # 5. PermissionError while inspecting a directory is reported, not raised.
    @unittest.skipIf(IS_ROOT, SKIPPED_AS_ROOT)
    def test_unreadable_directory_is_reported_without_crashing(self) -> None:
        blocked = self.home / ".trae"
        blocked.mkdir()
        blocked.chmod(0)
        self.addCleanup(blocked.chmod, 0o755)
        result = self.scan()
        self.assertEqual(len(result["tools"]), len(agent_environments.CATALOG))
        trae = self.tool(result, "trae")
        root = next(item for item in trae["roots"] if item["path"] == self.home_path(".trae"))
        self.assertTrue(root["exists"])
        self.assertFalse(root["readable"])
        self.assertTrue(any("unreadable directory" in note for note in trae["notes"]))
        rule = next(item for item in trae["instruction_entries"] if item["path"] == self.home_path(".trae/rules"))
        self.assertFalse(rule["exists"])

    # 6. Project rule candidates are read from the requested project only.
    def test_project_rules_are_detected_from_a_temp_project(self) -> None:
        project = self.root / "project"
        project.mkdir()
        (project / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
        (project / "CLAUDE.md").write_text("# rules\n", encoding="utf-8")
        self.write(".kimi-code/AGENTS.md", "# rules\n", base=project)
        self.write(".cursor/rules/one.mdc", "# rule\n", base=project)
        (project / "PROJECT_STATE.md").write_text("# state\n", encoding="utf-8")
        result = self.scan(project=project)
        resolved_project = project.resolve().as_posix()

        def rule_for(tool_id: str, relative: str) -> dict:
            tool = self.tool(result, tool_id)
            return next(item for item in tool["project_rules"] if item["path"] == f"{resolved_project}/{relative}")

        self.assertTrue(rule_for("codex", "AGENTS.md")["exists"])
        self.assertTrue(rule_for("claude-code", "CLAUDE.md")["exists"])
        self.assertTrue(rule_for("kimi-code", ".kimi-code/AGENTS.md")["exists"])
        self.assertTrue(rule_for("cursor", ".cursor/rules")["exists"])
        self.assertFalse(rule_for("cline", ".clinerules")["exists"])
        # PROJECT_STATE.md is project state, not a tool rule entry.
        all_rule_paths = {
            item["path"] for tool in result["tools"] for item in tool["project_rules"]
        }
        self.assertNotIn(f"{resolved_project}/PROJECT_STATE.md", all_rule_paths)
        self.assertEqual(result["scan"]["project"], resolved_project)
        # Without a project, project rules stay empty rather than scanning the cwd.
        self.assertTrue(all(tool["project_rules"] == [] for tool in self.scan()["tools"]))

    # 7. Local Skill Atlas copy versions and mismatch detection.
    @unittest.skipIf(IS_ROOT, SKIPPED_AS_ROOT)
    def test_skill_atlas_copy_versions_and_mismatch(self) -> None:
        self.make_copy(".codex/skills", "0.6.0")
        self.make_copy(".claude/skills", "0.7.0-beta")
        result = self.scan()
        self.assertEqual(result["summary"]["skill_atlas_copies"], 2)
        self.assertEqual(
            sorted(copy["version"] for copy in result["skill_atlas_copies"]),
            ["0.6.0", "0.7.0-beta"],
        )
        self.assertTrue(result["summary"]["version_mismatch"])
        self.assertEqual(
            [copy["path"] for copy in result["skill_atlas_copies"]],
            sorted(copy["path"] for copy in result["skill_atlas_copies"]),
        )
        for copy in result["skill_atlas_copies"]:
            self.assertTrue(copy["readable"])
            self.assertFalse(copy["is_symlink"])
            self.assertIsNone(copy["target"])

        # Matching versions clear the mismatch flag.
        self.write(".codex/skills/skill-atlas/skill.json", json.dumps({"version": "0.7.0-beta"}))
        self.assertFalse(self.scan()["summary"]["version_mismatch"])

        # A missing manifest yields null version and readable false.
        opencode_copy = self.make_copy(".config/opencode/skills")
        self.assertFalse((opencode_copy / "skill.json").exists())
        result = self.scan()
        missing = next(
            copy for copy in result["skill_atlas_copies"] if copy["path"].endswith("opencode/skills/skill-atlas")
        )
        self.assertIsNone(missing["version"])
        self.assertFalse(missing["readable"])

        # An unreadable manifest yields null version and readable false.
        manifest = self.make_copy(".codex/skills", "9.9.9") / "skill.json"
        self.write(".codex/skills/skill-atlas/skill.json", json.dumps({"version": "9.9.9"}))
        manifest.chmod(0)
        self.addCleanup(manifest.chmod, 0o644)
        result = self.scan()
        unreadable = next(
            copy for copy in result["skill_atlas_copies"] if copy["path"].endswith("codex/skills/skill-atlas")
        )
        self.assertIsNone(unreadable["version"])
        self.assertFalse(unreadable["readable"])

    # 8. A shared physical skill root lists every tool that points at it.
    def test_shared_skill_root_lists_both_tools(self) -> None:
        self.make_skill(".agents/skills")
        (self.home / ".codex").mkdir()
        (self.home / ".codex/skills").symlink_to(Path("../.agents/skills"), target_is_directory=True)
        result = self.scan()
        shared_path = (self.home / ".agents/skills").resolve().as_posix()
        shared = next(item for item in result["shared_skill_roots"] if item["path"] == shared_path)
        self.assertIn("codex", shared["tools"])
        self.assertIn("kimi-code", shared["tools"])
        self.assertEqual(shared["tools"], sorted(shared["tools"]))

    # 9. The scan performs no writes anywhere in its discovery scope.
    def test_scan_performs_no_writes(self) -> None:
        self.write(".codex/AGENTS.md", "# rules\n")
        self.make_skill(".agents/skills")
        self.make_copy(".claude/skills", "0.7.0-beta")
        project = self.root / "project"
        project.mkdir()
        (project / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
        before = {
            "home": snapshot(self.home),
            "project": snapshot(project),
            "bin": snapshot(self.bin),
        }
        self.scan(project=project)
        after = {
            "home": snapshot(self.home),
            "project": snapshot(project),
            "bin": snapshot(self.bin),
        }
        self.assertEqual(before, after)

    # 10. Result shape and markdown rendering (including limitations).
    # 13. The shared root alone is reported but is not tool evidence.
    def test_shared_skill_root_alone_is_not_tool_evidence(self) -> None:
        self.make_skill(".agents/skills")
        result = self.scan()
        for tool_id in ("codex", "deepseek-harness", "kimi-code"):
            tool = self.tool(result, tool_id)
            self.assertFalse(tool["detected"], tool_id)
            self.assertEqual(tool["level"], "not-detected", tool_id)
            self.assertNotIn(self.home_path(".agents/skills"), tool["evidence_paths"])
        shared = next(
            item for item in result["shared_skill_roots"] if item["path"] == self.home_path(".agents/skills")
        )
        self.assertEqual(sorted(shared["tools"]), ["codex", "deepseek-harness", "kimi-code"])

    # 14. Copies in a non-tool root (CC Switch) are found and aliases are grouped.
    def test_copy_audit_includes_extra_root_and_groups_aliases(self) -> None:
        physical = self.make_copy(".cc-switch/skills", "0.7.0-beta")
        self.make_dir(".agents/skills")
        alias = self.home / ".agents/skills/skill-atlas"
        alias.symlink_to(physical, target_is_directory=True)
        result = self.scan()
        self.assertEqual(result["summary"]["skill_atlas_copies"], 1)
        copy = result["skill_atlas_copies"][0]
        self.assertEqual(copy["version"], "0.7.0-beta")
        self.assertTrue(copy["is_symlink"])
        self.assertEqual(Path(copy["target"]).resolve(), physical.resolve())
        self.assertIn(self.home_path(".cc-switch/skills/skill-atlas"), copy["aliases"])
        self.assertIn(self.home_path(".agents/skills/skill-atlas"), copy["aliases"])

    def test_result_shape_and_markdown_rendering(self) -> None:
        self.write(".codex/AGENTS.md", "# rules\n")
        result = self.scan()
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(
            set(result),
            {
                "schema_version",
                "scan",
                "tools",
                "shared_skill_roots",
                "skill_atlas_copies",
                "summary",
                "limitations",
            },
        )
        self.assertEqual(
            set(result["scan"]), {"home", "project", "generated_at"}
        )
        self.assertEqual(result["scan"]["home"], self.resolved_home.as_posix())
        self.assertIsNone(result["scan"]["project"])
        self.assertEqual(
            set(result["summary"]),
            {"tools_detected", "tools_configured", "skill_atlas_copies", "version_mismatch"},
        )
        for tool in result["tools"]:
            self.assertEqual(
                set(tool),
                {
                    "id",
                    "name",
                    "evidence_paths",
                    "detected",
                    "executables",
                    "roots",
                    "instruction_entries",
                    "project_rules",
                    "skill_roots",
                    "level",
                    "notes",
                },
            )
            self.assertIn(tool["level"], {"not-detected", "detected", "configured"})
            for root in tool["roots"]:
                self.assertEqual(
                    set(root), {"path", "exists", "is_symlink", "broken", "readable"}
                )
            for entry in tool["instruction_entries"]:
                self.assertEqual(set(entry), {"path", "exists", "evidence"})
                self.assertIn(entry["evidence"], {"documented", "candidate"})
            for skill in tool["skill_roots"]:
                self.assertEqual(set(skill), {"path", "exists", "is_symlink", "skill_count"})
            for executable in tool["executables"]:
                self.assertEqual(set(executable), {"name", "path", "found"})
            for rule in tool["project_rules"]:
                self.assertEqual(set(rule), {"path", "exists"})
        self.assertIsInstance(result["limitations"], list)
        joined = " ".join(result["limitations"])
        self.assertIn("Runtime loading was not verified", joined)
        self.assertIn("no agent tool was executed", joined)
        self.assertIn("unverified discovery hints", joined)
        json.loads(json.dumps(result))

        out = StringIO()
        with redirect_stdout(out):
            agent_environments.emit_markdown(result)
        markdown = out.getvalue()
        self.assertIn("# Skill Atlas Agent Environment Scan", markdown)
        self.assertIn("## Summary", markdown)
        self.assertIn("## Limitations", markdown)
        self.assertIn("Runtime loading was not verified", markdown)
        self.assertIn("codex", markdown)
        self.assertIn("configured", markdown)

    # 11. CLI wiring: `agents scan` parses and uses the requested home only.
    def test_cli_wiring_uses_requested_home(self) -> None:
        self.write(".codex/AGENTS.md", "# rules\n")
        args = skill_atlas.parse_args(
            ["agents", "scan", "--home", str(self.home), "--format", "json"]
        )
        self.assertEqual(args.command, "agents")
        self.assertEqual(args.action, "scan")
        self.assertTrue(callable(args.handler))
        out = StringIO()
        with patch.dict(os.environ, {"PATH": str(self.bin)}):
            with redirect_stdout(out):
                args.handler(args)
        result = json.loads(out.getvalue())
        self.assertEqual(result["scan"]["home"], self.resolved_home.as_posix())
        self.assertIsNone(result["scan"]["project"])
        codex = next(tool for tool in result["tools"] if tool["id"] == "codex")
        self.assertEqual(codex["level"], "configured")
        for path in codex["evidence_paths"]:
            self.assertTrue(path.startswith(self.resolved_home.as_posix() + os.sep), path)
        # Markdown is the default CLI format.
        markdown_args = skill_atlas.parse_args(["agents", "scan", "--home", str(self.home)])
        self.assertEqual(markdown_args.format, "markdown")
        out = StringIO()
        with patch.dict(os.environ, {"PATH": str(self.bin)}):
            with redirect_stdout(out):
                markdown_args.handler(markdown_args)
        self.assertIn("## Limitations", out.getvalue())

    # 12. A candidate-only tool is at most detected, never configured.
    def test_candidate_only_tools_are_never_configured(self) -> None:
        self.make_skill(".trae/skills")
        self.write(".trae/rules/rule.md", "# rule\n")
        result = self.scan()
        candidate_only = {
            spec.id
            for spec in agent_environments.CATALOG
            if all(item.evidence == "candidate" for item in spec.instruction_entries)
        }
        self.assertIn("trae", candidate_only)
        trae = self.tool(result, "trae")
        self.assertTrue(trae["detected"])
        self.assertEqual(trae["level"], "detected")
        self.assertTrue(all(item["evidence"] == "candidate" for item in trae["instruction_entries"]))
        self.assertTrue(any("unverified" in note for note in trae["notes"]))
        for tool in result["tools"]:
            if tool["id"] in candidate_only:
                self.assertNotEqual(tool["level"], "configured", tool["id"])

    # Extra: a documented home environment variable relocates only that tool.
    def test_home_env_override_relocates_kimi_specific_paths(self) -> None:
        alternative = self.root / "kimi-home"
        alternative.mkdir()
        (alternative / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
        result = self.scan(environ={"KIMI_CODE_HOME": str(alternative)})
        kimi = self.tool(result, "kimi-code")
        relocated = next(
            item
            for item in kimi["instruction_entries"]
            if item["path"] == (alternative.resolve() / "AGENTS.md").as_posix()
        )
        self.assertTrue(relocated["exists"])
        self.assertEqual(relocated["evidence"], "documented")
        self.assertEqual(kimi["level"], "configured")
        shared = next(
            item for item in kimi["skill_roots"] if item["path"] == self.home_path(".agents/skills")
        )
        self.assertFalse(shared["exists"])

    # Extra: no credential file is read and no socket is opened.
    def test_scan_reads_no_credentials_and_opens_no_socket(self) -> None:
        self.write(".codex/AGENTS.md", "# rules\n")
        self.write(".codex/auth.json", '{"token": "SENTINEL-CREDENTIAL"}')
        self.write(".dsh/.credentials.yaml", "SENTINEL-CREDENTIAL")
        self.write(".claude/.credentials.json", '{"key": "SENTINEL-CREDENTIAL"}')
        self.write(".claude/skills/skill-atlas/skill.json", json.dumps({"version": "0.7.0-beta"}))
        read_paths: list[Path] = []
        original_read_text = Path.read_text

        def recording_read_text(path: Path, *args, **kwargs) -> str:
            read_paths.append(path)
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", new=recording_read_text), patch.object(
            socket, "socket", side_effect=AssertionError("scan must not open a socket")
        ):
            result = self.scan()
        payload = json.dumps(result)
        self.assertNotIn("SENTINEL-CREDENTIAL", payload)
        self.assertTrue(read_paths)
        self.assertTrue(all(path.name == "skill.json" for path in read_paths), read_paths)

    # Extra: repeated scans are deterministic apart from the timestamp.
    def test_scan_is_deterministic(self) -> None:
        self.write(".codex/AGENTS.md", "# rules\n")
        self.make_skill(".agents/skills")
        first = self.scan()
        second = self.scan()
        first["scan"]["generated_at"] = second["scan"]["generated_at"] = "fixed"
        self.assertEqual(first, second)
        self.assertEqual(
            [tool["id"] for tool in first["tools"]],
            [spec.id for spec in agent_environments.CATALOG],
        )


if __name__ == "__main__":
    unittest.main()
