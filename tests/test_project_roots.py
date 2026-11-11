from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import project_roots  # noqa: E402
import skill_atlas  # noqa: E402

IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
SKIPPED_AS_ROOT = "PermissionError behaviour cannot be simulated as root"


def snapshot(root: Path) -> dict[str, tuple[int, int, int]]:
    items: dict[str, tuple[int, int, int]] = {}
    for path in sorted(root.rglob("*")):
        stat = path.lstat()
        items[path.relative_to(root).as_posix()] = (stat.st_mode, stat.st_size, stat.st_mtime_ns)
    return items


class ProjectRootAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    # ---------------------------------------------------------------- helpers

    def write(self, path: Path, content: str = "x") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def make_git_repo(
        self,
        directory: Path,
        remote: str | None = None,
        head: str | None = "refs/heads/main",
        bare: bool = False,
    ) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        git_dir = directory / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)
        lines = ["[core]", "    repositoryformatversion = 0", f"    bare = {str(bare).lower()}"]
        if remote is not None:
            lines += [
                '[remote "origin"]',
                f"    url = {remote}",
                "    fetch = +refs/heads/*:refs/remotes/origin/*",
            ]
        self.write(git_dir / "config", "\n".join(lines) + "\n")
        if head is not None:
            self.write(git_dir / "HEAD", f"ref: {head}\n")
        return directory

    def make_project(
        self,
        directory: Path,
        *,
        remote: str | None = None,
        head: str | None = "refs/heads/main",
        docs: dict[str, str] | None = None,
        git: bool = True,
    ) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        if git:
            self.make_git_repo(directory, remote=remote, head=head)
        for name, content in (docs or {}).items():
            self.write(directory / name, content)
        return directory

    def touched(self, path: Path, seconds: int) -> Path:
        os.utime(path, ns=(seconds * 1_000_000_000, seconds * 1_000_000_000))
        return path

    # 1. Explicit project: .git/config origin remote and .git/HEAD branch ref.
    def test_explicit_project_parses_git_config_origin_and_head(self) -> None:
        project = self.make_project(
            self.root / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# rules\n"},
        )
        result = project_roots.audit([project], [], 2)
        self.assertEqual(result["summary"]["projects"], 1)
        record = result["projects"][0]
        self.assertEqual(record["path"], project.resolve().as_posix())
        self.assertEqual(record["name"], "project")
        self.assertEqual(record["discovered_by"], "explicit")
        self.assertEqual(record["evidence"], ["explicit", "git:.git", "marker:AGENTS.md"])
        self.assertTrue(record["git"]["is_repo"])
        self.assertEqual(record["git"]["remote_name"], "origin")
        self.assertEqual(record["git"]["remote_url"], "https://github.com/acme/widgets.git")
        self.assertEqual(record["git"]["head_ref"], "refs/heads/main")
        self.assertFalse(record["git"]["worktree_or_bare"])
        # Markers and docs are metadata records; doc bytes are hashed, not read.
        self.assertEqual(
            [marker["name"] for marker in record["markers"]],
            list(project_roots.DISCOVERY_MARKERS),
        )
        agents = next(doc for doc in record["docs"] if doc["name"] == "AGENTS.md")
        self.assertEqual(agents["size"], len("# rules\n"))
        self.assertIsNotNone(agents["sha256"])
        self.assertEqual(len(agents["sha256"]), 64)
        self.assertFalse(agents["too_large"])
        self.assertIsInstance(agents["mtime"], float)
        claude = next(doc for doc in record["docs"] if doc["name"] == "CLAUDE.md")
        self.assertIsNone(claude["size"])
        self.assertIsNone(claude["sha256"])

    # 2. Two paths with the same remote form a confirmed duplicate group.
    def test_same_remote_creates_confirmed_duplicate_group(self) -> None:
        first = self.make_project(
            self.root / "alpha" / "copy-a",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# a\n"},
        )
        second = self.make_project(
            self.root / "beta" / "copy-b",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# b\n"},
        )
        result = project_roots.audit([first, second], [], 2)
        self.assertEqual(len(result["duplicate_groups"]), 1)
        group = result["duplicate_groups"][0]
        self.assertEqual(group["identity"], "git-remote:github.com/acme/widgets")
        self.assertEqual(group["evidence"], "git-remote")
        self.assertEqual(
            group["paths"],
            sorted([first.resolve().as_posix(), second.resolve().as_posix()]),
        )
        self.assertEqual(result["summary"]["duplicate_groups"], 1)
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["recommendations"][0]["evidence"], "git-remote")

    # 3. Same basename with different docs: probable group plus divergence.
    def test_same_basename_different_docs_is_probable_and_divergent(self) -> None:
        first = self.make_project(
            self.root / "one" / "project",
            git=False,
            docs={"AGENTS.md": "# first copy\n", "CLAUDE.md": "# shared rules\n"},
        )
        second = self.make_project(
            self.root / "two" / "project",
            git=False,
            docs={"AGENTS.md": "# second copy\n", "CLAUDE.md": "# shared rules\n"},
        )
        result = project_roots.audit([first, second], [], 2)
        self.assertEqual(len(result["duplicate_groups"]), 1)
        group = result["duplicate_groups"][0]
        self.assertEqual(group["identity"], "name:project")
        self.assertEqual(group["evidence"], "directory-name")
        self.assertEqual(len(group["divergent_docs"]), 1)
        divergent = group["divergent_docs"][0]
        self.assertEqual(divergent["name"], "AGENTS.md")
        self.assertEqual(divergent["distinct_hashes"], 2)
        self.assertEqual(len(divergent["variants"]), 2)
        hashes = {variant["sha256"] for variant in divergent["variants"]}
        self.assertEqual(len(hashes), 2)
        for variant in divergent["variants"]:
            self.assertEqual(len(variant["sha256"]), 12)
            self.assertIsInstance(variant["size"], int)
            self.assertIsInstance(variant["mtime"], float)
        self.assertEqual(result["summary"]["divergent_docs"], 1)
        self.assertEqual(
            [item["name"] for item in group["shared_identical_docs"]], ["CLAUDE.md"]
        )

    # 4. Identical docs across grouped copies are not divergence.
    def test_identical_docs_are_not_divergent(self) -> None:
        first = self.make_project(
            self.root / "one" / "same",
            remote="https://github.com/acme/shared.git",
            docs={"AGENTS.md": "# same\n", "CONTEXT.md": "# context\n"},
        )
        second = self.make_project(
            self.root / "two" / "same",
            remote="https://github.com/acme/shared.git",
            docs={"AGENTS.md": "# same\n", "CONTEXT.md": "# context\n"},
        )
        result = project_roots.audit([first, second], [], 2)
        group = result["duplicate_groups"][0]
        self.assertEqual(group["divergent_docs"], [])
        self.assertEqual(
            [item["name"] for item in group["shared_identical_docs"]],
            ["AGENTS.md", "CONTEXT.md"],
        )
        for shared in group["shared_identical_docs"]:
            self.assertEqual(len(shared["paths"]), 2)
            self.assertEqual(len(shared["sha256"]), 12)
        self.assertEqual(result["summary"]["divergent_docs"], 0)

    # 5. Deterministic canonical recommendation that requires confirmation.
    def test_canonical_recommendation_is_deterministic_and_confirm_required(self) -> None:
        older = self.make_project(
            self.root / "one" / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# a\n", "CONTEXT.md": "# old state\n"},
        )
        newer = self.make_project(
            self.root / "two" / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# b\n", "CONTEXT.md": "# new state\n"},
        )
        self.touched(older / "CONTEXT.md", 1_500_000_000)
        self.touched(newer / "CONTEXT.md", 1_600_000_000)
        before = snapshot(self.root)
        first = project_roots.audit([older, newer], [], 2)
        after = snapshot(self.root)
        self.assertEqual(before, after, "the audit must not write anything")
        recommendation = first["recommendations"][0]
        self.assertEqual(recommendation["canonical_candidate"], newer.resolve().as_posix())
        self.assertIs(recommendation["requires_user_confirmation"], True)
        self.assertTrue(recommendation["suggested_actions"][0].startswith("keep "))
        self.assertTrue(
            any("archive" in action for action in recommendation["suggested_actions"])
        )
        self.assertTrue(
            any("review divergent" in action for action in recommendation["suggested_actions"])
        )
        self.assertTrue(
            any(
                "do not move" in action
                for action in recommendation["suggested_actions"]
            )
        )
        second = project_roots.audit([older, newer], [], 2)
        first["audit"]["generated_at"] = second["audit"]["generated_at"] = "fixed"
        self.assertEqual(first, second)

        # A directory-name group ignores state freshness: most docs wins.
        plain_a = self.make_project(
            self.root / "three" / "plain",
            git=False,
            docs={"AGENTS.md": "# a\n"},
        )
        plain_b = self.make_project(
            self.root / "four" / "plain",
            git=False,
            docs={"AGENTS.md": "# b\n", "CLAUDE.md": "# more docs\n"},
        )
        plain = project_roots.audit([plain_a, plain_b], [], 2)
        plain_recommendation = plain["recommendations"][0]
        self.assertEqual(plain_recommendation["evidence"], "directory-name")
        self.assertEqual(
            plain_recommendation["canonical_candidate"], plain_b.resolve().as_posix()
        )

    # 6. Nested project roots are reported as an outer/inner pair.
    def test_nested_project_pair_is_detected(self) -> None:
        outer = self.make_project(
            self.root / "nested" / "outer",
            remote="https://github.com/acme/outer.git",
            docs={"AGENTS.md": "# outer\n"},
        )
        inner = self.make_project(
            outer / "inner",
            remote="https://github.com/acme/inner.git",
            docs={"AGENTS.md": "# inner\n"},
        )
        result = project_roots.audit([outer, inner], [], 2)
        self.assertEqual(
            result["nested_pairs"],
            [
                {
                    "outer": outer.resolve().as_posix(),
                    "inner": inner.resolve().as_posix(),
                }
            ],
        )
        self.assertEqual(result["summary"]["nested_pairs"], 1)
        # Order of input paths must not change the reported pair.
        reordered = project_roots.audit([inner, outer], [], 2)
        self.assertEqual(reordered["nested_pairs"], result["nested_pairs"])

    # 7. Discovery respects the depth bound below each root.
    def test_discovery_depth_limit_is_respected(self) -> None:
        scan_root = self.root / "scan"
        scan_root.mkdir()
        depth_one = self.make_project(
            scan_root / "p1",
            git=False,
            docs={"AGENTS.md": "# 1\n", "CLAUDE.md": "# 1\n"},
        )
        depth_two = self.make_project(
            scan_root / "level2" / "p2",
            git=False,
            docs={"AGENTS.md": "# 2\n", "CLAUDE.md": "# 2\n"},
        )
        depth_three = self.make_project(
            scan_root / "level3" / "mid" / "p3",
            git=False,
            docs={"AGENTS.md": "# 3\n", "CLAUDE.md": "# 3\n"},
        )
        two = project_roots.audit([], [scan_root], 2)
        found = {project["name"] for project in two["projects"]}
        self.assertIn(depth_one.name, found)
        self.assertIn(depth_two.name, found)
        self.assertNotIn(depth_three.name, found)
        self.assertEqual(two["summary"]["roots_scanned"], 1)
        self.assertEqual(two["summary"]["projects"], 2)

        one = project_roots.audit([], [scan_root], 1)
        self.assertEqual({project["name"] for project in one["projects"]}, {depth_one.name})

        three = project_roots.audit([], [scan_root], 3)
        self.assertEqual(
            {project["name"] for project in three["projects"]},
            {depth_one.name, depth_two.name, depth_three.name},
        )
        discovered = next(
            project for project in three["projects"] if project["name"] == depth_two.name
        )
        self.assertEqual(discovered["discovered_by"], "marker")
        self.assertIn("marker:AGENTS.md", discovered["evidence"])
        # An explicitly listed path also found by discovery is reported once,
        # and explicit evidence wins.
        both = project_roots.audit([depth_one], [scan_root], 2)
        self.assertEqual(both["summary"]["projects"], 2)
        explicit = next(
            project for project in both["projects"] if project["name"] == depth_one.name
        )
        self.assertEqual(explicit["discovered_by"], "explicit")
        self.assertEqual(explicit["evidence"][0], "explicit")

    # 8. Hidden directories, node_modules, .git internals, and symlinks are skipped.
    def test_hidden_node_modules_git_internals_and_symlink_cycles_are_skipped(self) -> None:
        scan_root = self.root / "scan"
        scan_root.mkdir()
        hidden = self.make_project(
            scan_root / ".hidden-project",
            docs={"AGENTS.md": "# hidden\n", "CLAUDE.md": "# hidden\n"},
        )
        vendored = self.make_project(
            scan_root / "node_modules" / "pkg",
            docs={"AGENTS.md": "# vendored\n", "CLAUDE.md": "# vendored\n"},
        )
        real = self.make_project(
            scan_root / "real-project",
            remote="https://github.com/acme/real.git",
            docs={"AGENTS.md": "# real\n", "CLAUDE.md": "# real\n"},
        )
        # A project-looking directory inside .git internals must never count.
        self.write(real / ".git" / "fake" / "AGENTS.md", "# fake\n")
        self.write(real / ".git" / "fake" / "CLAUDE.md", "# fake\n")
        (scan_root / "loop").symlink_to(scan_root, target_is_directory=True)
        (scan_root / "cycle-a").symlink_to(scan_root / "cycle-b", target_is_directory=True)
        (scan_root / "cycle-b").symlink_to(scan_root / "cycle-a", target_is_directory=True)

        result = project_roots.audit([], [scan_root], 5)
        paths = [project["path"] for project in result["projects"]]
        self.assertEqual(paths, [real.resolve().as_posix()])
        for path in paths:
            self.assertNotIn(hidden.resolve().as_posix(), path)
            self.assertNotIn(vendored.resolve().as_posix(), path)
            self.assertNotIn("/.git/", path)
            self.assertNotIn("/loop", path)
        self.assertEqual(result["projects"][0]["discovered_by"], "git")
        self.assertIn("git:.git", result["projects"][0]["evidence"])
        # A symlink loop passed directly as a root is a warning, not a crash.
        looped = project_roots.audit([], [scan_root / "cycle-a"], 2)
        self.assertEqual(looped["projects"], [])
        self.assertTrue(looped["audit"]["warnings"])
        # A symlinked root that resolves normally is audited once.
        via_loop = project_roots.audit([], [scan_root / "loop"], 2)
        self.assertEqual(
            [item["path"] for item in via_loop["projects"]],
            [real.resolve().as_posix()],
        )

    # 9. Unreadable directories and files are reported without crashing.
    @unittest.skipIf(IS_ROOT, SKIPPED_AS_ROOT)
    def test_unreadable_directory_and_file_do_not_crash(self) -> None:
        scan_root = self.root / "scan"
        scan_root.mkdir()
        blocked = scan_root / "blocked"
        self.write(blocked / "AGENTS.md", "# blocked\n")
        self.write(blocked / "CLAUDE.md", "# blocked\n")
        blocked.chmod(0)
        self.addCleanup(blocked.chmod, 0o755)
        project = self.make_project(
            scan_root / "ok-project",
            git=False,
            docs={"AGENTS.md": "# rules\n", "CLAUDE.md": "# rules\n"},
        )
        unreadable_doc = project / "AGENTS.md"
        unreadable_doc.chmod(0)
        self.addCleanup(unreadable_doc.chmod, 0o644)

        result = project_roots.audit([], [scan_root], 2)
        paths = [item["path"] for item in result["projects"]]
        self.assertEqual(paths, [project.resolve().as_posix()])
        warnings = result["audit"]["warnings"]
        self.assertTrue(any("unreadable directory" in warning for warning in warnings), warnings)
        self.assertTrue(any("blocked" in warning for warning in warnings), warnings)
        record = result["projects"][0]
        agents = next(doc for doc in record["docs"] if doc["name"] == "AGENTS.md")
        self.assertIsNone(agents["sha256"])
        self.assertFalse(agents["too_large"])
        claude = next(doc for doc in record["docs"] if doc["name"] == "CLAUDE.md")
        self.assertIsNotNone(claude["sha256"])
        # An unreadable root is also tolerated.
        unreadable_root = project_roots.audit([], [blocked], 2)
        self.assertEqual(unreadable_root["projects"], [])

    # 10. The audit performs no writes in its discovery scope.
    def test_audit_performs_no_writes(self) -> None:
        scan_root = self.root / "scan"
        project = self.make_project(
            scan_root / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# a\n", "CONTEXT.md": "# state\n"},
        )
        self.make_project(
            scan_root / "project-copy",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# b\n"},
        )
        before = snapshot(self.root)
        result = project_roots.audit([], [scan_root], 3)
        after = snapshot(self.root)
        self.assertEqual(before, after)
        self.assertEqual(result["summary"]["projects"], 2)
        out = StringIO()
        with redirect_stdout(out):
            project_roots.emit_markdown(result)
            print(json.dumps(result))
        self.assertEqual(snapshot(self.root), before)
        self.assertIn(project.resolve().as_posix(), out.getvalue())

    # 11. No git process and no network connection are used.
    def test_audit_uses_no_subprocess_or_network(self) -> None:
        project = self.make_project(
            self.root / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# SENTINEL-DOC-CONTENT\n"},
        )
        guard = AssertionError("the audit must not spawn a process or open a socket")
        guards = [
            patch.object(subprocess, "run", side_effect=guard),
            patch.object(subprocess, "Popen", side_effect=guard),
            patch.object(subprocess, "check_output", side_effect=guard),
            patch.object(os, "system", side_effect=guard),
            patch.object(socket, "socket", side_effect=guard),
            patch.object(socket, "create_connection", side_effect=guard),
        ]
        with ExitStack() as stack:
            for item in guards:
                stack.enter_context(item)
            result = project_roots.audit([project], [], 2)
            markdown_out = StringIO()
            with redirect_stdout(markdown_out):
                project_roots.emit_markdown(result)
        payload = json.dumps(result)
        self.assertNotIn("SENTINEL-DOC-CONTENT", payload)
        self.assertNotIn("SENTINEL-DOC-CONTENT", markdown_out.getvalue())
        self.assertNotIn("subprocess", vars(project_roots))
        self.assertNotIn("socket", vars(project_roots))

    # 12. JSON contract keys, markdown rendering, and limitations.
    def test_result_contract_and_markdown_rendering(self) -> None:
        first = self.make_project(
            self.root / "one" / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# first\n", "CLAUDE.md": "# shared\n"},
        )
        second = self.make_project(
            self.root / "two" / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# second\n", "CLAUDE.md": "# shared\n"},
        )
        result = project_roots.audit([first, second], [], 2)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(
            set(result),
            {
                "schema_version",
                "audit",
                "projects",
                "duplicate_groups",
                "nested_pairs",
                "recommendations",
                "summary",
                "limitations",
            },
        )
        self.assertEqual(
            set(result["audit"]),
            {"roots", "explicit_projects", "depth", "generated_at", "warnings"},
        )
        self.assertEqual(
            set(result["summary"]),
            {
                "projects",
                "duplicate_groups",
                "divergent_docs",
                "nested_pairs",
                "roots_scanned",
            },
        )
        for project in result["projects"]:
            self.assertEqual(
                set(project),
                {
                    "path",
                    "name",
                    "git",
                    "markers",
                    "docs",
                    "discovered_by",
                    "evidence",
                },
            )
            self.assertEqual(
                set(project["git"]),
                {"is_repo", "remote_url", "remote_name", "head_ref", "worktree_or_bare"},
            )
            for marker in project["markers"]:
                self.assertEqual(
                    set(marker), {"name", "path", "exists", "size", "mtime"}
                )
            for doc in project["docs"]:
                self.assertEqual(
                    set(doc),
                    {"name", "path", "size", "mtime", "sha256", "too_large"},
                )
        for group in result["duplicate_groups"]:
            self.assertEqual(
                set(group),
                {
                    "identity",
                    "evidence",
                    "paths",
                    "divergent_docs",
                    "shared_identical_docs",
                },
            )
            for divergent in group["divergent_docs"]:
                self.assertEqual(
                    set(divergent), {"name", "distinct_hashes", "variants"}
                )
                for variant in divergent["variants"]:
                    self.assertEqual(
                        set(variant), {"path", "size", "mtime", "sha256"}
                    )
            for shared in group["shared_identical_docs"]:
                self.assertEqual(set(shared), {"name", "sha256", "paths"})
        for recommendation in result["recommendations"]:
            self.assertEqual(
                set(recommendation),
                {
                    "identity",
                    "evidence",
                    "canonical_candidate",
                    "suggested_actions",
                    "requires_user_confirmation",
                },
            )
            self.assertIs(recommendation["requires_user_confirmation"], True)
        self.assertEqual(
            json.loads(json.dumps(result)), result
        )
        limitations = " ".join(result["limitations"]).lower()
        for phrase in (
            "identity is a heuristic",
            "git was not executed",
            "hashes prove",
            "recommendations are plans only",
            "depth-bounded",
        ):
            self.assertIn(phrase, limitations)
        self.assertEqual(result["limitations"], list(project_roots.LIMITATIONS))

        out = StringIO()
        with redirect_stdout(out):
            project_roots.emit_markdown(result)
        markdown = out.getvalue()
        self.assertIn("# Skill Atlas Project Root Audit", markdown)
        self.assertIn("## Summary", markdown)
        self.assertIn("## Duplicate groups", markdown)
        self.assertIn("## Recommendations", markdown)
        self.assertIn("## Limitations", markdown)
        self.assertIn("requires user confirmation: true", markdown)
        self.assertIn(result["recommendations"][0]["canonical_candidate"], markdown)
        self.assertIn("AGENTS.md", markdown)
        self.assertIn("divergent docs", markdown)

    # 13. CLI wiring: `projects audit` parses and renders a full result.
    def test_cli_wiring_returns_full_result(self) -> None:
        project = self.make_project(
            self.root / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# rules\n"},
        )
        args = skill_atlas.parse_args(
            ["projects", "audit", "--project", str(project), "--format", "json"]
        )
        self.assertEqual(args.command, "projects")
        self.assertEqual(args.action, "audit")
        self.assertEqual(args.project, [str(project)])
        self.assertEqual(args.format, "json")
        self.assertTrue(callable(args.handler))
        out = StringIO()
        with redirect_stdout(out):
            args.handler(args)
        result = json.loads(out.getvalue())
        self.assertEqual(
            result["audit"]["explicit_projects"], [project.resolve().as_posix()]
        )
        self.assertEqual(result["summary"]["projects"], 1)
        self.assertEqual(result["projects"][0]["git"]["head_ref"], "refs/heads/main")
        self.assertTrue(result["limitations"])

        markdown_args = skill_atlas.parse_args(
            ["projects", "audit", "--project", str(project)]
        )
        self.assertEqual(markdown_args.format, "markdown")
        out = StringIO()
        with redirect_stdout(out):
            markdown_args.handler(markdown_args)
        self.assertIn("# Skill Atlas Project Root Audit", out.getvalue())
        self.assertIn("## Limitations", out.getvalue())

        scan_root = self.root / "scan"
        scan_root.mkdir()
        scan_args = skill_atlas.parse_args(
            [
                "projects",
                "audit",
                "--root",
                str(scan_root),
                "--depth",
                "3",
                "--format",
                "json",
            ]
        )
        self.assertEqual(scan_args.root, [str(scan_root)])
        self.assertEqual(scan_args.depth, 3)

    # 14. Empty inputs produce an empty, well-formed result.
    def test_empty_roots_and_projects(self) -> None:
        result = project_roots.audit([], [], 2)
        self.assertEqual(result["projects"], [])
        self.assertEqual(result["duplicate_groups"], [])
        self.assertEqual(result["nested_pairs"], [])
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(
            result["summary"],
            {
                "projects": 0,
                "duplicate_groups": 0,
                "divergent_docs": 0,
                "nested_pairs": 0,
                "roots_scanned": 0,
            },
        )
        self.assertEqual(result["audit"]["roots"], [])
        self.assertEqual(result["audit"]["explicit_projects"], [])
        self.assertTrue(result["limitations"])
        out = StringIO()
        with redirect_stdout(out):
            project_roots.emit_markdown(result)
        self.assertIn("## Recommendations", out.getvalue())
        # A missing root is reported as a warning, not raised.
        missing = project_roots.audit([], [self.root / "missing-root"], 2)
        self.assertEqual(missing["projects"], [])
        self.assertTrue(
            any("root is not a directory" in warning for warning in missing["audit"]["warnings"])
        )

    # Extra: remote URL spellings normalize to one identity; different remotes
    # are never merged even when the directory name matches.
    def test_remote_url_normalization_variants(self) -> None:
        expected = "github.com/acme/widgets"
        for url in (
            "https://github.com/acme/widgets.git",
            "git@github.com:acme/widgets.git",
            "ssh://git@github.com/acme/widgets.git",
            "https://github.com/acme/widgets/",
            "https://user:token@github.com/acme/widgets.git",
        ):
            self.assertEqual(project_roots.normalize_remote_url(url), expected, url)
        self.assertEqual(
            project_roots.normalize_remote_url("/srv/git/widgets.git"), "/srv/git/widgets"
        )
        self.assertEqual(project_roots.normalize_remote_url(""), "")

        https_copy = self.make_project(
            self.root / "a" / "copy",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": "# a\n"},
        )
        scp_copy = self.make_project(
            self.root / "b" / "copy",
            remote="git@github.com:acme/widgets.git",
            docs={"AGENTS.md": "# a\n"},
        )
        result = project_roots.audit([https_copy, scp_copy], [], 2)
        self.assertEqual(len(result["duplicate_groups"]), 1)
        self.assertEqual(result["duplicate_groups"][0]["identity"], f"git-remote:{expected}")

        other_remote = self.make_project(
            self.root / "c" / "copy",
            remote="https://github.com/acme/other.git",
            docs={"AGENTS.md": "# a\n"},
        )
        mixed = project_roots.audit([https_copy, other_remote], [], 2)
        self.assertEqual(mixed["duplicate_groups"], [])

    def test_remote_identity_folds_path_case(self) -> None:
        upper = self.make_project(
            self.root / "a" / "copy",
            remote="git@github.com:Jorgut/Demo.git",
            docs={"AGENTS.md": "# a\n"},
        )
        lower = self.make_project(
            self.root / "b" / "copy",
            remote="https://github.com/jorgut/demo",
            docs={"AGENTS.md": "# a\n"},
        )
        result = project_roots.audit([upper, lower], [], 2)
        self.assertEqual(len(result["duplicate_groups"]), 1)
        group = result["duplicate_groups"][0]
        self.assertEqual(group["evidence"], "git-remote")
        self.assertEqual(group["identity"], "git-remote:github.com/jorgut/demo")
        self.assertEqual(group["divergent_docs"], [])

    # Extra: a linked worktree (.git file + commondir) is parsed without git.
    def test_linked_worktree_git_file_is_parsed(self) -> None:
        main = self.make_git_repo(self.root / "main")
        self.write(
            main / ".git" / "config",
            "\n".join(
                [
                    "[core]",
                    "    bare = false",
                    '[remote "upstream"]',
                    "    url = https://github.com/acme/upstream.git",
                    '[remote "origin"]',
                    "    url = https://github.com/acme/widgets.git",
                    "",
                ]
            ),
        )
        worktree_gitdir = main / ".git" / "worktrees" / "wt"
        worktree_gitdir.mkdir(parents=True)
        self.write(worktree_gitdir / "HEAD", "ref: refs/heads/wt-branch\n")
        self.write(worktree_gitdir / "commondir", "../..\n")
        worktree = self.root / "wt"
        worktree.mkdir()
        self.write(worktree / ".git", "gitdir: ../main/.git/worktrees/wt\n")

        result = project_roots.audit([worktree], [], 2)
        git = result["projects"][0]["git"]
        self.assertTrue(git["is_repo"])
        self.assertTrue(git["worktree_or_bare"])
        self.assertEqual(git["head_ref"], "refs/heads/wt-branch")
        # origin wins over the first listed remote.
        self.assertEqual(git["remote_name"], "origin")
        self.assertEqual(git["remote_url"], "https://github.com/acme/widgets.git")

    # Extra: documents above the hash limit are recorded but never compared.
    def test_oversized_docs_are_not_hashed_or_compared(self) -> None:
        big = "x" * (project_roots.MAX_HASH_BYTES + 1)
        other_big = "y" * (project_roots.MAX_HASH_BYTES + 1)
        first = self.make_project(
            self.root / "one" / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": big, "CLAUDE.md": "# shared\n"},
        )
        second = self.make_project(
            self.root / "two" / "project",
            remote="https://github.com/acme/widgets.git",
            docs={"AGENTS.md": other_big, "CLAUDE.md": "# shared\n"},
        )
        result = project_roots.audit([first, second], [], 2)
        for project in result["projects"]:
            agents = next(doc for doc in project["docs"] if doc["name"] == "AGENTS.md")
            self.assertIsNone(agents["sha256"])
            self.assertTrue(agents["too_large"])
            self.assertEqual(agents["size"], project_roots.MAX_HASH_BYTES + 1)
        group = result["duplicate_groups"][0]
        self.assertEqual(group["divergent_docs"], [])
        self.assertEqual(
            [item["name"] for item in group["shared_identical_docs"]], ["CLAUDE.md"]
        )
        self.assertEqual(result["summary"]["divergent_docs"], 0)

    # Extra: a detached HEAD has no branch ref.
    def test_detached_head_has_no_branch_ref(self) -> None:
        project = self.make_project(self.root / "project", git=False)
        self.make_git_repo(project, remote="https://github.com/acme/widgets.git", head=None)
        self.write(project / ".git" / "HEAD", "0123456789abcdef0123456789abcdef01234567\n")
        result = project_roots.audit([project], [], 2)
        self.assertTrue(result["projects"][0]["git"]["is_repo"])
        self.assertIsNone(result["projects"][0]["git"]["head_ref"])

    # Extra: git config comments, quoted values and a non-origin-only remote.
    def test_git_config_comments_and_fallback_remote(self) -> None:
        project = self.root / "project"
        project.mkdir()
        self.write(
            project / ".git" / "config",
            "\n".join(
                [
                    "# leading comment",
                    "; another comment",
                    "[core]",
                    "    bare = false",
                    '[remote "origin"] # primary remote',
                    '    url = "https://github.com/acme/widgets.git" # quoted',
                    "",
                ]
            ),
        )
        self.write(project / ".git" / "HEAD", "ref: refs/heads/main\n")
        result = project_roots.audit([project], [], 2)
        git = result["projects"][0]["git"]
        self.assertEqual(git["remote_name"], "origin")
        self.assertEqual(git["remote_url"], "https://github.com/acme/widgets.git")
        self.assertEqual(git["head_ref"], "refs/heads/main")
        self.assertEqual(
            project_roots.normalize_remote_url(git["remote_url"]),
            "github.com/acme/widgets",
        )

        fallback = self.root / "fallback"
        fallback.mkdir()
        self.write(
            fallback / ".git" / "config",
            '\n[remote "upstream"]\n    url = git@example.com:team/repo.git\n',
        )
        fallback_result = project_roots.audit([fallback], [], 2)
        fallback_git = fallback_result["projects"][0]["git"]
        self.assertEqual(fallback_git["remote_name"], "upstream")
        self.assertEqual(fallback_git["remote_url"], "git@example.com:team/repo.git")
        self.assertIsNone(fallback_git["head_ref"])


if __name__ == "__main__":
    unittest.main()
