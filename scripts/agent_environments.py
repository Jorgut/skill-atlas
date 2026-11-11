#!/usr/bin/env python3
"""Read-only discovery of locally installed coding-agent environments.

The scan answers a narrow question: which coding-agent tools leave evidence on
this machine, which rule and skill roots does each tool's documentation or
convention point at, and do the local Skill Atlas copies agree on a version?

It only reads filesystem metadata and, for a local Skill Atlas copy, that
copy's ``skill.json`` manifest. It never launches or executes an agent tool,
opens a network connection, reads credentials or session data, and never
writes, links or deletes anything. Evidence stops at ``configured``: file
presence is not runtime loading, and candidate paths are never upgraded to
documented evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DOCUMENTED = "documented"
CANDIDATE = "candidate"
SKILL_ATLAS = "skill-atlas"

LEVEL_NOT_DETECTED = "not-detected"
LEVEL_DETECTED = "detected"
LEVEL_CONFIGURED = "configured"


@dataclass(frozen=True)
class PathSpec:
    """One discoverable path, its evidence level and an optional home override.

    ``relative`` is resolved against the scanned home directory. When
    ``env_var`` is set and non-empty in the supplied environment, the variable
    replaces the home-relative prefix and ``env_suffix`` is appended instead.
    """

    relative: str
    evidence: str = CANDIDATE
    env_var: str | None = None
    env_suffix: str = ""


@dataclass(frozen=True)
class ToolSpec:
    """Static, reviewable description of one coding-agent tool."""

    id: str
    name: str
    executables: tuple[str, ...]
    home_env_vars: tuple[str, ...]
    roots: tuple[PathSpec, ...]
    instruction_entries: tuple[PathSpec, ...]
    project_rules: tuple[PathSpec, ...]
    skill_roots: tuple[PathSpec, ...]


def _documented(relative: str, env_var: str | None = None, env_suffix: str = "") -> PathSpec:
    return PathSpec(relative, DOCUMENTED, env_var, env_suffix)


def _candidate(relative: str, env_var: str | None = None, env_suffix: str = "") -> PathSpec:
    return PathSpec(relative, CANDIDATE, env_var, env_suffix)


# Only entries explicitly described in this repository's docs are marked
# ``documented``: docs/cross-agent-collaboration.md (Codex, Claude Code,
# OpenCode, DeepSeek Harness, WorkBuddy, Kimi Code), docs/kimi-code.md (Kimi
# Code) and docs/external-search.md (no local tool paths). Everything else,
# including paths that merely look conventional, stays ``candidate``.
CATALOG: tuple[ToolSpec, ...] = (
    ToolSpec(
        id="codex",
        name="Codex",
        executables=("codex",),
        home_env_vars=("CODEX_HOME",),
        roots=(_candidate(".codex", "CODEX_HOME"),),
        instruction_entries=(_documented(".codex/AGENTS.md", "CODEX_HOME", "AGENTS.md"),),
        project_rules=(_documented("AGENTS.md"),),
        skill_roots=(
            _candidate(".codex/skills", "CODEX_HOME", "skills"),
            _candidate(".agents/skills"),
        ),
    ),
    ToolSpec(
        id="claude-code",
        name="Claude Code",
        executables=("claude",),
        home_env_vars=("CLAUDE_CONFIG_DIR",),
        roots=(_candidate(".claude", "CLAUDE_CONFIG_DIR"),),
        instruction_entries=(_documented(".claude/CLAUDE.md", "CLAUDE_CONFIG_DIR", "CLAUDE.md"),),
        project_rules=(_documented("CLAUDE.md"), _candidate(".claude/CLAUDE.md")),
        skill_roots=(_candidate(".claude/skills", "CLAUDE_CONFIG_DIR", "skills"),),
    ),
    ToolSpec(
        id="opencode",
        name="OpenCode",
        executables=("opencode",),
        home_env_vars=("OPENCODE_CONFIG_DIR",),
        roots=(_candidate(".config/opencode", "OPENCODE_CONFIG_DIR"),),
        instruction_entries=(
            _documented(".config/opencode/AGENTS.md", "OPENCODE_CONFIG_DIR", "AGENTS.md"),
        ),
        project_rules=(_documented("AGENTS.md"),),
        skill_roots=(
            _candidate(".config/opencode/skills", "OPENCODE_CONFIG_DIR", "skills"),
        ),
    ),
    ToolSpec(
        id="deepseek-harness",
        name="DeepSeek Harness",
        executables=("dsh",),
        home_env_vars=("DSH_HOME",),
        roots=(_candidate(".dsh", "DSH_HOME"),),
        instruction_entries=(_documented(".dsh/AGENTS.md", "DSH_HOME", "AGENTS.md"),),
        project_rules=(_documented("AGENTS.md"),),
        skill_roots=(_candidate(".dsh/skills", "DSH_HOME", "skills"), _candidate(".agents/skills")),
    ),
    ToolSpec(
        id="workbuddy",
        name="WorkBuddy",
        executables=("workbuddy",),
        home_env_vars=("WORKBUDDY_HOME",),
        roots=(_candidate(".workbuddy", "WORKBUDDY_HOME"),),
        instruction_entries=(_documented(".workbuddy/rules", "WORKBUDDY_HOME", "rules"),),
        project_rules=(
            _documented("CODEBUDDY.md"),
            _documented(".codebuddy/CODEBUDDY.md"),
            _documented("AGENTS.md"),
        ),
        skill_roots=(_candidate(".workbuddy/skills", "WORKBUDDY_HOME", "skills"),),
    ),
    ToolSpec(
        id="kimi-code",
        name="Kimi Code CLI",
        executables=("kimi", "kimi-code"),
        home_env_vars=("KIMI_CODE_HOME",),
        roots=(_candidate(".kimi-code", "KIMI_CODE_HOME"),),
        instruction_entries=(
            _documented(".kimi-code/AGENTS.md", "KIMI_CODE_HOME", "AGENTS.md"),
            _documented(".agents/AGENTS.md"),
        ),
        project_rules=(_documented("AGENTS.md"), _documented(".kimi-code/AGENTS.md")),
        skill_roots=(
            _documented(".agents/skills"),
            _documented(".kimi-code/skills", "KIMI_CODE_HOME", "skills"),
        ),
    ),
    ToolSpec(
        id="cursor",
        name="Cursor",
        executables=("cursor",),
        home_env_vars=(),
        roots=(_candidate(".cursor"),),
        instruction_entries=(_candidate(".cursor/rules"),),
        project_rules=(_candidate(".cursor/rules"), _candidate(".cursorrules")),
        skill_roots=(_candidate(".cursor/skills"),),
    ),
    ToolSpec(
        id="trae",
        name="Trae",
        executables=("trae",),
        home_env_vars=(),
        roots=(_candidate(".trae"),),
        instruction_entries=(_candidate(".trae/rules"),),
        project_rules=(_candidate(".trae/rules"), _candidate("AGENTS.md")),
        skill_roots=(_candidate(".trae/skills"),),
    ),
    ToolSpec(
        id="qoder",
        name="Qoder",
        executables=("qoder",),
        home_env_vars=(),
        roots=(_candidate(".qoder"),),
        instruction_entries=(_candidate(".qoder/AGENTS.md"),),
        project_rules=(_candidate(".qoder/rules"), _candidate("AGENTS.md")),
        skill_roots=(_candidate(".qoder/skills"),),
    ),
    ToolSpec(
        id="gemini-cli",
        name="Gemini CLI",
        executables=("gemini",),
        home_env_vars=(),
        roots=(_candidate(".gemini"),),
        instruction_entries=(_candidate(".gemini/GEMINI.md"),),
        project_rules=(_candidate("GEMINI.md"),),
        skill_roots=(_candidate(".gemini/skills"),),
    ),
    ToolSpec(
        id="copilot-cli",
        name="Copilot CLI",
        executables=("copilot",),
        home_env_vars=(),
        roots=(_candidate(".copilot"),),
        instruction_entries=(_candidate(".copilot/copilot-instructions.md"),),
        project_rules=(_candidate(".github/copilot-instructions.md"),),
        skill_roots=(_candidate(".copilot/skills"),),
    ),
    ToolSpec(
        id="codebuddy",
        name="CodeBuddy",
        executables=("codebuddy",),
        home_env_vars=(),
        roots=(_candidate(".codebuddy"),),
        instruction_entries=(_candidate(".codebuddy/CODEBUDDY.md"),),
        project_rules=(_candidate("CODEBUDDY.md"), _candidate(".codebuddy/CODEBUDDY.md")),
        skill_roots=(_candidate(".codebuddy/skills"),),
    ),
    ToolSpec(
        id="antigravity",
        name="Antigravity",
        executables=("antigravity",),
        home_env_vars=(),
        roots=(_candidate(".antigravity"),),
        instruction_entries=(_candidate(".antigravity/rules"),),
        project_rules=(_candidate(".agent/rules"),),
        skill_roots=(_candidate(".antigravity/skills"),),
    ),
    ToolSpec(
        id="cline",
        name="Cline",
        executables=("cline",),
        home_env_vars=(),
        roots=(_candidate(".cline"),),
        instruction_entries=(_candidate(".cline/rules"),),
        project_rules=(_candidate(".clinerules"),),
        skill_roots=(_candidate(".cline/skills"),),
    ),
)

LIMITATIONS = (
    "Runtime loading was not verified: existing files and directories do not prove any tool loaded them.",
    "Agent tool versions were not read and no agent tool was executed; a PATH hit only proves an executable file exists.",
    "Candidate paths and home environment-variable overrides are unverified discovery hints and may be version-specific or outdated.",
    "No network connection was opened, no credentials or session data were read, and no files or links were created or modified.",
    "Configured means documented configuration evidence exists; loaded and handoff-verified claims remain out of scope.",
    "Project rule candidates are project-scoped hints; their presence does not prove a tool is installed or active.",
)


def _normalize(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError:
        return path.expanduser()


def _posix(path: Path) -> str:
    return path.as_posix()


def _safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _safe_is_symlink(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError:
        return False


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _expand(spec: PathSpec, home: Path, environ: dict[str, str]) -> Path:
    env_value = environ.get(spec.env_var, "") if spec.env_var else ""
    if env_value:
        base = _normalize(Path(env_value))
        return base / spec.env_suffix if spec.env_suffix else base
    return home / spec.relative


def _readable(path: Path) -> bool:
    try:
        if _safe_is_dir(path):
            return os.access(path, os.R_OK | os.X_OK)
        return os.access(path, os.R_OK)
    except OSError:
        return False


def _root_entry(path: Path) -> dict[str, Any]:
    exists = _safe_exists(path)
    is_symlink = _safe_is_symlink(path)
    return {
        "path": _posix(path),
        "exists": exists,
        "is_symlink": is_symlink,
        "broken": bool(is_symlink and not exists),
        "readable": bool(exists and _readable(path)),
    }


def _skill_count(path: Path) -> int | None:
    """Count visible child directories, which is how skill roots are laid out."""
    if not _safe_is_dir(path):
        return None
    try:
        entries = list(os.scandir(path))
    except OSError:
        return None
    count = 0
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir(follow_symlinks=True):
                count += 1
        except OSError:
            continue
    return count


def _skill_entry(path: Path) -> dict[str, Any]:
    exists = _safe_exists(path)
    return {
        "path": _posix(path),
        "exists": exists,
        "is_symlink": _safe_is_symlink(path),
        "skill_count": _skill_count(path) if exists else None,
    }


def _instruction_entry(path: Path, evidence: str) -> dict[str, Any]:
    return {"path": _posix(path), "exists": _safe_exists(path), "evidence": evidence}


def _project_entry(project: Path, spec: PathSpec) -> dict[str, Any]:
    path = project / spec.relative
    return {"path": _posix(path), "exists": _safe_exists(path)}


def _executables(spec: ToolSpec, environ: dict[str, str]) -> list[dict[str, Any]]:
    # Never fall back to the real process PATH: callers must supply discovery scope.
    search_path = environ.get("PATH", "")
    entries: list[dict[str, Any]] = []
    for name in spec.executables:
        found = shutil.which(name, path=search_path) if search_path else None
        entries.append({"name": name, "path": found, "found": bool(found)})
    return entries


def _documented_evidence_present(
    instruction_entries: list[dict[str, Any]],
    skill_entries: list[dict[str, Any]],
    skill_specs: tuple[PathSpec, ...],
    detected: bool,
) -> bool:
    """Configured requires documented, tool-specific evidence.

    A documented instruction entry is enough. A documented skill root only
    counts when the tool itself is otherwise detected, so a shared
    ``~/.agents/skills`` does not make every tool that lists it configured.
    """
    if any(item["exists"] and item["evidence"] == DOCUMENTED for item in instruction_entries):
        return True
    if not detected:
        return False
    return any(
        item["exists"]
        and (item["skill_count"] or 0) > 0
        and spec.evidence == DOCUMENTED
        for item, spec in zip(skill_entries, skill_specs)
    )


def _tool_notes(
    root_entries: list[dict[str, Any]],
    skill_entries: list[dict[str, Any]],
    instruction_entries: list[dict[str, Any]],
    executables: list[dict[str, Any]],
    level: str,
) -> list[str]:
    notes: list[str] = []
    for executable in executables:
        if executable["found"]:
            notes.append(
                f"executable '{executable['name']}' found at {executable['path']}; it was not executed"
            )
    for root in root_entries:
        if root["broken"]:
            notes.append(f"broken symlink: {root['path']}")
        elif root["exists"] and not root["readable"]:
            notes.append(f"unreadable directory: {root['path']}")
    for skill in skill_entries:
        if skill["is_symlink"] and not skill["exists"]:
            notes.append(f"broken symlink: {skill['path']}")
        elif skill["exists"] and skill["skill_count"] is None:
            notes.append(f"skill root could not be listed: {skill['path']}")
    if level == LEVEL_CONFIGURED:
        notes.append("documented configuration evidence present; runtime loading was not verified")
    elif level == LEVEL_DETECTED:
        notes.append("local evidence only; candidate paths and runtime loading are unverified")
    if any(
        item["exists"] and item["evidence"] == CANDIDATE for item in instruction_entries
    ):
        notes.append("candidate rule paths are unverified discovery hints")
    if not any(item["exists"] for item in root_entries) and any(
        item["exists"] for item in skill_entries
    ):
        notes.append("only shared or tool-specific skill roots were found; no tool root evidence")
    return sorted(set(notes))


def _scan_tool(
    spec: ToolSpec,
    home: Path,
    environ: dict[str, str],
    project: Path | None,
    shared_paths: set[str] | None = None,
) -> dict[str, Any]:
    shared_paths = shared_paths or set()
    roots = [_root_entry(_expand(item, home, environ)) for item in spec.roots]
    instruction_entries = [
        _instruction_entry(_expand(item, home, environ), item.evidence)
        for item in spec.instruction_entries
    ]
    skill_roots = [_skill_entry(_expand(item, home, environ)) for item in spec.skill_roots]
    project_rules = (
        [_project_entry(project, item) for item in spec.project_rules] if project else []
    )
    executables = _executables(spec, environ)

    tool_specific = any(item["exists"] for item in roots) or any(
        item["found"] for item in executables
    )
    specific_skills = [
        item
        for item in skill_roots
        if item["exists"]
        and _posix(_normalize(Path(item["path"]))) not in shared_paths
    ]
    detected = bool(tool_specific or specific_skills or any(item["exists"] for item in instruction_entries))
    evidence_paths = sorted(
        {
            item["path"]
            for item in roots + instruction_entries + specific_skills
            if item["exists"]
        }
    )
    configured = _documented_evidence_present(
        instruction_entries, skill_roots, spec.skill_roots, detected
    )
    level = LEVEL_CONFIGURED if configured else LEVEL_DETECTED if detected else LEVEL_NOT_DETECTED

    return {
        "id": spec.id,
        "name": spec.name,
        "evidence_paths": evidence_paths,
        "detected": detected,
        "executables": executables,
        "roots": roots,
        "instruction_entries": instruction_entries,
        "project_rules": project_rules,
        "skill_roots": skill_roots,
        "level": level,
        "notes": _tool_notes(roots, skill_roots, instruction_entries, executables, level),
    }


def _shared_skill_roots(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, set[str]] = {}
    for tool in tools:
        for skill in tool["skill_roots"]:
            if not skill["exists"]:
                continue
            try:
                real = Path(skill["path"]).resolve(strict=False)
            except OSError:
                continue
            groups.setdefault(_posix(real), set()).add(tool["id"])
    return [
        {"path": path, "tools": sorted(ids)}
        for path, ids in sorted(groups.items())
        if len(ids) > 1
    ]


def _read_manifest(copy_dir: Path) -> tuple[str | None, bool]:
    """Return (version, readable) from a readable ``skill.json`` only."""
    manifest = copy_dir / "skill.json"
    try:
        raw = manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, False
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, True
    version = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not version.strip():
        return None, True
    return version.strip(), True


# Skill roots that are not owned by one tool but commonly hold the installed
# Skill Atlas copy (CC Switch manages several agent skill roots).
EXTRA_COPY_ROOTS = (_candidate(".cc-switch/skills"),)


def _copy_roots() -> tuple[PathSpec, ...]:
    roots: list[PathSpec] = list(EXTRA_COPY_ROOTS)
    for spec in CATALOG:
        roots.extend(spec.skill_roots)
    return tuple(roots)


def _skill_atlas_copies(home: Path, environ: dict[str, str]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for path_spec in _copy_roots():
        root = _expand(path_spec, home, environ)
        copy_dir = root / SKILL_ATLAS
        if not (_safe_exists(copy_dir) or _safe_is_symlink(copy_dir)):
            continue
        physical = _posix(_normalize(copy_dir))
        group = groups.setdefault(
            physical, {"path": _posix(copy_dir), "aliases": set(), "is_symlink": False}
        )
        group["aliases"].add(_posix(copy_dir))
        group["is_symlink"] = group["is_symlink"] or _safe_is_symlink(copy_dir)
    copies: list[dict[str, Any]] = []
    for physical in sorted(groups):
        group = groups[physical]
        version, readable = _read_manifest(Path(physical))
        copies.append(
            {
                "path": group["path"],
                "aliases": sorted(group["aliases"]),
                "is_symlink": group["is_symlink"],
                "target": physical if group["is_symlink"] else None,
                "version": version,
                "readable": readable,
            }
        )
    return copies


def scan(home: Path, environ: dict[str, str], project: Path | None = None) -> dict[str, Any]:
    """Return a read-only snapshot of local coding-agent tool evidence.

    ``home`` and ``project`` are normalized with ``resolve(strict=False)``.
    ``environ`` is the only source of ``PATH`` and home-override variables, so
    tests and callers control discovery scope explicitly.
    """
    home = _normalize(Path(home))
    project = _normalize(Path(project)) if project is not None else None
    preliminary = [_scan_tool(spec, home, environ, project) for spec in CATALOG]
    shared = _shared_skill_roots(preliminary)
    shared_paths = {
        _posix(_normalize(Path(item["path"]))) for item in shared
    }
    tools = [
        _scan_tool(spec, home, environ, project, shared_paths) for spec in CATALOG
    ]
    copies = _skill_atlas_copies(home, environ)
    versions = sorted({copy["version"] for copy in copies if copy["version"]})
    return {
        "schema_version": SCHEMA_VERSION,
        "scan": {
            "home": _posix(home),
            "project": _posix(project) if project is not None else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "tools": tools,
        "shared_skill_roots": shared,
        "skill_atlas_copies": copies,
        "summary": {
            "tools_detected": sum(item["detected"] for item in tools),
            "tools_configured": sum(item["level"] == LEVEL_CONFIGURED for item in tools),
            "skill_atlas_copies": len(copies),
            "version_mismatch": len(versions) > 1,
        },
        "limitations": list(LIMITATIONS),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    project_value = getattr(args, "project", None)
    return scan(
        Path(args.home),
        dict(os.environ),
        Path(project_value) if project_value else None,
    )


def _emit_evidence_markdown(tool: dict[str, Any]) -> None:
    printed = False
    for executable in tool["executables"]:
        if executable["found"]:
            print(f"- executable: `{executable['name']}` at `{executable['path']}` (not executed)")
            printed = True
    for root in tool["roots"]:
        if root["exists"]:
            state = "unreadable" if not root["readable"] else "readable"
            print(f"- home root: `{root['path']}` ({state})")
            printed = True
        elif root["broken"]:
            print(f"- home root: `{root['path']}` (broken symlink)")
            printed = True
    for entry in tool["instruction_entries"]:
        if entry["exists"]:
            print(f"- rule entry ({entry['evidence']}): `{entry['path']}`")
            printed = True
    for skill in tool["skill_roots"]:
        if skill["exists"]:
            label = "symlink" if skill["is_symlink"] else "root"
            print(f"- skill root ({label}): `{skill['path']}` ({skill['skill_count']} skills)")
            printed = True
    for rule in tool["project_rules"]:
        if rule["exists"]:
            print(f"- project rule: `{rule['path']}`")
            printed = True
    for note in tool["notes"]:
        print(f"- note: {note}")
    if not printed and not tool["notes"]:
        print("- no local evidence found")


def emit_markdown(result: dict[str, Any]) -> None:
    scan_info = result["scan"]
    summary = result["summary"]
    print("# Skill Atlas Agent Environment Scan")
    print()
    print(f"- home: `{scan_info['home']}`")
    if scan_info["project"]:
        print(f"- project: `{scan_info['project']}`")
    else:
        print("- project: not scanned")
    print(f"- generated: {scan_info['generated_at']}")
    print()
    print("## Summary")
    print()
    print(f"- tools detected: {summary['tools_detected']}")
    print(f"- tools configured: {summary['tools_configured']}")
    print(f"- skill atlas copies: {summary['skill_atlas_copies']}")
    print(f"- version mismatch: {str(summary['version_mismatch']).lower()}")
    print()
    print("## Tools")
    for tool in result["tools"]:
        print()
        print(f"### {tool['name']} (`{tool['id']}`): {tool['level']}")
        _emit_evidence_markdown(tool)
    print()
    print("## Shared skill roots")
    print()
    if result["shared_skill_roots"]:
        for shared in result["shared_skill_roots"]:
            print(f"- `{shared['path']}`: {', '.join(shared['tools'])}")
    else:
        print("- none")
    print()
    print("## Skill Atlas copies")
    print()
    if result["skill_atlas_copies"]:
        for copy in result["skill_atlas_copies"]:
            version = copy["version"] if copy["version"] is not None else "unknown"
            print(f"- `{copy['path']}`: {version}")
            aliases = [alias for alias in copy.get("aliases", []) if alias != copy["path"]]
            if aliases:
                print(f"  - also reachable at: {', '.join(f'`{alias}`' for alias in aliases)}")
            if copy.get("target"):
                print(f"  - resolves to: `{copy['target']}`")
    else:
        print("- none")
    print()
    print("## Limitations")
    print()
    for limitation in result["limitations"]:
        print(f"- {limitation}")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--home", default=str(Path.home()), help="User home directory to scan.")
    parser.add_argument("--project", help="Optional project directory whose rule files are reported.")
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
