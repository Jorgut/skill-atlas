#!/usr/bin/env python3
"""Install and manage the optional macOS menu-bar sync helper.

The helper is an explicit opt-in: it is a small AppKit app that polls the
existing `sync notify --channel json` CLI and shows a menu-bar badge when a
repository needs a push. It needs no notification permission; the installer
still requires `--confirm`, backs up nothing silently and can be removed with
`sync helper uninstall`.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

LABEL = "com.skill-atlas.notify-helper"
APP_NAME = "Skill Atlas Notify.app"
ROOT = Path(__file__).resolve().parents[1]


class HelperError(ValueError):
    """Invalid or failed helper installation."""


def paths(home: Path) -> dict[str, Path]:
    home = home.expanduser()
    return {
        "app": home / "Applications" / APP_NAME,
        "config": home / "Library" / "Application Support" / "Skill Atlas" / "helper.json",
        "plist": home / "Library" / "LaunchAgents" / f"{LABEL}.plist",
        "registry": home / ".config" / "skill-atlas" / "watch.json",
        "state": home / ".cache" / "skill-atlas" / "helper-state.json",
        "log": home / ".cache" / "skill-atlas" / "helper.log",
    }


def build_app(output_dir: Path) -> Path:
    """Build the AppKit bundle with swiftc; return the .app path."""
    script = ROOT / "helper" / "build.sh"
    if not script.is_file():
        raise HelperError("helper/build.sh is missing")
    if shutil.which("swiftc") is None:
        raise HelperError("swiftc is required to build the helper (install Xcode command-line tools)")
    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["/bin/bash", str(script), str(output_dir)],
        capture_output=True, text=True, timeout=180, check=False,
    )
    app = output_dir / APP_NAME
    if result.returncode != 0 or not app.is_dir():
        detail = (result.stderr or result.stdout).strip()
        raise HelperError(f"helper build failed: {detail or 'unknown error'}")
    return app


def _plist(app: Path) -> dict[str, Any]:
    return {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/open", "-a", str(app)],
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",
    }


def _launchctl(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(["launchctl", *args], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stderr or result.stdout).decode("utf-8", "replace").strip()


def install(args: argparse.Namespace) -> dict[str, Any]:
    home = Path(getattr(args, "home", None) or Path.home()).expanduser()
    p = paths(home)
    confirm = bool(getattr(args, "confirm", False))
    interval = max(60, int(getattr(args, "interval", 900)))
    dirty_min_files = max(1, int(getattr(args, "dirty_min_files", 20)))
    if not confirm:
        return {
            "status": "preview",
            "app": str(p["app"]),
            "config": str(p["config"]),
            "plist": str(p["plist"]),
            "interval_seconds": interval,
            "dirty_min_files": dirty_min_files,
            "notes": [
                "Preview only. Re-run with --confirm to build/install the helper and its login item.",
                "The helper needs one-time macOS file access permission for the registered repositories.",
            ],
        }
    if sys.platform != "darwin":
        raise HelperError("the menu-bar helper is macOS-only")
    build_dir = Path(tempfile.mkdtemp(prefix="skill-atlas-helper-"))
    try:
        built = build_app(build_dir)
        p["app"].parent.mkdir(parents=True, exist_ok=True)
        if p["app"].exists():
            shutil.rmtree(p["app"])
        shutil.copytree(built, p["app"])
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
    p["config"].parent.mkdir(parents=True, exist_ok=True)
    p["config"].write_text(json.dumps({
        "python": str(Path(sys.executable).resolve()),
        "cli": str(ROOT / "scripts" / "skill_atlas.py"),
        "registry": str(p["registry"]),
        "state": str(p["state"]),
        "log": str(p["log"]),
        "interval": interval,
        "dirty_min_files": dirty_min_files,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    p["plist"].parent.mkdir(parents=True, exist_ok=True)
    p["plist"].write_bytes(plistlib.dumps(_plist(p["app"]), fmt=plistlib.FMT_XML))
    _launchctl(["bootout", f"gui/{os.getuid()}", str(p["plist"])])
    loaded, output = _launchctl(["bootstrap", f"gui/{os.getuid()}", str(p["plist"])])
    if not bool(getattr(args, "no_open", False)):
        subprocess.run(["/usr/bin/open", "-a", str(p["app"])], check=False)
    return {
        "status": "installed" if loaded else "error",
        "app": str(p["app"]),
        "config": str(p["config"]),
        "plist": str(p["plist"]),
        "launchctl_loaded": loaded,
        "launchctl_output": output,
        "notes": [
            "The helper shows a menu-bar SA badge; grant Files and Folders access for the registered repositories when macOS asks.",
            "It never pushes or changes repositories; uninstall with sync helper uninstall --confirm.",
        ],
    }


def uninstall(args: argparse.Namespace) -> dict[str, Any]:
    home = Path(getattr(args, "home", None) or Path.home()).expanduser()
    p = paths(home)
    if not bool(getattr(args, "confirm", False)):
        return {"status": "preview", "app": str(p["app"]), "plist": str(p["plist"]), "config": str(p["config"])}
    _launchctl(["bootout", f"gui/{os.getuid()}", str(p["plist"])])
    subprocess.run(["/usr/bin/pkill", "-f", str(p["app"] / "Contents/MacOS/SkillAtlasNotify")], check=False)
    removed = []
    for key in ("plist", "app", "config"):
        path = p[key]
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(str(path))
        elif path.exists():
            path.unlink()
            removed.append(str(path))
    return {"status": "removed", "removed": removed}


def status(args: argparse.Namespace) -> dict[str, Any]:
    p = paths(Path(getattr(args, "home", None) or Path.home()).expanduser())
    return {
        "status": "installed" if p["app"].is_dir() else "not-installed",
        "app": str(p["app"]),
        "config": str(p["config"]),
        "plist": str(p["plist"]),
    }


def add_install_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--confirm", action="store_true", help="Build and install the helper and login item.")
    parser.add_argument("--interval", type=int, default=900, help="Poll interval in seconds (default 900).")
    parser.add_argument("--dirty-min-files", type=int, default=20,
                        help="Show a dirty-worktree warning at or above this file count (default 20).")
    parser.add_argument("--no-open", action="store_true", help="Do not launch the helper after install.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--home", default=None, help=argparse.SUPPRESS)


def add_confirm_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--confirm", action="store_true", help="Actually remove the helper.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--home", default=None, help=argparse.SUPPRESS)


def add_status_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--home", default=None, help=argparse.SUPPRESS)


def emit_markdown(result: dict[str, Any]) -> None:
    print(f"# Skill Atlas Notify helper: {result['status']}")
    for key in ("app", "config", "plist", "launchctl_loaded", "launchctl_output", "removed"):
        if key in result:
            print(f"- {key}: {result[key]}")
    for note in result.get("notes", []):
        print(f"- note: {note}")
