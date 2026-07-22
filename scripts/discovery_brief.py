#!/usr/bin/env python3
"""Create external discovery briefs for local skills."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
AUDIT_SCRIPT = SCRIPT_DIR / "audit_skills.py"

SOURCE_HINTS = [
    "GitHub",
    "SkillsMP",
    "SkillMD",
    "Playbooks",
    "ClawHub",
    "Claude Code skills",
    "OpenAI Codex skills",
    "OpenCode skills",
]


def run_audit(roots: list[str]) -> list[dict[str, Any]]:
    cmd = [sys.executable, str(AUDIT_SCRIPT), "--format", "json"]
    for root in roots:
        cmd.extend(["--root", root])
    output = subprocess.check_output(cmd, text=True)
    return json.loads(output)


def tokens(value: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{1,}", value.lower())
    stop = {
        "skill",
        "skills",
        "agent",
        "agents",
        "local",
        "using",
        "with",
        "when",
        "user",
        "users",
        "create",
        "manage",
        "use",
        "this",
        "that",
        "and",
        "for",
        "the",
    }
    seen: set[str] = set()
    result = []
    for item in raw:
        item = item.strip("-_.")
        if item in stop or len(item) < 3 or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result[:10]


def skill_briefs(records: list[dict[str, Any]], focus: str) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_name[record.get("name", "")].append(record)

    briefs = []
    focus_l = focus.lower().strip()
    for name, items in sorted(by_name.items()):
        descriptions = [item.get("description", "") for item in items if item.get("description")]
        combined = " ".join([name] + descriptions)
        combined_tokens = set(tokens(combined))
        if focus_l and focus_l not in combined_tokens and focus_l not in name.lower().split("-"):
            continue
        terms = tokens(combined)
        domain = " ".join(terms[:5]) or name
        queries = [
            f'"{name}" "SKILL.md"',
            f'{domain} agent skill "SKILL.md"',
            f'{domain} Claude Code skill',
            f'{domain} Codex skill',
            f'{domain} OpenCode skill',
            f'{domain} AI agent workflow GitHub',
        ]
        briefs.append(
            {
                "name": name,
                "copies": len(items),
                "root_classes": sorted({item.get("root_class", "") for item in items}),
                "sample_path": items[0].get("path", ""),
                "description": descriptions[0] if descriptions else "",
                "discovery_queries": queries,
                "source_hints": SOURCE_HINTS,
            }
        )
    return briefs


def emit_markdown(briefs: list[dict[str, Any]], limit: int) -> None:
    print("# External Skill Discovery Brief")
    print()
    print("Use these briefs to search for better or complementary public skills. Do not install anything without reviewing the source, license, and local fit.")
    print()
    for brief in briefs[:limit]:
        print(f"## {brief['name']}")
        print()
        print(f"- copies: {brief['copies']}")
        print(f"- roots: {', '.join(brief['root_classes'])}")
        print(f"- sample: `{brief['sample_path']}`")
        if brief["description"]:
            print(f"- local description: {brief['description']}")
        print("- search queries:")
        for query in brief["discovery_queries"]:
            print(f"  - {query}")
        print("- compare on: source trust, trigger clarity, scripts/assets quality, update recency, license, install safety, and whether it should replace or complement the local skill")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", default=[], help="Root directory to scan. May be repeated.")
    parser.add_argument("--focus", default="", help="Only include skills whose name/description contains this text.")
    parser.add_argument("--limit", type=int, default=30, help="Maximum markdown briefs to print.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    briefs = skill_briefs(run_audit(args.root), args.focus)
    if args.format == "json":
        print(json.dumps(briefs, ensure_ascii=False, indent=2))
    else:
        emit_markdown(briefs, args.limit)


if __name__ == "__main__":
    main()
