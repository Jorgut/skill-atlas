#!/usr/bin/env python3
"""Plan how Skill Development Kit could create a skill; does not install or create it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

METHODS = {
    "github": ("skill-from-github", "Inspect maintained GitHub implementations and distill methods"),
    "masters": ("skill-from-masters", "Extract proven and failed practices from real cases"),
    "notebook": ("skill-from-notebook", "Extract repeatable methods from documents and notes"),
}


def choose(request: str, source: str) -> tuple[str | None, str]:
    if source != "auto":
        return source, "explicit source selection"
    lower = request.lower()
    matched = []
    if any(word in lower for word in ("github", "repository", "repo", "开源", "仓库")):
        matched.append("github")
    if any(word in lower for word in ("notebook", "notes", "document", "pdf", "笔记", "文档")):
        matched.append("notebook")
    if any(word in lower for word in ("case study", "real cases", "best practice", "案例", "实践")):
        matched.append("masters")
    if len(matched) == 1:
        return matched[0], "matched an explicit source type in the request"
    return None, "source type is ambiguous; review available methods"


def build_plan(request: str, source: str, kit_root: str | None) -> dict:
    chosen, reason = choose(request, source)
    root = Path(kit_root).expanduser().resolve() if kit_root else None
    possible = (
        root / "skills" / METHODS[chosen][0] / "SKILL.md"
        if root is not None and chosen else None
    )
    return {
        "status": "ready-to-invoke" if possible and possible.is_file() else "plan-only",
        "request": request,
        "selected_method": METHODS[chosen][0] if chosen else None,
        "selection_reason": reason,
        "methods": [
            {"name": value[0], "purpose": value[1]} for value in METHODS.values()
        ],
        "kit_root": str(root) if root else None,
        "skill_entry": str(possible) if possible and possible.is_file() else None,
        "next_action": (
            "Open and follow the verified skill entry in the selected tool; review generated Skill and tests"
            if possible and possible.is_file()
            else "Choose a source type and verify an installed Skill Development Kit before invoking creation"
        ),
        "read_only": True,
        "executed": False,
        "external_source": "https://github.com/Jorgut/skill-development-kit",
    }


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("request", help="Requested skill and source material")
    parser.add_argument("--from", dest="source", choices=("auto", *METHODS), default="auto")
    parser.add_argument("--kit-root", help="Existing local Skill Development Kit checkout")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")


def run(args: argparse.Namespace) -> dict:
    if not args.request.strip():
        raise ValueError("Skill request cannot be empty")
    return build_plan(args.request, args.source, args.kit_root)


def emit_markdown(result: dict) -> None:
    print("# Skill Atlas: Skill creation plan")
    print(f"- status: {result['status']}")
    print(f"- chosen method: {result['selected_method'] or 'not yet selected'}")
    print(f"- selection: {result['selection_reason']}")
    print(f"- kit source: {result['external_source']}")
    if result["skill_entry"]:
        print(f"- skill entry: {result['skill_entry']}")
    print(f"- next: {result['next_action']}")
    print("- no skill was created, installed, or executed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = parser.parse_args()
    result = run(args)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_markdown(result)


if __name__ == "__main__":
    main()
