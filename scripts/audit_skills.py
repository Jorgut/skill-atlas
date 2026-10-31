#!/usr/bin/env python3
"""Audit local skill installations and optional upstream freshness."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


HOME = Path.home()
KIMI_CODE_HOME = Path(os.environ.get("KIMI_CODE_HOME", str(HOME / ".kimi-code"))).expanduser()
DEFAULT_ROOTS = [
    HOME / ".codex" / "skills",
    HOME / ".agents" / "skills",
    KIMI_CODE_HOME / "skills",
    HOME / ".config" / "opencode" / "skills",
    HOME / ".claude" / "skills",
    HOME / ".codex" / "plugins" / "cache",
    HOME / ".codex" / "vendor_imports",
    HOME / ".cursor",
    HOME / ".gemini",
    HOME / ".codebuddy",
    HOME / ".cc-switch" / "skills",
]
EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "Library",
    ".Trash",
}


@dataclass
class SkillRecord:
    name: str
    description: str
    path: str
    root_class: str
    maintenance_class: str
    is_symlink: bool
    symlink_target: str
    upstream_url: str
    local_sha256: str
    update_status: str = "skipped"
    upstream_sha256: str = ""
    note: str = ""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def parse_frontmatter(text: str, fallback_name: str) -> tuple[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return fallback_name, ""
    block = match.group(1)
    lines = block.splitlines()
    name = fallback_name
    description = ""
    for idx, line in enumerate(lines):
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip("\"'")
        if line.startswith("description:"):
            value = line.split(":", 1)[1].strip()
            if value in {">", ">-", "|", "|-"}:
                collected: list[str] = []
                for follow in lines[idx + 1 :]:
                    if re.match(r"^[A-Za-z0-9_-]+:", follow):
                        break
                    collected.append(follow.strip())
                description = " ".join(x for x in collected if x)
            else:
                description = value.strip().strip("\"'")
    return name, description


def root_class(path: Path) -> str:
    s = str(path)
    if s.startswith(str(HOME / ".codex" / "skills") + os.sep):
        return "codex-loadable"
    if s.startswith(str(HOME / ".agents" / "skills") + os.sep):
        return "agents-loadable"
    if s.startswith(str(KIMI_CODE_HOME / "skills") + os.sep):
        return "kimi-loadable"
    if s.startswith(str(HOME / ".config" / "opencode" / "skills") + os.sep):
        return "opencode-loadable"
    if s.startswith(str(HOME / ".claude" / "skills") + os.sep):
        return "claude-loadable"
    if s.startswith(str(HOME / ".codex" / "plugins" / "cache") + os.sep):
        return "codex-plugin-cache"
    if s.startswith(str(HOME / ".codex" / "vendor_imports") + os.sep):
        return "codex-vendor-import"
    if s.startswith(str(HOME / ".cc-switch" / "skills") + os.sep):
        return "cc-switch"
    if "/.cursor/" in s:
        return "cursor"
    if "/.gemini/" in s:
        return "gemini"
    if "/.codebuddy/" in s:
        return "codebuddy"
    return "other"


def walk_skill_files(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()

    def add_path(path: Path) -> None:
        key = str(path.absolute())
        if key in seen:
            return
        seen.add(key)
        found.append(path)

    for root in roots:
        root = root.expanduser()
        if not root.exists():
            continue
        if root.is_file() and root.name == "SKILL.md":
            add_path(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for dirname in list(dirnames):
                candidate_dir = Path(dirpath) / dirname
                if candidate_dir.is_symlink():
                    candidate = candidate_dir / "SKILL.md"
                    if candidate.exists():
                        add_path(candidate)
            if "SKILL.md" not in filenames:
                continue
            path = Path(dirpath) / "SKILL.md"
            add_path(path)
    return sorted(found)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}


def first_string(data: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_github_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if "raw.githubusercontent.com" in value and value.endswith("SKILL.md"):
        return value
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*SKILL\.md)$", value)
    if match:
        owner, repo, ref, file_path = match.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{file_path}"
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.*)$", value)
    if match:
        owner, repo, ref, folder = match.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{folder.rstrip('/')}/SKILL.md"
    return value


def git_upstream(skill_dir: Path) -> tuple[str, str]:
    if not (skill_dir / ".git").exists():
        return "", ""
    try:
        remote = subprocess.check_output(
            ["git", "-C", str(skill_dir), "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        return "", ""
    match = re.match(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$", remote)
    if match:
        owner, repo = match.groups()
    else:
        match = re.match(r"https://github\.com/([^/]+)/(.+?)(?:\.git)?$", remote)
        if not match:
            return remote, "git-remote"
        owner, repo = match.groups()
    try:
        ref = subprocess.check_output(
            ["git", "-C", str(skill_dir), "branch", "--show-current"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        ref = ""
    if not ref:
        ref = "main"
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/SKILL.md", "git-remote"


def discover_upstream(skill_md: Path, text: str) -> tuple[str, str]:
    skill_dir = skill_md.parent
    evo = load_json(skill_dir / "evolution.json")
    upstream = evo.get("upstream")
    if isinstance(upstream, dict):
        url = first_string(upstream, ["raw_skill_md_url", "url", "source", "repo"])
        if url:
            return normalize_github_url(url), "evolution.json"

    for filename in ["skill.json", ".skill-source.json", "source.json"]:
        data = load_json(skill_dir / filename)
        url = first_string(data, ["raw_skill_md_url", "url", "source", "upstream", "repo"])
        if url:
            return normalize_github_url(url), filename

    raw_match = re.search(r"https://raw\.githubusercontent\.com/\S+/SKILL\.md", text)
    if raw_match:
        return raw_match.group(0).rstrip(").,]"), "SKILL.md"

    github_match = re.search(r"https://github\.com/[^)\s]+/(?:blob|tree)/[^)\s]+", text)
    if github_match:
        url = normalize_github_url(github_match.group(0).rstrip(").,]"))
        return url, "SKILL.md-hint"

    git_url, git_note = git_upstream(skill_dir)
    if git_url:
        return git_url, git_note

    return "", ""


def fetch_text(url: str) -> tuple[str, str]:
    req = Request(url, headers={"User-Agent": "skill-atlas"})
    try:
        with urlopen(req, timeout=30) as response:
            data = response.read()
        return data.decode("utf-8", errors="replace"), ""
    except (OSError, URLError) as exc:
        return "", str(exc)


def symlink_info(path: Path) -> tuple[bool, str]:
    if path.is_symlink():
        return True, str(path.resolve())
    if path.parent.is_symlink():
        return True, str(path.parent.resolve())
    return False, ""


def maintenance_class(path: Path, class_name: str, upstream_url: str) -> str:
    path_text = str(path)
    if class_name in {"codex-plugin-cache", "codebuddy", "codex-vendor-import", "cursor", "gemini"}:
        return "tool-bundled/cache"
    if upstream_url:
        return "external-maintained"
    if class_name in {"codex-loadable", "agents-loadable", "opencode-loadable", "claude-loadable", "cc-switch"}:
        if any(token in path_text for token in ["/plugins/cache/", "/marketplace", "/marketplaces/"]):
            return "tool-bundled/cache"
        return "unknown-local"
    return "unknown-local"


def build_records(roots: list[Path], check_upstream: bool) -> list[SkillRecord]:
    records: list[SkillRecord] = []
    for path in walk_skill_files(roots):
        is_link, link_target = symlink_info(path)
        try:
            text = read_text(path)
        except OSError as exc:
            records.append(
                SkillRecord(
                    name=path.parent.name,
                    description="",
                    path=str(path),
                    root_class=root_class(path),
                    maintenance_class="unknown-local",
                    is_symlink=is_link,
                    symlink_target=link_target,
                    upstream_url="",
                    local_sha256="",
                    update_status="unreadable",
                    note=str(exc),
                )
            )
            continue
        name, description = parse_frontmatter(text, path.parent.name)
        upstream_url, upstream_note = discover_upstream(path, text)
        class_name = root_class(path)
        record = SkillRecord(
            name=name,
            description=description,
            path=str(path),
            root_class=class_name,
            maintenance_class=maintenance_class(path, class_name, upstream_url),
            is_symlink=is_link,
            symlink_target=link_target,
            upstream_url=upstream_url,
            local_sha256=sha256_text(text),
            note=upstream_note,
        )
        if not upstream_url:
            record.update_status = "no-upstream"
        elif not check_upstream:
            record.update_status = "skipped"
        else:
            remote, error = fetch_text(upstream_url)
            if error:
                record.update_status = "fetch-failed"
                record.note = error
            else:
                record.upstream_sha256 = sha256_text(remote)
                record.update_status = (
                    "up-to-date" if record.upstream_sha256 == record.local_sha256 else "differs"
                )
        records.append(record)
    return records


def emit_json(records: list[SkillRecord]) -> None:
    print(json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2))


def emit_tsv(records: list[SkillRecord]) -> None:
    writer = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
    writer.writerow(list(SkillRecord.__dataclass_fields__.keys()))
    for record in records:
        writer.writerow([getattr(record, field) for field in SkillRecord.__dataclass_fields__])


def emit_markdown(records: list[SkillRecord]) -> None:
    by_class = Counter(r.root_class for r in records)
    by_maintenance = Counter(r.maintenance_class for r in records)
    by_status = Counter(r.update_status for r in records)
    by_name: dict[str, list[SkillRecord]] = defaultdict(list)
    for record in records:
        by_name[record.name].append(record)
    duplicates = {name: items for name, items in by_name.items() if len(items) > 1}
    update_candidates = [r for r in records if r.update_status in {"differs", "fetch-failed"}]
    symlinks = [r for r in records if r.is_symlink]
    platform_classes = {"codex-loadable", "agents-loadable", "opencode-loadable", "claude-loadable"}
    consolidation_candidates = []
    for name, items in duplicates.items():
        platform_items = [item for item in items if item.root_class in platform_classes]
        if len(platform_items) < 2:
            continue
        real_paths = {str(Path(item.path).resolve()) for item in platform_items}
        if len(real_paths) > 1:
            consolidation_candidates.append((name, platform_items, len(real_paths)))

    print("# Skill Update Audit")
    print()
    print(f"- Total SKILL.md files: {len(records)}")
    print(f"- Unique parsed names: {len(by_name)}")
    print(f"- Duplicate names: {len(duplicates)}")
    print(f"- Symlinked skill entries: {len(symlinks)}")
    print()
    print("## By Root Class")
    print()
    for key, count in by_class.most_common():
        print(f"- {key}: {count}")
    print()
    print("## By Maintenance Class")
    print()
    for key, count in by_maintenance.most_common():
        print(f"- {key}: {count}")
    print()
    print("## Update Status")
    print()
    for key, count in by_status.most_common():
        print(f"- {key}: {count}")
    print()

    if update_candidates:
        print("## Update Candidates")
        print()
        for record in update_candidates[:100]:
            print(f"- {record.name} [{record.update_status}]")
            print(f"  - path: `{record.path}`")
            if record.upstream_url:
                print(f"  - upstream: {record.upstream_url}")
            if record.note:
                print(f"  - note: {record.note}")
        print()

    if symlinks:
        print("## Symlinked Skills")
        print()
        for record in symlinks[:100]:
            print(f"- {record.name} [{record.root_class}]")
            print(f"  - path: `{record.path}`")
            print(f"  - target: `{record.symlink_target}`")
        if len(symlinks) > 100:
            print(f"- ... {len(symlinks) - 100} more")
        print()

    if consolidation_candidates:
        print("## Consolidation Suggestions")
        print()
        print(
            "These skills appear as separate physical copies in multiple agent-loadable roots. "
            "Consider keeping one canonical directory and exposing it to each agent with symlinks."
        )
        print()
        for name, items, real_count in sorted(consolidation_candidates)[:100]:
            classes = ", ".join(sorted({item.root_class for item in items}))
            print(f"- {name}: {len(items)} entries, {real_count} physical targets ({classes})")
            for item in items[:8]:
                print(f"  - `{item.path}`")
        if len(consolidation_candidates) > 100:
            print(f"- ... {len(consolidation_candidates) - 100} more")
        print()

    print("## Duplicate Names")
    print()
    for name, items in sorted(duplicates.items()):
        classes = ", ".join(sorted({item.root_class for item in items}))
        print(f"- {name}: {len(items)} copies ({classes})")
        for item in items[:8]:
            print(f"  - `{item.path}`")
        if len(items) > 8:
            print(f"  - ... {len(items) - 8} more")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Root directory to scan. May be repeated. Defaults to common local skill roots.",
    )
    parser.add_argument(
        "--check-upstream",
        action="store_true",
        help="Fetch recorded upstream raw SKILL.md URLs and compare hashes.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "tsv"],
        default="markdown",
        help="Output format.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    roots = [Path(value).expanduser() for value in args.root] if args.root else DEFAULT_ROOTS
    records = build_records(roots, args.check_upstream)
    if args.format == "json":
        emit_json(records)
    elif args.format == "tsv":
        emit_tsv(records)
    else:
        emit_markdown(records)


if __name__ == "__main__":
    main()
