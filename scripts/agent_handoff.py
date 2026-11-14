#!/usr/bin/env python3
"""Portable, local-only Git checkpoints and verified agent handoffs."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
STATE_DIR = ".agent-state"


class HandoffError(ValueError):
    """Unsafe or unsupported handoff request."""


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise HandoffError(f"Git command failed: {' '.join(args)}")
    return result.stdout.rstrip("\n")


def repo_root(project: str | Path) -> Path:
    location = Path(project).expanduser().resolve()
    if not location.is_dir():
        raise HandoffError("Project directory does not exist")
    return Path(git(location, "rev-parse", "--show-toplevel")).resolve()


def state_path(root: Path, task: str) -> Path:
    if not TASK_ID.fullmatch(task):
        raise HandoffError("Task ID must use 1-80 letters, numbers, dots, dashes or underscores")
    return root / STATE_DIR / "tasks" / f"{task}.json"


def fingerprint(root: Path) -> dict[str, Any]:
    raw = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    # Exclude only the generated state directory; never discard user modifications.
    entries = [line for line in raw.splitlines() if line and
               not line[3:].startswith(f"{STATE_DIR}/")]
    normalized = "\n".join(sorted(entries))
    # Status alone misses content changes when file names and M flags are unchanged.
    # Hash Git's tracked patch locally without writing source or secrets to the state file.
    patch = git(root, "diff", "--binary", "HEAD", "--", ".", ":(exclude).agent-state")
    unstaged_untracked = []
    for line in entries:
        if line.startswith("?? "):
            relative = line[3:]
            candidate = root / relative
            try:
                details = candidate.lstat()
                unstaged_untracked.append([relative, details.st_size, details.st_mtime_ns])
            except OSError:
                unstaged_untracked.append([relative, "missing"])
    content_digest = hashlib.sha256(
        (patch + "\n" + json.dumps(unstaged_untracked, sort_keys=True)).encode("utf-8")
    ).hexdigest()
    try:
        branch = git(root, "symbolic-ref", "--short", "HEAD")
    except HandoffError:
        branch = "DETACHED"
    return {
        "branch": branch,
        "commit": git(root, "rev-parse", "HEAD"),
        "working_tree_changes": len(entries),
        "working_tree_digest": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "content_digest": content_digest,
    }


def sync_status(root: Path) -> dict[str, Any]:
    """Read-only local Git sync status; never fetches, pushes or mutates refs."""
    try:
        branch = git(root, "symbolic-ref", "--short", "HEAD")
    except HandoffError:
        branch = "DETACHED"
    detached = branch == "DETACHED"
    upstream: str | None = None
    try:
        upstream = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    except HandoffError:
        upstream = None
    ahead = 0
    behind = 0
    if upstream:
        counts = git(root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD").split()
        if len(counts) == 2:
            behind, ahead = int(counts[0]), int(counts[1])
    raw = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    dirty = len([line for line in raw.splitlines() if line and
                 not line[3:].startswith(f"{STATE_DIR}/")])
    try:
        last_commit = git(root, "log", "-1", "--format=%cI")
    except HandoffError:
        last_commit = None
    try:
        commit = git(root, "rev-parse", "HEAD")
    except HandoffError:
        commit = None
    warnings: list[str] = []
    if detached:
        warnings.append("Detached HEAD: commits are not on a branch and are easy to lose; create a branch before continuing")
    elif not upstream:
        warnings.append("Current branch has no upstream: commits are local-only; push when the work is reviewed")
    if ahead > 0:
        warnings.append(f"{ahead} local commit(s) are not on the remote; push when the work is reviewed")
    if behind > 0:
        warnings.append(f"Remote-tracking branch is {behind} commit(s) ahead; fetch/rebase or merge before handoff")
    if dirty > 0:
        warnings.append(f"{dirty} uncommitted change(s); commit or record them before handoff")
    notes = ["Tracking refs may be stale: no fetch or network call was made"]
    return {
        "branch": branch,
        "upstream": upstream,
        "has_upstream": upstream is not None,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty,
        "detached": detached,
        "last_commit": last_commit,
        "commit": commit,
        "warnings": warnings,
        "tracking_refs_may_be_stale": upstream is not None,
        "notes": notes,
    }


def sync_report(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root(args.project)
    status = sync_status(root)
    return {
        "status": "ok",
        "project": str(root),
        "git": status,
        "warnings": status["warnings"],
        "notes": "Read-only local Git status; no fetch, push or repository mutation executed",
    }


def worktree_paths(root: Path) -> list[Path]:
    """Return the main and linked worktrees for a repository."""
    raw = git(root, "worktree", "list", "--porcelain")
    paths = []
    for line in raw.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line[len("worktree "):]).resolve())
    if not paths:
        paths = [root]
    unique = []
    seen = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def load_registry(path: Path) -> list[Path]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HandoffError(f"Registry is unreadable: {path}") from exc
    if isinstance(data, dict):
        data = data.get("projects")
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise HandoffError("Registry must be a JSON list or an object with a 'projects' list")
    return [Path(item) for item in data]


def fetch_remotes(root: Path, timeout: float) -> str | None:
    """Fetch one repository's remotes; return an error note instead of raising."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "fetch", "--quiet", "--prune"],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if result.returncode != 0:
        return result.stderr.decode("utf-8", "replace").strip() or f"git fetch exited {result.returncode}"
    return None


def _compact_notification(items: list[dict[str, Any]]) -> tuple[str, str, str]:
    title = "Skill Atlas"
    plural = "s" if len(items) != 1 else ""
    verb = "need" if len(items) != 1 else "needs"
    subtitle = f"{len(items)} project{plural} {verb} a push"
    parts = []
    for item in items[:3]:
        label = Path(item["path"]).name
        if not item["has_upstream"]:
            detail = "no upstream"
        elif item["ahead"]:
            detail = f"{item['ahead']} unpushed"
        elif item["behind"]:
            detail = f"behind {item['behind']}"
        elif item["detached"]:
            detail = "detached HEAD"
        else:
            detail = "needs review"
        parts.append(f"{label} · {item['branch']}: {detail}")
    body = "; ".join(parts)
    if len(items) > 3:
        body += f"; +{len(items) - 3} more"
    return title, subtitle, body


def _send_macos_notification(title: str, subtitle: str, body: str, sound: str | None = "Glass") -> None:
    def quote(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    suffix = f" sound name {quote(sound)}" if sound else ""
    script = f"display notification {quote(body)} with title {quote(title)} subtitle {quote(subtitle)}{suffix}"
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return


def _append_notification_log(log_path: Path, entries: list[dict[str, Any]], channel: str) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({
                "at": datetime.now(timezone.utc).isoformat(),
                "channel": channel,
                "items": [
                    {
                        "path": item["path"],
                        "branch": item["branch"],
                        "warnings": item["warnings"],
                    }
                    for item in entries
                ],
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _recent_activity(root: Path) -> float | None:
    """Latest mtime of a dirty path or the last commit, used for idle suppression."""
    latest: float | None = None
    try:
        raw = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    except HandoffError:
        raw = ""
    for record in raw.split("\0"):
        if not record:
            continue
        relative = record[3:]
        if relative.startswith(f"{STATE_DIR}/"):
            continue
        try:
            latest = max(latest or 0, (root / relative).lstat().st_mtime)
        except OSError:
            continue
    try:
        latest = max(latest or 0, float(git(root, "log", "-1", "--format=%ct")))
    except (HandoffError, ValueError):
        pass
    return latest


def sync_notify(args: argparse.Namespace) -> dict[str, Any]:
    """Check registered projects and notify only when a push-related warning appears."""
    projects: list[Path] = [Path(item) for item in getattr(args, "project", [])]
    registry = getattr(args, "registry", None)
    if registry:
        projects.extend(load_registry(Path(registry)))
    channel = getattr(args, "channel", "macos")
    min_interval = max(0.0, float(getattr(args, "min_interval", 60)))
    include_dirty = bool(getattr(args, "include_dirty", False))
    do_fetch = bool(getattr(args, "fetch", False))
    idle_minutes = max(0.0, float(getattr(args, "idle_minutes", 0)))
    force_after_minutes = max(0.0, float(getattr(args, "force_after_minutes", 0)))
    sound = getattr(args, "sound", "Glass")
    state_path = Path(getattr(args, "state", None) or (Path.home() / ".cache" / "skill-atlas" / "sync-notify.json"))
    log_path = Path(getattr(args, "log", None) or (Path.home() / ".cache" / "skill-atlas" / "sync-notify.log"))
    fetch_timeout = max(1.0, float(getattr(args, "fetch_timeout", 10)))
    if getattr(args, "test_notification", False):
        title, subtitle, body = "Skill Atlas test notification", "Notification delivery test", "If you see this, macOS notifications work."
        if channel == "macos":
            _send_macos_notification(title, subtitle, body, sound)
        elif channel == "stderr":
            print(f"{title} · {subtitle}: {body}")
        elif channel != "json":
            raise HandoffError("channel must be macos, stderr or json")
        _append_notification_log(log_path, [{
            "path": "test", "branch": "-", "warnings": ["test notification"]
        }], channel)
        return {
            "status": "test-notification",
            "channel": channel,
            "notified": [],
            "suppressed": [],
            "skipped": [],
            "fetch_errors": [],
            "state_file": str(state_path),
            "log_file": str(log_path),
            "fetch": False,
            "notes": "Test notification sent; no repository was checked",
        }
    if not projects:
        raise HandoffError("Provide at least one --project or a --registry file")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    now = time.time()
    actionable: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    fetch_errors: list[dict[str, str]] = []
    for project in projects:
        try:
            root = repo_root(project)
        except HandoffError as exc:
            skipped.append({"project": str(project), "reason": str(exc)})
            continue
        if do_fetch:
            error = fetch_remotes(root, fetch_timeout)
            if error:
                fetch_errors.append({"project": str(root), "error": error})
        for path in worktree_paths(root):
            key_path = str(path)
            if key_path in seen_paths:
                continue
            seen_paths.add(key_path)
            try:
                status = sync_status(path)
            except HandoffError as exc:
                skipped.append({"project": key_path, "reason": str(exc)})
                continue
            warnings = []
            if status["detached"]:
                warnings.append("detached HEAD")
            if not status["has_upstream"]:
                warnings.append("no upstream")
            if status["ahead"]:
                warnings.append(f"{status['ahead']} unpushed commit(s)")
            if status["behind"]:
                warnings.append(f"behind remote by {status['behind']} commit(s)")
            if include_dirty and status["dirty"]:
                warnings.append(f"{status['dirty']} uncommitted change(s)")
            if not warnings:
                state.pop(key_path, None)
                continue
            item = {
                "project": str(root),
                "path": key_path,
                "branch": status["branch"],
                "has_upstream": status["has_upstream"],
                "ahead": status["ahead"],
                "behind": status["behind"],
                "dirty": status["dirty"],
                "detached": status["detached"],
                "commit": status["commit"],
                "warnings": warnings,
            }
            key = "|".join(str(item[field]) for field in
                           ("path", "branch", "commit", "ahead", "behind", "has_upstream", "detached"))
            previous = state.get(key_path) or {}
            same_key = previous.get("key") == key
            first_seen = float(previous.get("first_seen_at", now)) if same_key else now
            notified_at = float(previous.get("notified_at", 0))
            interval_ok = (not same_key) or (now - notified_at) >= min_interval * 60
            recent_activity = False
            if idle_minutes > 0:
                last_activity = _recent_activity(path)
                recent_activity = last_activity is not None and (now - last_activity) < idle_minutes * 60
            force_due = (
                force_after_minutes > 0
                and same_key
                and (now - first_seen) >= force_after_minutes * 60
                and interval_ok
            )
            if recent_activity and not force_due:
                suppressed.append({**item, "reason": "recent activity"})
                state[key_path] = {"key": key, "first_seen_at": first_seen, "notified_at": notified_at}
                continue
            if not interval_ok and not force_due:
                suppressed.append(item)
                state[key_path] = {"key": key, "first_seen_at": first_seen, "notified_at": notified_at}
                continue
            actionable.append(item)
            state[key_path] = {"key": key, "first_seen_at": now, "notified_at": now}
    if actionable:
        title, subtitle, body = _compact_notification(actionable)
        if channel == "macos":
            _send_macos_notification(title, subtitle, body, sound)
        elif channel == "stderr":
            print(f"{title} · {subtitle}: {body}")
        elif channel == "json":
            pass
        else:
            raise HandoffError("channel must be macos, stderr or json")
        _append_notification_log(log_path, actionable, channel)
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    result = {
        "status": "notified" if actionable else "clean",
        "channel": channel,
        "checked": len(seen_paths),
        "notified": actionable,
        "suppressed": suppressed,
        "skipped": skipped,
        "fetch_errors": fetch_errors,
        "state_file": str(state_path),
        "log_file": str(log_path),
        "idle_minutes": idle_minutes,
        "force_after_minutes": force_after_minutes,
        "fetch": do_fetch,
        "notes": "Read-only Git checks; notifications only, never push/commit/fetch unless --fetch was supplied",
    }
    return result


def write_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root(args.project)
    target = state_path(root, args.task)
    if args.test_result != "not-run" and not args.test_command:
        raise HandoffError("A passed or failed test result requires --test-command")
    git_state = fingerprint(root)
    git_state["sync"] = sync_status(root)
    state = {
        "schema_version": 1,
        "task": args.task,
        "kind": args.command,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "agent": args.agent,
        "summary": args.summary,
        "completed": args.completed or [],
        "remaining": args.remaining or [],
        "next_action": args.next_action,
        "git": git_state,
        "tests": {
            "command": args.test_command,
            "result": args.test_result,
            "evidence": "agent-reported" if args.test_result != "not-run" else "not-run",
        },
    }
    base = root / STATE_DIR
    target.parent.mkdir(parents=True, exist_ok=True)
    history = base / "history" / args.task
    history.mkdir(parents=True, exist_ok=True)
    # Serialize concurrent writers. Both current and immutable history are persisted.
    with (base / ".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        data = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        archive = history / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}.json"
        archive.write_text(data, encoding="utf-8")
        fd, name = tempfile.mkstemp(prefix=".checkpoint-", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(data)
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return {"status": "recorded", "state_file": str(target), "history_file": str(archive),
            "checkpoint": state, "warnings": git_state["sync"]["warnings"],
            "notes": "Local state only; no Git commit, push, tests or agent dispatch executed"}


def inspect_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root(args.project)
    target = state_path(root, args.task)
    if not target.is_file():
        return {"status": "no-checkpoint", "state_file": str(target),
                "next_action": "Inspect repository and current issue before editing"}
    try:
        checkpoint = json.loads(target.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise HandoffError("Checkpoint file is invalid or unreadable") from exc
    if checkpoint.get("schema_version") != 1 or checkpoint.get("task") != args.task:
        raise HandoffError("Checkpoint schema or task does not match")
    current = fingerprint(root)
    current["sync"] = sync_status(root)
    previous = checkpoint.get("git") or {}
    changed = [field for field in ("branch", "commit", "working_tree_changes", "working_tree_digest", "content_digest")
               if current.get(field) != previous.get(field)]
    return {"status": "review-required" if changed else "checkpoint-consistent",
            "state_file": str(target), "changed_fields": changed,
            "checkpoint": checkpoint, "current_git": current,
            "warnings": current["sync"]["warnings"],
            "notes": "Read-only inspection. Recheck files, issue and tests; no agent execution started"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    return inspect_checkpoint(args) if args.command == "resume" else write_checkpoint(args)


def emit_markdown(result: dict[str, Any]) -> None:
    print(f"# Agent handoff: {result['status']}")
    print(f"- state: \x60{result['state_file']}\x60")
    checkpoint = result.get("checkpoint")
    if checkpoint:
        print(f"- task: {checkpoint['task']}")
        print(f"- agent: {checkpoint['agent']}")
        print(f"- branch: {checkpoint['git']['branch']}")
        print(f"- commit: {checkpoint['git']['commit']}")
        print(f"- next: {checkpoint['next_action']}")
    for warning in result.get("warnings") or []:
        print(f"- warning: {warning}")
    if result.get("changed_fields"):
        print(f"- mismatches: {', '.join(result['changed_fields'])}")
    if result.get("notes"):
        print(f"- note: {result['notes']}")


def add_sync_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", default=".")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")


def add_notify_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", action="append", default=[],
                        help="Repository to check; may be repeated.")
    parser.add_argument("--registry", help="JSON file with a list (or a 'projects' list) of repository paths.")
    parser.add_argument("--channel", choices=("macos", "stderr", "json"), default="macos",
                        help="Where to send actionable warnings (default: macos notification).")
    parser.add_argument("--min-interval", type=float, default=60,
                        help="Do not repeat the same state for this many minutes (default 60).")
    parser.add_argument("--state", help="Deduplication state file (default: ~/.cache/skill-atlas/sync-notify.json).")
    parser.add_argument("--fetch", action="store_true",
                        help="Run git fetch before checking; off by default and never pushes.")
    parser.add_argument("--fetch-timeout", type=float, default=10,
                        help="Seconds allowed per repository fetch (default 10).")
    parser.add_argument("--include-dirty", action="store_true",
                        help="Also notify for uncommitted changes; off by default.")
    parser.add_argument("--idle-minutes", type=float, default=0,
                        help="Suppress notifications while the worktree changed within this many minutes (default 0 = off).")
    parser.add_argument("--force-after-minutes", type=float, default=0,
                        help="Send a periodic digest even while active once the same state has persisted this long (default 0 = off).")
    parser.add_argument("--sound", default="Glass",
                        help="macOS notification sound name (default Glass); empty string disables the sound.")
    parser.add_argument("--log", help="Append notification log (default: ~/.cache/skill-atlas/sync-notify.log).")
    parser.add_argument("--test-notification", action="store_true",
                        help="Send one test notification and exit; useful to verify delivery.")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", default=".")
    parser.add_argument("--task", required=True, help="Stable task ID, e.g. issue-28")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="command", required=True)
    for name in ("checkpoint", "handoff", "resume"):
        action = actions.add_parser(name)
        add_arguments(action)
        if name != "resume":
            action.add_argument("--agent", required=True)
            action.add_argument("--summary", required=True)
            action.add_argument("--next-action", required=True)
            action.add_argument("--completed", action="append", default=[])
            action.add_argument("--remaining", action="append", default=[])
            action.add_argument("--test-command")
            action.add_argument("--test-result", choices=("not-run", "passed", "failed"), default="not-run")
    args = parser.parse_args()
    try:
        result = run(args)
    except HandoffError as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        emit_markdown(result)


if __name__ == "__main__":
    main()
