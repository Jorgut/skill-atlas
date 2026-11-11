#!/usr/bin/env python3
"""Strictly read-only audit of project roots and duplicated project documentation.

The audit answers one narrow question: where do local project copies live, which
copies look like the same project, and do their agent-facing project documents
(AGENTS.md, CLAUDE.md, CONTEXT.md, PROJECT_STATE.md, ...) still agree?

It only reads directory entries, file metadata and documentation hashes. It
never runs ``git`` (``.git/config`` and ``.git/HEAD`` are parsed by hand), never
prints or stores document contents, opens no network connection, and never
writes, moves, merges, archives or deletes anything. Duplicate detection is a
heuristic and every recommendation is a plan that requires explicit user
confirmation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
MAX_HASH_BYTES = 256 * 1024
SHORT_HASH_LENGTH = 12
MAX_CONFIG_BYTES = 1024 * 1024

# Project documentation this audit compares. Directories are recorded but never
# hashed; only regular files at or below MAX_HASH_BYTES are hashed.
DOC_NAMES = (
    "AGENTS.md",
    "CLAUDE.md",
    "CONTEXT.md",
    "PROJECT_STATE.md",
    "PROJECT_INDEX.md",
    "CODEBUDDY.md",
    ".cursor/rules",
    ".agent/rules",
)

# Files and directories that make a directory a discovered project. At least
# two of these are required unless a .git entry is present.
DISCOVERY_MARKERS = (
    "AGENTS.md",
    "CLAUDE.md",
    "CONTEXT.md",
    "PROJECT_STATE.md",
    "PROJECT_INDEX.md",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    ".cursor/rules",
    ".codebuddy/CODEBUDDY.md",
)

# Project documents that carry the freshest project state, used only for
# git-remote duplicate groups when choosing a canonical candidate.
STATE_DOCS = ("PROJECT_STATE.md", "CONTEXT.md")

# Hidden directories are skipped wholesale during discovery; node_modules is
# skipped because it is a vendored dependency tree, not a project root.
SKIP_DIR_NAMES = frozenset({"node_modules", "__pycache__"})

GIT_DIR = ".git"

LIMITATIONS = (
    "Identity is a heuristic: a matching normalized git remote is stronger evidence than a matching directory name, and a shared directory name alone does not prove two paths are the same project.",
    "File hashes prove that two documents differ; they do not prove which copy is newer, better or authoritative.",
    "Discovery is depth-bounded, skips hidden directories and node_modules, and does not traverse directory symlinks, so deeper or linked project roots can be missed; pass --project or --root explicitly for those.",
    "git was not executed: .git/config and .git/HEAD were parsed by hand, so unusual, bare, submodule or partially written repositories may be reported incompletely.",
    "Only file metadata and documentation hashes were read; document contents were never printed, stored in the result, or compared semantically.",
    "Recommendations are plans only. The audit never moves, merges, archives, rewrites or deletes files, and every suggested action requires user confirmation.",
    "Files larger than 256 KiB are not hashed, so divergence in oversized documents is not detected.",
)

_GIT_HEADER = re.compile(r'^\[\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:"([^"]*)")?\s*\]$')
_SCP_REMOTE = re.compile(r"^(?:[^@/\s]+@)?([^:/\s]+):(?!//)(.+)$")
_URL_REMOTE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/]*@)?([^/]*)(.*)$")


# ---------------------------------------------------------------------------
# Small filesystem helpers. Every one of them degrades to a missing value on
# an OSError instead of raising: unreadable or vanishing paths must not stop
# the audit.
# ---------------------------------------------------------------------------


def _normalize(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        # Symlink loops raise RuntimeError; embedded null bytes raise
        # ValueError. Keep the unresolved path so the caller can report it.
        try:
            return path.expanduser()
        except (OSError, ValueError):
            return path


def _posix(path: Path) -> str:
    return path.as_posix()


def _safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except (OSError, ValueError):
        return False


def _safe_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except (OSError, ValueError):
        return False


def _safe_stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except (OSError, ValueError):
        return None


def _mtime(stat_result: os.stat_result) -> float:
    return round(float(stat_result.st_mtime), 6)


def _read_small_text(path: Path) -> str | None:
    """Read a small metadata file (never a project document) or return None."""
    stat_result = _safe_stat(path)
    if stat_result is None or stat.S_ISDIR(stat_result.st_mode):
        return None
    if stat_result.st_size > MAX_CONFIG_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError, ValueError):
        return None


def _hash_file(path: Path) -> str | None:
    """Return the SHA-256 of a regular file's bytes, or None if unreadable."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, ValueError):
        return None
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Marker and documentation records.
# ---------------------------------------------------------------------------


def _marker_entry(project: Path, name: str) -> dict[str, Any]:
    path = project / name
    entry: dict[str, Any] = {
        "name": name,
        "path": _posix(path),
        "exists": False,
        "size": None,
        "mtime": None,
    }
    stat_result = _safe_stat(path)
    if stat_result is None:
        return entry
    entry["exists"] = True
    entry["size"] = None if stat.S_ISDIR(stat_result.st_mode) else stat_result.st_size
    entry["mtime"] = _mtime(stat_result)
    return entry


def _doc_entry(project: Path, name: str) -> dict[str, Any]:
    path = project / name
    entry: dict[str, Any] = {
        "name": name,
        "path": _posix(path),
        "size": None,
        "mtime": None,
        "sha256": None,
        "too_large": False,
    }
    stat_result = _safe_stat(path)
    if stat_result is None:
        return entry
    entry["size"] = None if stat.S_ISDIR(stat_result.st_mode) else stat_result.st_size
    entry["mtime"] = _mtime(stat_result)
    if stat.S_ISDIR(stat_result.st_mode):
        return entry
    if stat_result.st_size > MAX_HASH_BYTES:
        entry["too_large"] = True
        return entry
    entry["sha256"] = _hash_file(path)
    return entry


# ---------------------------------------------------------------------------
# Manual .git parsing: config is INI-ish, HEAD is a single ref line. No git
# process is ever spawned.
# ---------------------------------------------------------------------------


def _strip_git_comment(line: str) -> str:
    """Drop a git config comment, keeping ``#``/``;`` inside quoted values."""
    in_quotes = False
    kept: list[str] = []
    for char in line:
        if char == '"':
            in_quotes = not in_quotes
        elif not in_quotes and char in "#;":
            break
        kept.append(char)
    return "".join(kept).strip()


def _strip_config_value(value: str) -> str:
    value = _strip_git_comment(value)
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return value


def _parse_git_section(line: str) -> tuple[str, str | None] | None:
    match = _GIT_HEADER.match(line)
    if match:
        return match.group(1).lower(), match.group(2)
    inner = line.strip().lstrip("[").rstrip("]").strip()
    if not inner:
        return None
    if "." in inner:
        section, _, subsection = inner.partition(".")
        return section.strip().lower(), subsection.strip() or None
    return inner.lower(), None


def _read_git_config(path: Path) -> list[tuple[str, str | None, dict[str, str]]]:
    """Parse an INI-ish git config into ordered (section, subsection, values)."""
    text = _read_small_text(path)
    if text is None:
        return []
    sections: list[tuple[str, str | None, dict[str, str]]] = []
    current: tuple[str, str | None, dict[str, str]] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("["):
            parsed = _parse_git_section(_strip_git_comment(line))
            current = None
            if parsed is not None:
                current = (parsed[0], parsed[1], {})
                sections.append(current)
            continue
        if current is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        if key:
            current[2][key] = _strip_config_value(value)
    return sections


def _remote_from_sections(
    sections: Iterable[tuple[str, str | None, dict[str, str]]],
) -> tuple[str | None, str | None]:
    remotes: dict[str, str] = {}
    for section, subsection, values in sections:
        if section != "remote" or not subsection:
            continue
        url = values.get("url", "").strip()
        if url:
            remotes.setdefault(subsection, url)
    if not remotes:
        return None, None
    if "origin" in remotes:
        return "origin", remotes["origin"]
    first = next(iter(remotes))
    return first, remotes[first]


def _core_bare(sections: Iterable[tuple[str, str | None, dict[str, str]]]) -> bool:
    for section, _subsection, values in sections:
        if section == "core":
            return values.get("bare", "").strip().lower() == "true"
    return False


def _read_head(git_dir: Path) -> str | None:
    text = _read_small_text(git_dir / "HEAD")
    if text is None:
        return None
    value = text.strip()
    if not value.lower().startswith("ref:"):
        # Detached HEAD carries a commit id, not a branch ref.
        return None
    ref = value.split(":", 1)[1].strip()
    return ref or None


def _gitdir_pointer(project: Path, dot_git: Path) -> Path | None:
    """Resolve a ``gitdir: <path>`` file used by linked worktrees and submodules."""
    text = _read_small_text(dot_git)
    if text is None:
        return None
    value = text.strip()
    if not value:
        return None
    if value.lower().startswith("gitdir:"):
        value = value.split(":", 1)[1].strip()
    if not value:
        return None
    target = Path(value).expanduser()
    if not target.is_absolute():
        target = project / target
    return _normalize(target)


def _common_dir(git_dir: Path) -> Path:
    text = _read_small_text(git_dir / "commondir")
    if text is None:
        return git_dir
    value = text.strip()
    if not value:
        return git_dir
    target = Path(value).expanduser()
    if not target.is_absolute():
        target = git_dir / target
    return _normalize(target)


def _git_info(project: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "is_repo": False,
        "remote_url": None,
        "remote_name": None,
        "head_ref": None,
        "worktree_or_bare": False,
    }
    dot_git = project / GIT_DIR
    if not _safe_exists(dot_git):
        return info
    info["is_repo"] = True

    git_dir = dot_git
    common_dir = dot_git
    if _safe_is_file(dot_git):
        # A .git file marks a linked worktree or submodule checkout; the real
        # git directory lives elsewhere and shares config with its common dir.
        info["worktree_or_bare"] = True
        resolved = _gitdir_pointer(project, dot_git)
        if resolved is None:
            return info
        git_dir = resolved
        common_dir = _common_dir(git_dir)
    sections = _read_git_config(common_dir / "config")
    if not info["worktree_or_bare"]:
        info["worktree_or_bare"] = _core_bare(sections)
    remote_name, remote_url = _remote_from_sections(sections)
    info["remote_name"] = remote_name
    info["remote_url"] = remote_url
    info["head_ref"] = _read_head(git_dir)
    return info


# ---------------------------------------------------------------------------
# Identity: normalized git remote first, directory name second.
# ---------------------------------------------------------------------------


def _strip_git_suffix(value: str) -> str:
    value = value.strip().strip('"').rstrip("/")
    if value.lower().endswith(".git"):
        value = value[:-4].rstrip("/")
    return value


def _finish_remote(host: str, path: str) -> str:
    cleaned = _strip_git_suffix(path.strip().lstrip("/"))
    return f"{host}/{cleaned}" if cleaned else host


def normalize_remote_url(url: str) -> str:
    """Normalize a git remote URL to ``host/path`` for identity comparison.

    ``https://github.com/acme/widgets.git``, ``git@github.com:acme/widgets.git``
    and ``ssh://git@github.com/acme/widgets`` all normalize to
    ``github.com/acme/widgets``. Local-path remotes are normalized only
    textually; relative paths are not resolved against the filesystem.
    """
    value = (url or "").strip().strip('"').strip()
    if not value:
        return ""
    if "://" in value:
        match = _URL_REMOTE.match(value)
        if match and match.group(1):
            return _finish_remote(match.group(1).lower(), match.group(2))
        return _strip_git_suffix(value)
    scp = _SCP_REMOTE.match(value)
    if scp and scp.group(1) and not scp.group(1).startswith("/"):
        return _finish_remote(scp.group(1).lower(), scp.group(2))
    return _strip_git_suffix(value)


def _identity(record: dict[str, Any]) -> tuple[str, str]:
    remote_url = record["git"]["remote_url"]
    if remote_url:
        # Host-based git hosts (GitHub, GitLab, ...) treat the owner/repository
        # path case-insensitively, so identity folding must too; the original
        # URL is still reported unchanged on the record.
        normalized = normalize_remote_url(remote_url).casefold()
        if normalized:
            return f"git-remote:{normalized}", "git-remote"
    return f"name:{record['name'].casefold()}", "directory-name"


# ---------------------------------------------------------------------------
# Discovery.
# ---------------------------------------------------------------------------


def _marker_presence(path: Path) -> list[dict[str, Any]]:
    return [_marker_entry(path, name) for name in DISCOVERY_MARKERS]


def _project_evidence(path: Path) -> tuple[bool, str, list[str]]:
    git_dir = path / GIT_DIR
    has_git = _safe_exists(git_dir)
    present = [marker["name"] for marker in _marker_presence(path) if marker["exists"]]
    is_project = bool(has_git or len(present) >= 2)
    if not is_project:
        return False, "", []
    evidence: list[str] = []
    if has_git:
        evidence.append(f"git:{GIT_DIR}")
    evidence.extend(f"marker:{name}" for name in present)
    return True, "git" if has_git else "marker", evidence


def _safe_scandir(directory: Path) -> list[os.DirEntry[str]] | None:
    try:
        with os.scandir(directory) as iterator:
            return sorted(iterator, key=lambda entry: entry.name)
    except OSError:
        return None


def _discover(
    root: Path,
    depth: int,
    selected: dict[str, dict[str, Any]],
    warnings: list[str],
) -> None:
    """Depth-bounded walk below one root; never follows directory symlinks."""
    visited: set[str] = set()
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        directory, level = stack.pop()
        key = _posix(directory)
        if key in visited:
            continue
        visited.add(key)
        if level >= depth:
            continue
        entries = _safe_scandir(directory)
        if entries is None:
            warnings.append(f"unreadable directory skipped: {key}")
            continue
        for entry in entries:
            name = entry.name
            if name.startswith(".") or name in SKIP_DIR_NAMES:
                continue
            try:
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
            except (OSError, ValueError):
                continue
            child = _normalize(Path(entry.path))
            child_key = _posix(child)
            if child_key in visited:
                continue
            is_project, discovered_by, evidence = _project_evidence(child)
            if is_project and child_key not in selected:
                selected[child_key] = {
                    "path": child,
                    "discovered_by": discovered_by,
                    "evidence": evidence,
                }
            stack.append((child, level + 1))


# ---------------------------------------------------------------------------
# Records.
# ---------------------------------------------------------------------------


def _project_record(selection: dict[str, Any]) -> dict[str, Any]:
    path: Path = selection["path"]
    markers = _marker_presence(path)
    present = [marker["name"] for marker in markers if marker["exists"]]
    git = _git_info(path)
    evidence = list(selection["evidence"])
    if git["is_repo"] and f"git:{GIT_DIR}" not in evidence:
        evidence.append(f"git:{GIT_DIR}")
    for name in present:
        token = f"marker:{name}"
        if token not in evidence:
            evidence.append(token)
    return {
        "path": _posix(path),
        "name": path.name or _posix(path),
        "git": git,
        "markers": markers,
        "docs": [_doc_entry(path, name) for name in DOC_NAMES],
        "discovered_by": selection["discovered_by"],
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# Duplicate groups and per-group comparison.
# ---------------------------------------------------------------------------


def _doc_instances(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for doc in record["docs"]:
            if doc["sha256"] is None:
                continue
            by_name.setdefault(doc["name"], []).append(doc)
    for instances in by_name.values():
        instances.sort(key=lambda doc: doc["path"])
    return by_name


def _divergent_docs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    divergent: list[dict[str, Any]] = []
    instances_by_name = _doc_instances(records)
    for name in sorted(instances_by_name):
        instances = instances_by_name[name]
        hashes = {doc["sha256"] for doc in instances}
        if len(instances) < 2 or len(hashes) < 2:
            continue
        divergent.append(
            {
                "name": name,
                "distinct_hashes": len(hashes),
                "variants": [
                    {
                        "path": doc["path"],
                        "size": doc["size"],
                        "mtime": doc["mtime"],
                        "sha256": doc["sha256"][:SHORT_HASH_LENGTH],
                    }
                    for doc in instances
                ],
            }
        )
    return divergent


def _shared_identical_docs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shared: list[dict[str, Any]] = []
    instances_by_name = _doc_instances(records)
    for name in sorted(instances_by_name):
        instances = instances_by_name[name]
        hashes = {doc["sha256"] for doc in instances}
        if len(instances) < 2 or len(hashes) != 1:
            continue
        shared.append(
            {
                "name": name,
                "sha256": instances[0]["sha256"][:SHORT_HASH_LENGTH],
                "paths": [doc["path"] for doc in instances],
            }
        )
    return shared


def _duplicate_groups(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for record in records:
        identity, evidence = _identity(record)
        bucket = buckets.setdefault(
            identity,
            {
                "identity": identity,
                "evidence": evidence,
                "records": [],
            },
        )
        bucket["records"].append(record)

    groups: list[dict[str, Any]] = []
    for identity in sorted(buckets):
        bucket = buckets[identity]
        if len(bucket["records"]) < 2:
            continue
        ordered = sorted(bucket["records"], key=lambda record: record["path"])
        groups.append(
            {
                "identity": identity,
                "evidence": bucket["evidence"],
                "paths": [record["path"] for record in ordered],
                "divergent_docs": _divergent_docs(ordered),
                "shared_identical_docs": _shared_identical_docs(ordered),
            }
        )
    return groups


def _nested_pairs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = [Path(record["path"]) for record in records]
    pairs: list[dict[str, Any]] = []
    for outer in paths:
        for inner in paths:
            if outer == inner:
                continue
            try:
                inner.relative_to(outer)
            except ValueError:
                continue
            pairs.append({"outer": _posix(outer), "inner": _posix(inner)})
    pairs.sort(key=lambda pair: (pair["outer"], pair["inner"]))
    return pairs


# ---------------------------------------------------------------------------
# Plan-only recommendations.
# ---------------------------------------------------------------------------


def _state_mtime(record: dict[str, Any]) -> float | None:
    values = [
        doc["mtime"]
        for doc in record["docs"]
        if doc["name"] in STATE_DOCS and doc["mtime"] is not None
    ]
    return max(values) if values else None


def _doc_count(record: dict[str, Any]) -> int:
    return sum(1 for doc in record["docs"] if doc["mtime"] is not None)


def _canonical_candidate(
    records: list[dict[str, Any]], evidence: str
) -> dict[str, Any]:
    """Deterministic canonical choice; freshness is only trusted for git groups."""
    if evidence == "git-remote":

        def key(record: dict[str, Any]) -> tuple[Any, ...]:
            mtime = _state_mtime(record)
            return (
                mtime is None,
                -(mtime or 0.0),
                -_doc_count(record),
                len(record["path"]),
                record["path"],
            )

    else:

        def key(record: dict[str, Any]) -> tuple[Any, ...]:
            return (
                -_doc_count(record),
                len(record["path"]),
                record["path"],
            )

    return min(records, key=key)


def _recommendation(
    group: dict[str, Any], records_by_path: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    group_records = [records_by_path[path] for path in group["paths"]]
    canonical = _canonical_candidate(group_records, group["evidence"])
    actions = [f"keep `{canonical['path']}` as the canonical candidate"]
    for divergent in group["divergent_docs"]:
        actions.append(
            f"review divergent {divergent['name']} across {len(divergent['variants'])} copies"
        )
    if len(group["paths"]) > 1:
        duplicates = len(group["paths"]) - 1
        noun = "copy" if duplicates == 1 else "copies"
        actions.append(
            f"archive the {duplicates} duplicate {noun} only after user confirmation"
        )
    actions.append("do not move, merge, delete or rewrite files automatically")
    return {
        "identity": group["identity"],
        "evidence": group["evidence"],
        "canonical_candidate": canonical["path"],
        "suggested_actions": actions,
        "requires_user_confirmation": True,
    }


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


def _as_paths(value: Any) -> list[Path]:
    if value is None:
        return []
    if isinstance(value, (str, os.PathLike)):
        return [Path(value)]
    return [Path(item) for item in value]


def _normalize_depth(depth: Any) -> int:
    try:
        return max(0, int(depth))
    except (TypeError, ValueError):
        return 2


def audit(
    projects: list[Path],
    roots: list[Path],
    depth: int = 2,
) -> dict[str, Any]:
    """Return a read-only audit of explicit projects plus roots discovered below.

    ``projects`` are always audited, whether or not they contain project
    markers. ``roots`` are walked at most ``depth`` levels below each root.
    Paths are normalized with ``resolve(strict=False)`` and the function only
    reads metadata, small git metadata files and document hashes.
    """
    depth = _normalize_depth(depth)
    explicit = [_normalize(Path(path)) for path in _as_paths(projects)]
    scanned_roots = [_normalize(Path(root)) for root in _as_paths(roots)]
    warnings: list[str] = []
    selected: dict[str, dict[str, Any]] = {}

    for path in explicit:
        key = _posix(path)
        if not _safe_is_dir(path):
            warnings.append(f"explicit project is not a directory: {key}")
        selected[key] = {
            "path": path,
            "discovered_by": "explicit",
            "evidence": ["explicit"],
        }

    for root in scanned_roots:
        if not _safe_is_dir(root):
            warnings.append(f"root is not a directory: {_posix(root)}")
            continue
        _discover(root, depth, selected, warnings)

    records = [
        _project_record(selected[key]) for key in sorted(selected)
    ]
    groups = _duplicate_groups(records)
    records_by_path = {record["path"]: record for record in records}
    recommendations = [
        _recommendation(group, records_by_path) for group in groups
    ]
    nested = _nested_pairs(records)

    return {
        "schema_version": SCHEMA_VERSION,
        "audit": {
            "roots": [_posix(root) for root in scanned_roots],
            "explicit_projects": [_posix(path) for path in explicit],
            "depth": depth,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "warnings": sorted(set(warnings)),
        },
        "projects": records,
        "duplicate_groups": groups,
        "nested_pairs": nested,
        "recommendations": recommendations,
        "summary": {
            "projects": len(records),
            "duplicate_groups": len(groups),
            "divergent_docs": sum(
                len(group["divergent_docs"]) for group in groups
            ),
            "nested_pairs": len(nested),
            "roots_scanned": len(scanned_roots),
        },
        "limitations": list(LIMITATIONS),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    return audit(
        _as_paths(getattr(args, "project", None)),
        _as_paths(getattr(args, "root", None)),
        getattr(args, "depth", 2),
    )


# ---------------------------------------------------------------------------
# Rendering.
# ---------------------------------------------------------------------------


def _emit_project_markdown(project: dict[str, Any]) -> None:
    git = project["git"]
    print(f"### `{project['path']}`")
    print()
    print(f"- name: {project['name']}")
    print(f"- discovered by: {project['discovered_by']}")
    if git["is_repo"]:
        remote = (
            f"`{git['remote_name']}` = `{git['remote_url']}`"
            if git["remote_url"]
            else "no remote URL in .git/config"
        )
        print(f"- git: {remote}")
        print(f"- HEAD: {git['head_ref'] or 'detached or unreadable'}")
        print(f"- worktree or bare: {str(git['worktree_or_bare']).lower()}")
    else:
        print("- git: no .git entry")
    present = [marker["name"] for marker in project["markers"] if marker["exists"]]
    print(f"- markers present: {', '.join(present) if present else 'none'}")
    hashed = [
        f"{doc['name']} ({doc['sha256'][:SHORT_HASH_LENGTH]})"
        for doc in project["docs"]
        if doc["sha256"] is not None
    ]
    print(f"- docs hashed: {', '.join(hashed) if hashed else 'none'}")
    oversized = [doc["name"] for doc in project["docs"] if doc["too_large"]]
    if oversized:
        print(f"- docs not hashed (over 256 KiB): {', '.join(oversized)}")
    print()


def _emit_group_markdown(group: dict[str, Any]) -> None:
    print(f"### `{group['identity']}` ({group['evidence']})")
    print()
    for path in group["paths"]:
        print(f"- `{path}`")
    if group["divergent_docs"]:
        print("- divergent docs:")
        for divergent in group["divergent_docs"]:
            print(f"  - {divergent['name']} ({divergent['distinct_hashes']} distinct hashes)")
            for variant in divergent["variants"]:
                print(
                    f"    - `{variant['path']}` size={variant['size']} "
                    f"mtime={variant['mtime']} sha256={variant['sha256']}"
                )
    else:
        print("- divergent docs: none")
    if group["shared_identical_docs"]:
        shared = ", ".join(
            f"{item['name']} ({item['sha256']})"
            for item in group["shared_identical_docs"]
        )
        print(f"- identical docs: {shared}")
    else:
        print("- identical docs: none")
    print()


def emit_markdown(result: dict[str, Any]) -> None:
    audit_info = result["audit"]
    summary = result["summary"]
    print("# Skill Atlas Project Root Audit")
    print()
    if audit_info["roots"]:
        print(f"- roots scanned: {', '.join(f'`{root}`' for root in audit_info['roots'])}")
    else:
        print("- roots scanned: none")
    if audit_info["explicit_projects"]:
        print(
            "- explicit projects: "
            + ", ".join(f"`{path}`" for path in audit_info["explicit_projects"])
        )
    else:
        print("- explicit projects: none")
    print(f"- discovery depth: {audit_info['depth']}")
    print(f"- generated: {audit_info['generated_at']}")
    print()
    print("## Summary")
    print()
    print(f"- projects: {summary['projects']}")
    print(f"- duplicate groups: {summary['duplicate_groups']}")
    print(f"- divergent docs: {summary['divergent_docs']}")
    print(f"- nested project pairs: {summary['nested_pairs']}")
    print(f"- roots scanned: {summary['roots_scanned']}")
    print()
    print("## Projects")
    print()
    if result["projects"]:
        for project in result["projects"]:
            _emit_project_markdown(project)
    else:
        print("- none")
        print()
    print("## Duplicate groups")
    print()
    if result["duplicate_groups"]:
        for group in result["duplicate_groups"]:
            _emit_group_markdown(group)
    else:
        print("- none")
        print()
    print("## Nested project pairs")
    print()
    if result["nested_pairs"]:
        for pair in result["nested_pairs"]:
            print(f"- `{pair['outer']}` contains `{pair['inner']}`")
    else:
        print("- none")
    print()
    print("## Recommendations")
    print()
    if result["recommendations"]:
        for recommendation in result["recommendations"]:
            print(f"### `{recommendation['identity']}`")
            print()
            print(f"- canonical candidate: `{recommendation['canonical_candidate']}`")
            print(
                "- requires user confirmation: "
                f"{str(recommendation['requires_user_confirmation']).lower()}"
            )
            print("- suggested actions:")
            for action in recommendation["suggested_actions"]:
                print(f"  - {action}")
            print()
    else:
        print("- none")
        print()
    if audit_info["warnings"]:
        print("## Warnings")
        print()
        for warning in audit_info["warnings"]:
            print(f"- {warning}")
        print()
    print("## Limitations")
    print()
    for limitation in result["limitations"]:
        print(f"- {limitation}")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Project directory to audit as a project even without markers. May be repeated.",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help=(
            "Directory whose descendants are searched for project roots; the root "
            "itself is not reported, use --project for it. May be repeated."
        ),
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Maximum discovery depth below each root; direct children are depth 1 (default: 2).",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")


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
