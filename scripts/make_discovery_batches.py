#!/usr/bin/env python3
"""Create batched external discovery worklists from a local skill inventory."""

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

USER_LOADABLE_ROOTS = {
    "codex-loadable",
    "agents-loadable",
    "opencode-loadable",
    "claude-loadable",
    "cc-switch",
}
MARKETPLACE_HINTS = (
    "plugins/cache",
    "marketplace",
    "marketplaces",
    ".codebuddy",
    "vendor_imports",
)
CATEGORY_TERMS = {
    "design-ux": ["ux", "ui", "design", "frontend", "figma", "slides", "canvas", "brand"],
    "coding": ["python", "go", "java", "django", "spring", "backend", "testing", "tdd", "review", "patterns", "git"],
    "data-ai": ["ai", "llm", "model", "hugging", "dataset", "eval", "notebook", "postgres", "clickhouse", "supabase"],
    "docs-media": ["pdf", "docx", "pptx", "xlsx", "slides", "youtube", "video", "article"],
    "ops-tools": ["browser", "chrome", "vercel", "deploy", "mcp", "calendar", "gmail", "slack", "automation"],
    "domain": ["finance", "architecture", "space", "arch", "boq", "biology", "security", "calendar"],
}


def run_audit() -> list[dict[str, Any]]:
    output = subprocess.check_output([sys.executable, str(AUDIT_SCRIPT), "--format", "json"], text=True)
    return json.loads(output)


def classify_category(name: str, description: str) -> str:
    text = f"{name} {description}".lower()
    scores = {}
    for category, terms in CATEGORY_TERMS.items():
        scores[category] = sum(1 for term in terms if term in text)
    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score else "other"


def is_self_developed(items: list[dict[str, Any]]) -> bool:
    roots = {item.get("root_class", "") for item in items}
    paths = " ".join(item.get("path", "") for item in items)
    has_upstream = any(item.get("upstream_url") for item in items)
    return bool(roots & USER_LOADABLE_ROOTS) and not has_upstream and not any(
        hint in paths for hint in MARKETPLACE_HINTS
    )


def tokens(value: str) -> list[str]:
    found = re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{1,}", value.lower())
    stop = {"skill", "skills", "agent", "agents", "local", "using", "with", "when", "user", "users", "create", "manage", "this", "that", "and", "for", "the"}
    result = []
    seen: set[str] = set()
    for item in found:
        item = item.strip("-_.")
        if len(item) < 3 or item in stop or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result[:8]


def build_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_name[record.get("name", "")].append(record)
    rows = []
    for name, items in sorted(by_name.items()):
        descriptions = [item.get("description", "") for item in items if item.get("description")]
        description = descriptions[0] if descriptions else ""
        category = classify_category(name, description)
        self_developed = is_self_developed(items)
        words = " ".join(tokens(f"{name} {description}")[:5]) or name
        rows.append(
            {
                "name": name,
                "category": category,
                "mode": "competitor-only" if self_developed else "replacement-or-complement",
                "copies": len(items),
                "root_classes": sorted({item.get("root_class", "") for item in items}),
                "sample_path": items[0].get("path", ""),
                "description": description,
                "query_pack": [
                    f'"{name}" "SKILL.md"',
                    f'{words} agent skill "SKILL.md"',
                    f'{words} Claude Code skill',
                    f'{words} Codex skill',
                    f'{words} OpenCode skill',
                    f'{words} AI agent workflow GitHub',
                ],
                "decision_rule": "do not replace; collect competitors and ideas" if self_developed else "may recommend replace, complement, or skip after review",
            }
        )
    return rows


def batches(rows: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    result = []
    for idx in range(0, len(rows), size):
        chunk = rows[idx : idx + size]
        result.append(
            {
                "batch": len(result) + 1,
                "start": idx + 1,
                "end": idx + len(chunk),
                "count": len(chunk),
                "categories": sorted({row["category"] for row in chunk}),
                "items": chunk,
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()
    rows = build_rows(run_audit())
    if args.format == "json":
        print(json.dumps({"total": len(rows), "batch_size": args.batch_size, "batches": batches(rows, args.batch_size)}, ensure_ascii=False, indent=2))
        return
    print("# External Discovery Batches")
    print()
    print(f"- unique skills: {len(rows)}")
    print(f"- batch size: {args.batch_size}")
    print(f"- batches: {(len(rows) + args.batch_size - 1) // args.batch_size}")
    print()
    for batch in batches(rows, args.batch_size):
        print(f"## Batch {batch['batch']} ({batch['start']}-{batch['end']})")
        print()
        for item in batch["items"]:
            print(f"- {item['name']} [{item['category']}, {item['mode']}]")
        print()


if __name__ == "__main__":
    main()
