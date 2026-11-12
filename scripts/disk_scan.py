#!/usr/bin/env python3
"""Read-only disk audit for agent tools, caches, sessions and project copies.

The audit answers one question: what on this machine is taking space that agent
work produced? It only reads file metadata (never file contents, credentials or
session text), never follows directory symlinks, and labels every candidate
with a risk level and a suggested action. By default it never moves or deletes
anything; an explicit ``--apply --to-trash --confirm`` moves selected low/medium
risk candidates into the trash directory (never ``rm -rf``).

Default scope is a set of known agent homes below the scanned home directory,
plus optional ``--root`` and ``--project`` paths. Both apparent (``st_size``)
and allocated (``st_blocks x 512``) sizes are reported; allocated size is the
real disk usage, while sparse files can have a much larger apparent size. APFS
clones, snapshots and hard links can still mean that deleting a path does not
free all of its allocated blocks, which every result states in its limitations.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
DEFAULT_TOP_FILES = 15
DEFAULT_MIN_FILE_MB = 200.0
DEFAULT_MAX_ENTRIES = 400000

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
CLEANUP_RISKS = (RISK_LOW, RISK_MEDIUM)


class DiskScanError(ValueError):
    """Unsafe or unsupported disk cleanup request."""


@dataclass(frozen=True)
class RootSpec:
    """One known or requested scan root."""

    id: str
    label: str
    relative: str | None
    evidence: str = "documented"


# Known agent homes. ``documented`` mirrors the paths documented in this
# repository; other entries stay candidates and should be verified per version.
KNOWN_ROOTS: tuple[RootSpec, ...] = (
    RootSpec("codex", "Codex home", ".codex"),
    RootSpec("claude-code", "Claude Code home", ".claude"),
    RootSpec("deepseek-harness", "DeepSeek Harness home", ".dsh"),
    RootSpec("cc-switch", "CC Switch skills", ".cc-switch", "candidate"),
    RootSpec("opencode", "OpenCode config", ".config/opencode", "candidate"),
    RootSpec("workbuddy", "WorkBuddy home", ".workbuddy", "candidate"),
    RootSpec("kimi-code", "Kimi Code home", ".kimi-code", "candidate"),
    RootSpec("cursor", "Cursor home", ".cursor", "candidate"),
    RootSpec(
        "xcode-developer",
        "Xcode developer data",
        "Library/Developer/Xcode",
        "candidate",
    ),
)

CATEGORY_RISK = {
    "agent-cache": RISK_LOW,
    "build-artifact": RISK_LOW,
    "agent-session": RISK_MEDIUM,
    "agent-attachment": RISK_MEDIUM,
    "plugin-package": RISK_MEDIUM,
    "archive": RISK_MEDIUM,
    "project-media": RISK_MEDIUM,
    "git-object": RISK_HIGH,
    "database": RISK_HIGH,
    "other": RISK_MEDIUM,
}

CATEGORY_ACTION = {
    "agent-cache": "Regenerable cache: close the owning tool before removing it.",
    "build-artifact": "Regenerable build output: rebuild when needed.",
    "agent-session": "Review age and keep what matters: archive old sessions elsewhere or prune them with the tool's own controls.",
    "agent-attachment": "Review old session attachments; keep only what is needed.",
    "plugin-package": "Plugins and package caches are usually reinstallable; check for local development plugins first.",
    "archive": "Move to external storage or delete only after verifying the archive is not the only copy.",
    "project-media": "Move finished media to external storage; keep the final exports and remove intermediate renders.",
    "git-object": "Never delete directly: migrate large media with Git LFS or start a new history without it.",
    "database": "Never delete: back it up first and consider the tool's own maintenance command (for example VACUUM).",
    "other": "Review manually; nothing is recommended automatically.",
}

SESSION_NAMES = {
    "sessions",
    "archived_sessions",
    "projects",
    "transcripts",
    "rollouts",
    "history",
    "threads",
}
CACHE_NAMES = {
    "codingassistant",
    "cache",
    "caches",
    ".cache",
    ".tmp",
    "tmp",
    "temp",
    "computer-use",
    "visualizations",
    "generated_images",
}
BUILD_NAMES = {
    "node_modules",
    ".build",
    "build",
    "dist",
    "target",
    "deriveddata",
    "__pycache__",
    ".next",
    ".venv",
    "venv",
    "pods",
    ".gradle",
    ".turbo",
    ".parcel-cache",
}
PLUGIN_NAMES = {"plugins", "packages", "extensions"}
ATTACHMENT_NAMES = {"attachments", "uploads"}
MEDIA_DIR_NAMES = {"media", "audio", "video", "videos", "renders", "exports", "footage", "images", "photos"}
ARCHIVE_NAMES = {"archive", "archives", "backups", "backup", "old"}
MEDIA_SUFFIXES = {
    ".wav",
    ".aiff",
    ".flac",
    ".mp3",
    ".mp4",
    ".mov",
    ".m4v",
    ".mkv",
    ".psd",
    ".ai",
    ".aep",
    ".prproj",
    ".dng",
    ".raw",
}
DATABASE_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".db-wal", ".db-shm"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError:
        return path.expanduser()


def _posix(path: Path) -> str:
    return path.as_posix()


def _human(size: int | float) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{value:.0f} B"
        value /= 1024
    return f"{value:.1f} TiB"


def _stat_sizes(stat: os.stat_result) -> tuple[int, int]:
    """Return (apparent size, allocated size) for one file."""
    apparent = int(stat.st_size)
    blocks = getattr(stat, "st_blocks", None)
    allocated = int(blocks) * 512 if isinstance(blocks, int) else apparent
    return apparent, max(0, allocated)


def _human_pair(apparent: int | float, allocated: int | float) -> str:
    if allocated == apparent:
        return _human(allocated)
    return f"{_human(allocated)} allocated ({_human(apparent)} apparent)"


def classify_name(name: str, is_dir: bool, inside_git: bool = False) -> str:
    """Classify one entry by its name, never by reading its contents."""
    lowered = name.casefold()
    if inside_git:
        return "git-object"
    if is_dir:
        if lowered in SESSION_NAMES or lowered.startswith("session"):
            return "agent-session"
        if lowered in CACHE_NAMES:
            return "agent-cache"
        if lowered in BUILD_NAMES:
            return "build-artifact"
        if lowered in PLUGIN_NAMES:
            return "plugin-package"
        if lowered in ATTACHMENT_NAMES:
            return "agent-attachment"
        if lowered in MEDIA_DIR_NAMES:
            return "project-media"
        if lowered in ARCHIVE_NAMES:
            return "archive"
        return "other"
    suffix = Path(name).suffix.casefold()
    if suffix in DATABASE_SUFFIXES or lowered.startswith("thread_history"):
        return "database"
    if suffix in MEDIA_SUFFIXES:
        return "project-media"
    return "other"


def classify_path(path: Path) -> str:
    """Classify a file by its nearest meaningful parent directory."""
    parts = path.parts
    for index in range(len(parts) - 2, -1, -1):
        part = parts[index]
        if part == ".git":
            return "git-object"
        category = classify_name(part, True)
        if category != "other":
            return category
    return classify_name(path.name, False, ".git" in parts)


def _walk_files(
    path: Path,
    *,
    max_entries: int,
    state: dict[str, Any],
    min_file_bytes: int,
    candidates: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """Walk a tree, collecting large files and apparent + allocated sizes."""
    apparent_total = 0
    allocated_total = 0
    files = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            state["skipped"] += 1
            continue
        for entry in entries:
            if state["entries"] >= max_entries:
                state["truncated"] = True
                return apparent_total, allocated_total, files
            state["entries"] += 1
            try:
                if entry.is_symlink():
                    state["symlinks"] += 1
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    stat = entry.stat(follow_symlinks=False)
                    apparent, allocated = _stat_sizes(stat)
                    apparent_total += apparent
                    allocated_total += allocated
                    files += 1
                    if allocated >= min_file_bytes:
                        candidates.append(
                            {
                                "path": _posix(Path(entry.path)),
                                "size_bytes": apparent,
                                "allocated_bytes": allocated,
                                "modified_at": datetime.fromtimestamp(
                                    stat.st_mtime, timezone.utc
                                ).isoformat(),
                                "inside_git": ".git" in Path(entry.path).parts,
                            }
                        )
            except OSError:
                state["skipped"] += 1
    return apparent_total, allocated_total, files


def _root_entries(
    root: Path, *, max_entries: int, min_file_bytes: int, candidates: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, int, int, dict[str, Any]]:
    state = {"entries": 0, "skipped": 0, "symlinks": 0, "truncated": False}
    children: list[dict[str, Any]] = []
    total = 0
    allocated_total = 0
    files = 0
    try:
        direct = list(os.scandir(root))
    except OSError:
        return [], 0, 0, 0, state
    for entry in direct:
        path = Path(entry.path)
        try:
            if entry.is_symlink():
                state["symlinks"] += 1
                continue
            if entry.is_dir(follow_symlinks=False):
                child_size, child_allocated, child_files = _walk_files(
                    path,
                    max_entries=max_entries,
                    state=state,
                    min_file_bytes=min_file_bytes,
                    candidates=candidates,
                )
            elif entry.is_file(follow_symlinks=False):
                stat = entry.stat(follow_symlinks=False)
                child_size, child_allocated = _stat_sizes(stat)
                child_files = 1
                if child_allocated >= min_file_bytes:
                    candidates.append(
                        {
                            "path": _posix(path),
                            "size_bytes": child_size,
                            "allocated_bytes": child_allocated,
                            "modified_at": datetime.fromtimestamp(
                                stat.st_mtime, timezone.utc
                            ).isoformat(),
                            "inside_git": ".git" in path.parts,
                        }
                    )
            else:
                continue
        except OSError:
            state["skipped"] += 1
            continue
        total += child_size
        allocated_total += child_allocated
        files += child_files
        category = classify_name(
            entry.name, entry.is_dir(follow_symlinks=False), ".git" in path.parts
        )
        children.append(
            {
                "name": entry.name,
                "path": _posix(path),
                "is_dir": entry.is_dir(follow_symlinks=False),
                "size_bytes": child_size,
                "allocated_bytes": child_allocated,
                "files": child_files,
                "category": category,
                "risk": CATEGORY_RISK.get(category, RISK_MEDIUM),
            }
        )
    children.sort(key=lambda item: item["allocated_bytes"], reverse=True)
    return children, total, allocated_total, files, state


def _dedupe_roots(paths: Iterable[Path]) -> list[Path]:
    normalized: list[Path] = []
    seen: set[str] = set()
    for path in sorted({_normalize(Path(item)) for item in paths}, key=lambda p: (len(p.parts), str(p))):
        key = _posix(path)
        if key in seen:
            continue
        if any(_posix(path).startswith(_posix(parent) + "/") for parent in normalized):
            continue
        seen.add(key)
        normalized.append(path)
    return normalized


def scan(
    home: Path,
    roots: Iterable[Path] | None = None,
    project: Path | None = None,
    *,
    top_files: int = DEFAULT_TOP_FILES,
    min_file_mb: float = DEFAULT_MIN_FILE_MB,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> dict[str, Any]:
    """Return a disk audit; read-only unless the caller applies a Trash plan."""
    home = _normalize(Path(home))
    project = _normalize(Path(project)) if project is not None else None
    top_files = max(0, min(100, int(top_files)))
    min_file_bytes = max(0, int(float(min_file_mb) * 1024 * 1024))
    max_entries = max(1000, int(max_entries))

    candidates: list[dict[str, Any]] = []
    root_specs: list[dict[str, Any]] = []
    requested: list[tuple[Path, dict[str, Any]]] = []
    for spec in KNOWN_ROOTS:
        path = home / (spec.relative or "")
        requested.append(
            (
                path,
                {
                    "id": spec.id,
                    "label": spec.label,
                    "evidence": spec.evidence,
                    "source": "known-root",
                },
            )
        )
    for extra in roots or []:
        requested.append(
            (
                _normalize(Path(extra)),
                {"id": _posix(_normalize(Path(extra))), "label": "Requested root",
                 "evidence": "explicit", "source": "argument"},
            )
        )
    if project is not None:
        requested.append(
            (
                project,
                {"id": "project", "label": "Project", "evidence": "explicit",
                 "source": "project"},
            )
        )

    # Keep the outermost requested roots so nested roots are not counted twice.
    existing = [(path, meta) for path, meta in requested if _safe_exists(path)]
    unique_paths = _dedupe_roots(path for path, _ in existing)
    meta_for = {_posix(path): meta for path, meta in existing}
    nested_skipped = sorted(
        {
            _posix(path)
            for path, _ in existing
            if _posix(path) not in {_posix(item) for item in unique_paths}
        }
    )

    for path in unique_paths:
        meta = meta_for[_posix(path)]
        children, total, total_allocated, files, state = _root_entries(
            path, max_entries=max_entries, min_file_bytes=min_file_bytes, candidates=candidates
        )
        category_totals: dict[str, int] = {}
        for child in children:
            category_totals[child["category"]] = (
                category_totals.get(child["category"], 0) + child["allocated_bytes"]
            )
        root_specs.append(
            {
                **meta,
                "path": _posix(path),
                "exists": True,
                "size_bytes": total,
                "allocated_bytes": total_allocated,
                "files": files,
                "entries": children,
                "categories": [
                    {"category": category, "allocated_bytes": size}
                    for category, size in sorted(
                        category_totals.items(), key=lambda item: item[1], reverse=True
                    )
                ],
                "skipped": state.get("skipped", 0),
                "symlinks_skipped": state.get("symlinks", 0),
                "truncated": bool(state.get("truncated")),
            }
        )

    candidates.sort(key=lambda item: item["allocated_bytes"], reverse=True)
    top = candidates[:top_files]
    for item in top:
        category = classify_path(Path(item["path"]))
        item["category"] = category
        item["risk"] = CATEGORY_RISK.get(category, RISK_MEDIUM)
        item.pop("inside_git", None)

    reclaimable: list[dict[str, Any]] = []
    for root in root_specs:
        for child in root["entries"]:
            if child["category"] == "other":
                continue
            reclaimable.append(
                {
                    "path": child["path"],
                    "size_bytes": child["size_bytes"],
                    "allocated_bytes": child["allocated_bytes"],
                    "category": child["category"],
                    "risk": child["risk"],
                    "suggested_action": CATEGORY_ACTION[child["category"]],
                    "root_id": root["id"],
                }
            )
    reclaimable.sort(key=lambda item: item["allocated_bytes"], reverse=True)

    risk_totals = {RISK_LOW: 0, RISK_MEDIUM: 0, RISK_HIGH: 0}
    for item in reclaimable:
        risk_totals[item["risk"]] = risk_totals.get(item["risk"], 0) + item["allocated_bytes"]

    return {
        "schema_version": SCHEMA_VERSION,
        "scan": {
            "home": _posix(home),
            "project": _posix(project) if project is not None else None,
            "generated_at": utc_now().isoformat(),
            "top_files": top_files,
            "min_file_mb": float(min_file_mb),
            "min_file_basis": "allocated_bytes",
        },
        "roots": root_specs,
        "top_files": top,
        "reclaimable": reclaimable,
        "nested_roots_skipped": nested_skipped,
        "summary": {
            "roots_scanned": len(root_specs),
            "total_bytes": sum(root["size_bytes"] for root in root_specs),
            "total_allocated_bytes": sum(root["allocated_bytes"] for root in root_specs),
            "files": sum(root["files"] for root in root_specs),
            "low_risk_bytes": risk_totals.get(RISK_LOW, 0),
            "medium_risk_bytes": risk_totals.get(RISK_MEDIUM, 0),
            "high_risk_bytes": risk_totals.get(RISK_HIGH, 0),
        },
        "limitations": [
            "Both apparent and allocated sizes are reported. Allocated size (st_blocks x 512) is the real disk usage; apparent size is what tools such as du --apparent-size show, and sparse files can have a huge apparent size with almost no allocation.",
            "APFS compression, clones, snapshots and hard links can make the real reclaimable space different from either size; deleting a path does not always free all of its allocated blocks.",
            "Only metadata was read: no file contents, credentials, session text or account data were read, stored or uploaded.",
            "Directory symlinks are never followed, so linked roots and external volumes are not counted.",
            "Known roots are discovery hints and may be version-specific; paths that do not exist are omitted.",
            "The scan is read-only. --apply --to-trash --confirm moves selected low/medium risk paths into the trash directory; it never deletes them permanently, and high-risk paths are never moved.",
            "Database and Git object sizes are reported for awareness only; deleting them directly can lose history or state.",
        ],
    }


def _safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _unique_trash_path(trash_dir: Path, name: str) -> Path:
    candidate = trash_dir / name
    if not candidate.exists() and not candidate.is_symlink():
        return candidate
    stamp = utc_now().strftime("%Y%m%dT%H%M%S")
    for index in range(1, 1000):
        suffix = f"-{stamp}" if index == 1 else f"-{stamp}-{index}"
        candidate = trash_dir / f"{name}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise DiskScanError("Could not find an unused name in the trash directory")


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def apply_plan(
    result: dict[str, Any],
    *,
    risks: Iterable[str],
    trash_dir: Path,
) -> dict[str, Any]:
    """Move selected reclaimable paths into a trash directory (never delete)."""
    selected = tuple(dict.fromkeys(risks))
    invalid = [risk for risk in selected if risk not in CLEANUP_RISKS]
    if invalid:
        raise DiskScanError(
            "Cleanup risks must be low or medium; high-risk paths are never moved"
        )
    if not selected:
        raise DiskScanError("Select at least one cleanup risk")
    trash_dir = _normalize(Path(trash_dir))
    if not trash_dir.is_dir():
        raise DiskScanError(f"Trash directory does not exist: {trash_dir}")
    trash_real = _normalize(trash_dir)
    moved: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in result.get("reclaimable", []):
        if item.get("risk") not in selected:
            continue
        source = Path(item["path"])
        if item.get("risk") == RISK_HIGH:
            skipped.append({**item, "reason": "high-risk paths are never moved"})
            continue
        if source.is_symlink():
            skipped.append({**item, "reason": "symlinks are not moved"})
            continue
        if not _safe_exists(source):
            skipped.append({**item, "reason": "no longer exists"})
            continue
        source = _normalize(source)
        if source == trash_real or _inside(trash_real, source) or _inside(source, trash_real):
            skipped.append({**item, "reason": "path overlaps the trash directory"})
            continue
        try:
            destination = _unique_trash_path(trash_real, source.name)
            shutil.move(str(source), str(destination))
        except (OSError, shutil.Error) as exc:
            failed.append({**item, "reason": str(exc)})
            continue
        moved.append(
            {
                "path": _posix(source),
                "trash_path": _posix(destination),
                "size_bytes": item["size_bytes"],
                "allocated_bytes": item["allocated_bytes"],
                "category": item["category"],
                "risk": item["risk"],
            }
        )
    return {
        "status": "applied" if moved else "no-candidates",
        "trash_dir": _posix(trash_real),
        "selected_risks": list(selected),
        "moved": moved,
        "skipped": skipped,
        "failed": failed,
        "reclaimed_allocated_bytes": sum(item["allocated_bytes"] for item in moved),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    result = scan(
        Path(args.home),
        roots=[Path(item) for item in getattr(args, "root", [])],
        project=Path(args.project) if getattr(args, "project", None) else None,
        top_files=getattr(args, "top", DEFAULT_TOP_FILES),
        min_file_mb=getattr(args, "min_file_mb", DEFAULT_MIN_FILE_MB),
        max_entries=getattr(args, "max_entries", DEFAULT_MAX_ENTRIES),
    )
    if not getattr(args, "apply", False):
        return result
    if not getattr(args, "to_trash", False):
        raise DiskScanError("--apply requires --to-trash; permanent deletion is not supported")
    if not getattr(args, "confirm", False):
        raise DiskScanError("--apply requires --confirm")
    risks = list(getattr(args, "risk", None) or [RISK_LOW])
    trash_dir = Path(getattr(args, "trash_dir", None) or (Path.home() / ".Trash"))
    result["apply"] = apply_plan(result, risks=risks, trash_dir=trash_dir)
    return result


def _emit_root(root: dict[str, Any]) -> None:
    print(f"### {root['label']} — {_human_pair(root['size_bytes'], root['allocated_bytes'])}")
    print()
    print(f"- path: `{root['path']}`")
    print(f"- files: {root['files']}")
    if root["truncated"]:
        print("- note: scan hit the entry limit; sizes are incomplete")
    if root["skipped"]:
        print(f"- note: {root['skipped']} entries could not be read")
    for child in root["entries"][:8]:
        print(
            f"- `{child['name']}` — {_human_pair(child['size_bytes'], child['allocated_bytes'])} "
            f"({child['category']}, {child['risk']} risk)"
        )
    print()


def emit_markdown(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("# Disk scan")
    print()
    print(f"- home: `{result['scan']['home']}`")
    if result["scan"]["project"]:
        print(f"- project: `{result['scan']['project']}`")
    print(f"- generated: {result['scan']['generated_at']}")
    print()
    print("## Summary")
    print()
    print(f"- roots scanned: {summary['roots_scanned']}")
    print(f"- total: {_human_pair(summary['total_bytes'], summary['total_allocated_bytes'])}")
    print(f"- files: {summary['files']}")
    print(f"- low-risk candidates: {_human(summary['low_risk_bytes'])}")
    print(f"- medium-risk candidates: {_human(summary['medium_risk_bytes'])}")
    print(f"- high-risk candidates: {_human(summary['high_risk_bytes'])}")
    print()
    print("## Roots")
    print()
    for root in result["roots"]:
        _emit_root(root)
    print("## Largest files")
    print()
    if result["top_files"]:
        for item in result["top_files"]:
            print(
                f"- `{item['path']}` — {_human_pair(item['size_bytes'], item['allocated_bytes'])} "
                f"({item['category']}, {item['risk']} risk)"
            )
    else:
        print("- none above the threshold")
    print()
    print("## Suggested review")
    print()
    if result["reclaimable"]:
        for item in result["reclaimable"][:20]:
            print(
                f"- {_human_pair(item['size_bytes'], item['allocated_bytes'])} — {item['category']} / "
                f"{item['risk']} risk: `{item['path']}`"
            )
            print(f"  - {item['suggested_action']}")
    else:
        print("- none")
    if result.get("apply"):
        applied = result["apply"]
        print()
        print("## Applied")
        print()
        print(f"- status: {applied['status']}")
        print(f"- trash: `{applied['trash_dir']}`")
        print(f"- selected risks: {', '.join(applied['selected_risks'])}")
        print(f"- moved: {len(applied['moved'])}")
        print(f"- reclaimed (allocated): {_human(applied['reclaimed_allocated_bytes'])}")
        for item in applied["moved"]:
            print(f"  - `{item['path']}` -> `{item['trash_path']}`")
        for item in applied["skipped"]:
            print(f"  - skipped `{item['path']}`: {item['reason']}")
        for item in applied["failed"]:
            print(f"  - failed `{item['path']}`: {item['reason']}")
        print("- note: empty the trash to actually free the space")
    print()
    print("## Limitations")
    print()
    for limitation in result["limitations"]:
        print(f"- {limitation}")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--home", default=str(Path.home()), help="Home directory to audit.")
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Additional directory to audit; may be repeated.",
    )
    parser.add_argument("--project", help="Project directory to include in the audit.")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_FILES,
                        help="Largest files to report after sorting by allocated size (default 15).")
    parser.add_argument(
        "--min-file-mb",
        type=float,
        default=DEFAULT_MIN_FILE_MB,
        help="Report files whose allocated size is at or above this MB threshold (default 200).",
    )
    parser.add_argument("--max-entries", type=int, default=DEFAULT_MAX_ENTRIES,
                        help="Stop after this many filesystem entries (safety limit).")
    parser.add_argument("--apply", action="store_true",
                        help="Move selected reclaimable paths to the trash; requires --to-trash and --confirm.")
    parser.add_argument("--to-trash", action="store_true",
                        help="Move selected paths into the trash directory; permanent deletion is never used.")
    parser.add_argument("--confirm", action="store_true",
                        help="Explicit confirmation for --apply.")
    parser.add_argument("--risk", action="append", choices=CLEANUP_RISKS, default=[],
                        help="Cleanup risk to move (low or medium); may be repeated. Default: low.")
    parser.add_argument("--trash-dir", default=None,
                        help="Trash directory (default: ~/.Trash); mainly for tests and external volumes.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = parser.parse_args()
    try:
        result = run(args)
    except DiskScanError as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_markdown(result)


if __name__ == "__main__":
    main()
