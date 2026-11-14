#!/usr/bin/env python3
"""One-command setup for the optional macOS sync notification job.

The command is deliberately explicit: without ``--confirm`` it only prints what
it would create. With ``--confirm`` it merges the project registry, writes a
user LaunchAgent (backing up existing files), loads it with ``launchctl`` and
sends a test notification. It never pushes, fetches or changes a repository.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import agent_handoff

LABEL = "com.skill-atlas.sync-notify"


class SetupError(ValueError):
    """Invalid or unsupported setup request."""


def default_paths(home: Path) -> dict[str, Path]:
    home = home.expanduser().resolve()
    return {
        "registry": home / ".config" / "skill-atlas" / "watch.json",
        "plist": home / "Library" / "LaunchAgents" / f"{LABEL}.plist",
        "log": home / ".cache" / "skill-atlas" / "sync-notify.log",
        "state": home / ".cache" / "skill-atlas" / "sync-notify.json",
    }


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%dT%H%M%S")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    if target.exists():
        target = path.with_name(f"{path.name}.bak-{stamp}-{os.getpid()}")
    target.write_bytes(path.read_bytes())
    return target


def _registry_document(path: Path, projects: list[str]) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SetupError(f"Existing registry is not valid JSON: {path}") from exc
        if isinstance(loaded, dict):
            existing = loaded
        elif isinstance(loaded, list):
            existing = {"projects": loaded}
        else:
            raise SetupError("Existing registry must be a JSON list or an object")
    current = existing.get("projects", [])
    if not isinstance(current, list) or not all(isinstance(item, str) for item in current):
        raise SetupError("Existing registry 'projects' must be a list of paths")
    merged = list(dict.fromkeys([*current, *projects]))
    existing["projects"] = merged
    return existing


def _plist_document(
    python: Path, script: Path, registry: Path, log: Path,
    *, interval_minutes: int, idle_minutes: int, min_interval: int,
) -> dict[str, Any]:
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(python),
            str(script),
            "sync",
            "notify",
            "--registry",
            str(registry),
            "--channel",
            "macos",
            "--min-interval",
            str(min_interval),
            "--idle-minutes",
            str(idle_minutes),
        ],
        "StartInterval": max(60, interval_minutes * 60),
        "RunAtLoad": False,
        "LimitLoadToSessionType": "Aqua",
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log.with_suffix(".err")),
    }


def _run_launchctl(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(["launchctl", *args], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (result.stderr or result.stdout).decode("utf-8", "replace").strip()
    return result.returncode == 0, output


def setup(args: argparse.Namespace) -> dict[str, Any]:
    home = Path(getattr(args, "home", None) or Path.home()).expanduser()
    paths = default_paths(home)
    projects = [str(Path(item).expanduser().resolve()) for item in getattr(args, "project", [])]
    if not projects:
        try:
            projects = [str(agent_handoff.repo_root("."))]
        except agent_handoff.HandoffError as exc:
            raise SetupError("Provide at least one --project or run inside a Git repository") from exc
    for project in projects:
        try:
            agent_handoff.repo_root(project)
        except agent_handoff.HandoffError as exc:
            raise SetupError(f"Not a usable Git repository: {project}") from exc
    interval = max(1, int(getattr(args, "interval", 15)))
    idle = max(0, int(getattr(args, "idle_minutes", 30)))
    min_interval = max(0, int(getattr(args, "min_interval", 60)))
    confirm = bool(getattr(args, "confirm", False))
    run_test = not bool(getattr(args, "no_test", False))
    registry = _registry_document(paths["registry"], projects)
    python = Path(sys.executable).resolve()
    script = Path(__file__).resolve().parent / "skill_atlas.py"
    plan = _plist_document(
        python, script, paths["registry"], paths["log"],
        interval_minutes=interval, idle_minutes=idle, min_interval=min_interval,
    )
    if not confirm:
        return {
            "status": "preview",
            "registry": str(paths["registry"]),
            "plist": str(paths["plist"]),
            "projects": registry["projects"],
            "interval_minutes": interval,
            "idle_minutes": idle,
            "min_interval": min_interval,
            "plist_document": plan,
            "notes": ["Preview only. Re-run with --confirm to write the registry, install the LaunchAgent and run a test notification."],
        }
    if sys.platform != "darwin":
        raise SetupError("LaunchAgent setup is macOS-only")
    backups: list[str] = []
    registry_parent = paths["registry"].parent
    registry_parent.mkdir(parents=True, exist_ok=True)
    paths["plist"].parent.mkdir(parents=True, exist_ok=True)
    backup = _backup(paths["registry"])
    if backup:
        backups.append(str(backup))
    backup = _backup(paths["plist"])
    if backup:
        backups.append(str(backup))
    paths["registry"].write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["plist"].write_bytes(plistlib.dumps(plan, fmt=plistlib.FMT_XML))
    ok, output = _run_launchctl(["bootout", f"gui/{os.getuid()}", str(paths["plist"])])
    loaded, bootstrap_output = _run_launchctl(["bootstrap", f"gui/{os.getuid()}", str(paths["plist"])])
    test_result: dict[str, Any] | None = None
    test_error: str | None = None
    if run_test:
        try:
            test_result = agent_handoff.sync_notify(argparse.Namespace(
                project=[], registry=None, channel="macos", min_interval=min_interval,
                state=str(paths["state"]), fetch=False, fetch_timeout=10, include_dirty=False,
                idle_minutes=0, sound="Glass", log=str(paths["log"]),
                test_notification=True,
            ))
        except Exception as exc:  # pragma: no cover - defensive for OS-specific failures
            test_error = str(exc)
    return {
        "status": "installed" if loaded else "error",
        "registry": str(paths["registry"]),
        "plist": str(paths["plist"]),
        "projects": registry["projects"],
        "interval_minutes": interval,
        "idle_minutes": idle,
        "min_interval": min_interval,
        "backups": backups,
        "launchctl_loaded": loaded,
        "launchctl_output": bootstrap_output or output,
        "test_notification": test_result,
        "test_error": test_error,
        "notes": [
            "The job only reads local Git metadata and never pushes, fetches or changes a repository.",
            "If no banner appears, allow notifications for Script Editor (or the helper app) in System Settings.",
        ],
    }


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", action="append", default=[], help="Git repository to watch; may be repeated.")
    parser.add_argument("--interval", type=int, default=15, help="Check interval in minutes (default 15).")
    parser.add_argument("--idle-minutes", type=int, default=30, help="Suppress while recently active (default 30).")
    parser.add_argument("--min-interval", type=int, default=60, help="Minimum repeat interval for the same state (default 60).")
    parser.add_argument("--confirm", action="store_true", help="Write files, install the LaunchAgent and test.")
    parser.add_argument("--no-test", action="store_true", help="Skip the test notification.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--home", default=None, help=argparse.SUPPRESS)


def emit_markdown(result: dict[str, Any]) -> None:
    print(f"# Sync notification setup: {result['status']}")
    print(f"- registry: `{result['registry']}`")
    print(f"- launch agent: `{result['plist']}`")
    print(f"- projects: {', '.join(result['projects'])}")
    print(f"- checks every {result['interval_minutes']} min; idle {result['idle_minutes']} min; repeat >= {result['min_interval']} min")
    if result.get("backups"):
        print(f"- backups: {', '.join(result['backups'])}")
    if "launchctl_loaded" in result:
        print(f"- launchctl loaded: {result['launchctl_loaded']}")
    if result.get("test_notification"):
        print(f"- test notification: {result['test_notification'].get('status')}")
    if result.get("test_error"):
        print(f"- test error: {result['test_error']}")
    for note in result.get("notes", []):
        print(f"- note: {note}")
