#!/usr/bin/env python3
"""First-run guide for Skill Atlas.

This is an explicit onboarding command, not a daemon or a popup. It prints a
short tour, the safest first commands, and links to the detailed guides.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "skill.json").read_text(encoding="utf-8")).get("version", "unknown")
REPO = "https://github.com/Jorgut/skill-atlas"


def guide() -> dict[str, Any]:
    return {
        "version": VERSION,
        "title": "Welcome to Skill Atlas",
        "summary": "A local-first atlas of your agent environment: what exists, what it loads, where copies drift, what takes disk space, and which commits are still local.",
        "quickstart": [
            {
                "command": "python3 scripts/skill_atlas.py agents scan",
                "purpose": "See which agent tools and Skill Atlas copies exist on this machine.",
            },
            {
                "command": "python3 scripts/skill_atlas.py projects audit --project <path>",
                "purpose": "Find duplicate project copies and drifted AGENTS.md / CLAUDE.md / state docs.",
            },
            {
                "command": "python3 scripts/skill_atlas.py disk scan --min-file-mb 100",
                "purpose": "Find what agent work uses on disk; cleanup is opt-in and moves to Trash.",
            },
            {
                "command": "python3 scripts/skill_atlas.py sync status --project .",
                "purpose": "Check unpushed commits, missing upstream, behind-remote and dirty state.",
            },
            {
                "command": "python3 scripts/skill_atlas.py sync setup --project . --confirm",
                "purpose": "Install the optional macOS push reminder (preview without --confirm).",
            },
        ],
        "workflows": [
            {"name": "Agent environment scan", "doc": f"{REPO}/blob/main/docs/agent-environments.md"},
            {"name": "Project root audit", "doc": f"{REPO}/blob/main/docs/project-root-audit.md"},
            {"name": "Disk usage audit", "doc": f"{REPO}/blob/main/docs/disk-scan.md"},
            {"name": "Sync notifications", "doc": f"{REPO}/blob/main/docs/sync-notify.md"},
            {"name": "Sync setup", "doc": f"{REPO}/blob/main/docs/sync-setup.md"},
            {"name": "Beginner guide", "doc": f"{REPO}/blob/main/docs/GETTING_STARTED.en.md"},
        ],
        "safety": [
            "Read-only by default.",
            "No automatic push, commit, fetch, merge, or deletion.",
            "Disk cleanup only moves selected low/medium risk paths to Trash.",
            "Runtime loading is never claimed from file evidence alone.",
        ],
        "next_steps": [
            "Run agents scan first.",
            "Run projects audit on each active project.",
            "If disk is tight, run disk scan and review before cleanup.",
            "For push reminders, run sync setup (macOS) or sync notify from a hook.",
        ],
    }


def emit_markdown(result: dict[str, Any]) -> None:
    print(f"# {result['title']}")
    print()
    print(f"**Version:** {result['version']}")
    print()
    print(result["summary"])
    print()
    print("## Quickstart")
    print()
    for item in result["quickstart"]:
        print(f"- `{item['command']}`")
        print(f"  - {item['purpose']}")
    print()
    print("## Workflows")
    print()
    for item in result["workflows"]:
        print(f"- [{item['name']}]({item['doc']})")
    print()
    print("## Safety")
    print()
    for item in result["safety"]:
        print(f"- {item}")
    print()
    print("## Suggested order")
    print()
    for item in result["next_steps"]:
        print(f"- {item}")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
