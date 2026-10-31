#!/usr/bin/env python3
"""Install Skill Atlas and optional platform command adapters safely."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import self_update


SKILL_NAME = "skill-atlas"
PLATFORMS = ("codex", "opencode", "claude", "kimi")


class InstallError(RuntimeError):
    """Raised when installation cannot proceed without overwriting data."""


def platform_paths(home: Path) -> dict[str, dict[str, Path | None]]:
    return {
        "codex": {
            "skill": home / ".codex/skills" / SKILL_NAME,
            "command": None,
        },
        "opencode": {
            "skill": home / ".config/opencode/skills" / SKILL_NAME,
            "command": home / ".config/opencode/commands" / f"{SKILL_NAME}.md",
        },
        "claude": {
            "skill": home / ".claude/skills" / SKILL_NAME,
            "command": home / ".claude/commands" / f"{SKILL_NAME}.md",
        },
        "kimi": {
            # Kimi Code CLI natively scans ~/.agents/skills/; avoid a duplicate link.
            "skill": None,
            "command": None,
        },
    }


def existing_status(path: Path, target: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "create"
    try:
        return "unchanged" if path.resolve() == target.resolve() else "conflict"
    except OSError:
        return "conflict"


def canonical_status(source: Path, canonical: Path) -> str:
    if not canonical.exists() and not canonical.is_symlink():
        return "copy"
    try:
        if canonical.resolve() == source.resolve():
            return "unchanged"
        self_update.load_metadata(canonical)
        return (
            "unchanged"
            if self_update.tree_sha256(canonical) == self_update.tree_sha256(source)
            else "conflict"
        )
    except (OSError, self_update.UpdateError):
        return "conflict"


def build_plan(
    source: Path,
    home: Path,
    platforms: list[str],
    commands: bool,
    with_closeout: bool = False,
) -> dict[str, Any]:
    source = source.expanduser().resolve()
    home = home.expanduser().resolve()
    self_update.load_metadata(source)
    command_source = source / "commands" / f"{SKILL_NAME}.md"
    if commands and not command_source.is_file():
        raise InstallError(f"missing command adapter: {command_source}")

    if with_closeout and not (source / "closeout/SKILL.md").is_file():
        raise InstallError("missing bundled Closeout package")
    canonical = home / ".agents/skills" / SKILL_NAME
    operations: list[dict[str, str]] = [
        {
            "kind": "canonical-skill",
            "path": str(canonical),
            "target": str(source),
            "status": canonical_status(source, canonical),
        }
    ]
    paths = platform_paths(home)
    for platform in platforms:
        if platform == "kimi":
            operations.append({
                "kind": "kimi-native-skill-discovery",
                "path": str(canonical),
                "target": str(canonical),
                "status": "native",
            })
            continue
        skill_path = paths[platform]["skill"]
        assert skill_path is not None
        operations.append(
            {
                "kind": f"{platform}-skill-link",
                "path": str(skill_path),
                "target": str(canonical),
                "status": existing_status(skill_path, canonical),
            }
        )
        command_path = paths[platform]["command"]
        if commands and command_path is not None:
            canonical_command = canonical / "commands" / f"{SKILL_NAME}.md"
            operations.append(
                {
                    "kind": f"{platform}-command-link",
                    "path": str(command_path),
                    "target": str(canonical_command),
                    "status": existing_status(command_path, canonical_command),
                }
            )

    if with_closeout:
        closeout_canonical = home / ".agents/skills/closeout"
        closeout_source = canonical / "closeout"
        operations.append({
            "kind": "closeout-canonical-link",
            "path": str(closeout_canonical),
            "target": str(closeout_source),
            "status": existing_status(closeout_canonical, closeout_source),
        })
        for platform in platforms:
            if platform == "kimi":
                # The generic Closeout link is natively scanned by Kimi too.
                continue
            platform_skill = paths[platform]["skill"]
            assert platform_skill is not None
            closeout_path = platform_skill.with_name("closeout")
            operations.append({
                "kind": f"{platform}-closeout-skill-link",
                "path": str(closeout_path),
                "target": str(closeout_canonical),
                "status": existing_status(closeout_path, closeout_canonical),
            })
            command_path = paths[platform]["command"]
            if commands and command_path is not None:
                adapter = command_path.with_name("closeout.md")
                operations.append({
                    "kind": f"{platform}-closeout-command-link",
                    "path": str(adapter),
                    "target": str(closeout_source / "commands/closeout.md"),
                    "status": existing_status(adapter, closeout_source / "commands/closeout.md"),
                })

    conflicts = [operation for operation in operations if operation["status"] == "conflict"]
    return {
        "action": "install",
        "status": "conflict" if conflicts else "ready",
        "read_only": True,
        "source": str(source),
        "canonical_path": str(canonical),
        "platforms": platforms,
        "commands_requested": commands,
        "closeout_requested": with_closeout,
        "operations": operations,
        "conflicts": conflicts,
        "codex_invocation": "$skill-atlas",
        "kimi_invocation": "/skill:skill-atlas" if "kimi" in platforms else None,
        "slash_commands": [f"/{SKILL_NAME}"]
        if commands and any(paths[platform]["command"] is not None for platform in platforms)
        else [],
    }


def copy_canonical(source: Path, canonical: Path) -> None:
    canonical.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}-install-", dir=canonical.parent))
    try:
        staged.rmdir()
        self_update.copy_candidate(source, staged)
        staged.rename(canonical)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        raise


def apply_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan["conflicts"]:
        paths = ", ".join(item["path"] for item in plan["conflicts"])
        raise InstallError(f"existing paths would be overwritten: {paths}")

    source = Path(plan["source"])
    canonical = Path(plan["canonical_path"])
    created_links: list[Path] = []
    canonical_created = False
    try:
        canonical_operation = plan["operations"][0]
        if canonical_operation["status"] == "copy":
            copy_canonical(source, canonical)
            canonical_created = True
        for operation in plan["operations"][1:]:
            if operation["status"] != "create":
                continue
            path = Path(operation["path"])
            target = Path(operation["target"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target, target_is_directory=operation["kind"].endswith("skill-link") or operation["kind"] == "closeout-canonical-link")
            created_links.append(path)
    except Exception:
        for path in reversed(created_links):
            path.unlink(missing_ok=True)
        if canonical_created and canonical.exists():
            shutil.rmtree(canonical)
        raise

    result = dict(plan)
    result["read_only"] = False
    result["status"] = "already-installed" if not canonical_created and not created_links else "installed"
    result["created"] = [str(path) for path in created_links]
    if canonical_created:
        result["created"].insert(0, str(canonical))
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    platforms = list(PLATFORMS) if args.all_platforms else list(dict.fromkeys(args.platform))
    if not platforms:
        raise InstallError("select --all-platforms or at least one --platform")
    source = Path(args.source or Path(__file__).resolve().parent.parent)
    plan = build_plan(source, Path(args.home), platforms, args.commands, getattr(args, "with_closeout", False))
    if args.apply != args.confirm:
        raise InstallError("installation requires both --apply and --confirm")
    if not args.apply:
        return plan
    return apply_plan(plan)


def emit_markdown(result: dict[str, Any]) -> None:
    print("# Skill Atlas Install")
    print()
    print(f"- status: {result['status']}")
    print(f"- mode: {'apply' if not result['read_only'] else 'preview'}")
    print(f"- canonical: `{result['canonical_path']}`")
    print(f"- platforms: {', '.join(result['platforms'])}")
    print(f"- command adapters: {str(result['commands_requested']).lower()}")
    print()
    for operation in result["operations"]:
        print(f"- {operation['status']}: `{operation['path']}`")
        print(f"  - target: `{operation['target']}`")
    if result["conflicts"]:
        print()
        print("Installation refused: existing paths would be overwritten.")
    elif result["read_only"]:
        print()
        print("No files or links were changed. Re-run with --apply --confirm after reviewing this plan.")
    else:
        print()
        print("Restart installed Agent applications before using the new commands.")
