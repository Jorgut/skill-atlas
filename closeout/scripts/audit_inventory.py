#!/usr/bin/env python3
"""Collect read-only closeout evidence and suggest project profiles."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


SKIP_DIRS = {
    ".git", ".next", ".venv", "build", "dist", "node_modules", "target", "vendor", "venv"
}
RULE_NAMES = ("AGENTS.override.md", "AGENTS.md", "CLAUDE.md", "CLAUDE.local.md")


def git_output(project: Path, *args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(project), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def files_matching(project: Path, suffixes: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for path in project.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(project).parts):
            continue
        if path.is_file() and path.suffix.lower() in suffixes:
            found.append(path.relative_to(project).as_posix())
    return sorted(found)


def detect_profiles(project: Path) -> list[dict[str, Any]]:
    indicators: dict[str, list[str]] = {
        "web-application": [],
        "api-service": [],
        "library-package": [],
        "desktop-application": [],
        "agent-skill": [],
        "documentation": [],
    }
    names = {path.name for path in project.iterdir()} if project.is_dir() else set()
    if "package.json" in names:
        indicators["web-application"].append("package.json")
        indicators["library-package"].append("package.json")
    for marker in ("openapi.json", "openapi.yaml", "Dockerfile", "migrations"):
        if marker in names:
            indicators["api-service"].append(marker)
    for marker in ("pyproject.toml", "Cargo.toml", "go.mod"):
        if marker in names:
            indicators["library-package"].append(marker)
    for marker in ("Package.swift", "project.pbxproj", "src-tauri"):
        if marker in names or any(project.rglob(marker)):
            indicators["desktop-application"].append(marker)
    if (project / "SKILL.md").is_file() or any(project.glob("*/SKILL.md")):
        indicators["agent-skill"].append("SKILL.md")
    markdown = files_matching(project, (".md", ".mdx"))
    if markdown:
        indicators["documentation"].append(f"{len(markdown)} markdown files")
    return [
        {"profile": profile, "indicators": values}
        for profile, values in indicators.items()
        if values
    ]


def collect(project: Path) -> dict[str, Any]:
    project = project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"project is not a directory: {project}")
    markdown = files_matching(project, (".md", ".mdx"))
    rules = []
    cursor = project
    while True:
        for name in RULE_NAMES:
            path = cursor / name
            if path.exists() or path.is_symlink():
                rules.append(
                    {
                        "path": str(path),
                        "symlink": path.is_symlink(),
                        "target": str(path.resolve()) if path.exists() else None,
                    }
                )
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    status = git_output(project, "status", "--porcelain=v1")
    branch = git_output(project, "branch", "--show-current")
    worktrees = git_output(project, "worktree", "list", "--porcelain")
    return {
        "project": str(project),
        "read_only": True,
        "profiles": detect_profiles(project),
        "inventory": {
            "markdown": markdown,
            "rules": rules,
            "root_entries": sorted(path.name for path in project.iterdir()),
            "git": {
                "available": status is not None,
                "branch": branch,
                "status_entries": len(status.splitlines()) if status else 0,
                "worktrees": worktrees.count("worktree ") if worktrees else 0,
            },
        },
        "fact_planes": {
            plane: {"status": "pending", "evidence": []}
            for plane in ("code", "runtime", "docs", "rules", "memory", "workspace")
        },
        "ledger_template": [
            "claim", "source_of_truth", "stale_surface", "intended_action", "verification", "final_status"
        ],
    }


def emit_markdown(result: dict[str, Any]) -> None:
    print("# closeout inventory")
    print(f"\n- project: `{result['project']}`")
    print("- mode: read-only")
    profiles = result["profiles"]
    print(f"- profiles: {', '.join(item['profile'] for item in profiles) or 'unknown'}")
    inventory = result["inventory"]
    print(f"- markdown files: {len(inventory['markdown'])}")
    print(f"- active rule candidates: {len(inventory['rules'])}")
    print(f"- git status entries: {inventory['git']['status_entries']}")
    print(f"- worktrees: {inventory['git']['worktrees']}")
    print("\n## Fact Planes")
    for plane, value in result["fact_planes"].items():
        print(f"- {plane}: {value['status']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    try:
        result = collect(Path(args.project))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        emit_markdown(result)


if __name__ == "__main__":
    main()
