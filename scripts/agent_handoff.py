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
