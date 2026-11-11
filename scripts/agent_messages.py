#!/usr/bin/env python3
"""Opt-in, local message transport for cross-agent handoffs.

Messages are stored as immutable JSON envelopes under ``.agent-state/messages``
inside the receiving project's Git root. The transport never sends network
traffic, never starts another agent and never performs the requested action.
Receiving agents, and people, read and acknowledge messages with explicit
commands so that every transition leaves a local receipt.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import agent_handoff

STATE_DIR = agent_handoff.STATE_DIR
SCHEMA_VERSION = 1
DEFAULT_TTL_HOURS = 24.0
MAX_TTL_HOURS = 24 * 30
MAX_PASSES = 10
MAX_SUMMARY = 2000
MAX_CONCLUSION = 4000
MAX_NOTE = 2000
MAX_EVIDENCE_ITEMS = 20
MAX_EVIDENCE_LENGTH = 300
MAX_INBOX = 200
MAX_MESSAGES_PER_TASK = 5000

AGENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:-]{0,63}$")
MESSAGE_ID = re.compile(r"^msg_[A-Za-z0-9][A-Za-z0-9_]{0,79}$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TASK_ID = agent_handoff.TASK_ID

STATUSES = ("queued", "taken", "completed", "refused")
TERMINAL_STATUSES = ("completed", "refused")


class MessageError(ValueError):
    """Unsafe, unsupported or conflicting message request."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise MessageError("Stored message timestamp is invalid") from exc


def _text(value: Any, field: str, limit: int, required: bool = False) -> str:
    if value is None:
        if required:
            raise MessageError(f"--{field} is required")
        return ""
    if not isinstance(value, str):
        raise MessageError(f"--{field} must be text")
    cleaned = value.strip()
    if any(ord(char) < 32 and char not in "\n\t" for char in cleaned):
        raise MessageError(f"--{field} contains control characters")
    if len(cleaned) > limit:
        raise MessageError(f"--{field} must be at most {limit} characters")
    if required and not cleaned:
        raise MessageError(f"--{field} must not be empty")
    return cleaned


def clean_task(value: Any) -> str:
    if not isinstance(value, str) or not TASK_ID.fullmatch(value):
        raise MessageError("Task ID must use 1-80 letters, numbers, dots, dashes or underscores")
    return value


def clean_agent(value: Any, field: str = "agent") -> str:
    if not isinstance(value, str):
        raise MessageError(f"--{field} must be text")
    cleaned = value.strip()
    if not AGENT.fullmatch(cleaned):
        raise MessageError(
            f"--{field} must start with a letter or digit and use at most 64 letters, "
            "digits, spaces, dots, dashes, underscores or colons"
        )
    return cleaned


def clean_message_id(value: Any) -> str:
    if not isinstance(value, str) or not MESSAGE_ID.fullmatch(value):
        raise MessageError("Message ID must look like msg_<token>")
    return value


def clean_request_id(value: Any) -> str:
    if value is None:
        return f"auto-{uuid.uuid4().hex}"
    if not isinstance(value, str) or not REQUEST_ID.fullmatch(value):
        raise MessageError(
            "Request ID must use 1-128 letters, numbers, dots, dashes, underscores or colons"
        )
    return value


def clean_evidence(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        raise MessageError("Evidence must be a list of short pointers")
    if len(values) > MAX_EVIDENCE_ITEMS:
        raise MessageError(f"Use at most {MAX_EVIDENCE_ITEMS} evidence entries")
    cleaned: list[str] = []
    for item in values:
        text = _text(item, "evidence", MAX_EVIDENCE_LENGTH)
        if text:
            cleaned.append(text)
    return cleaned


def clean_ttl(value: Any) -> float:
    try:
        hours = float(value)
    except (TypeError, ValueError) as exc:
        raise MessageError("TTL hours must be a number") from exc
    if not 0 < hours <= MAX_TTL_HOURS:
        raise MessageError(f"TTL hours must be greater than 0 and at most {MAX_TTL_HOURS}")
    return hours


def clean_pass(value: Any) -> int | None:
    if value is None:
        return None
    try:
        pass_count = int(value)
    except (TypeError, ValueError) as exc:
        raise MessageError("Message chain pass must be an integer") from exc
    if not 1 <= pass_count <= MAX_PASSES:
        raise MessageError(f"Message chain pass must be between 1 and {MAX_PASSES}")
    return pass_count


def _reject_symlinked_components(path: Path, root: Path) -> None:
    """Refuse a state path that resolves through a symlink inside the checkout."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise MessageError("Message state path escapes the project Git root") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise MessageError(
                f"Refusing to use a symlinked agent-state path: {current.relative_to(root)}"
            )


def _state_base(root: Path, task: str) -> Path:
    base = root / STATE_DIR / "messages" / clean_task(task)
    for relative in ("", "envelopes", "status", "requests", "receipts", "approvals"):
        _reject_symlinked_components(base / relative, root)
    return base


def _write_json_atomic(path: Path, payload: dict[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if exclusive:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
        return
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class _Lock:
    """Serialize writers with the same lock file the checkpoint commands use."""

    def __init__(self, project: str | Path) -> None:
        self.root = agent_handoff.repo_root(project)
        self.path = self.root / STATE_DIR / ".lock"

    def __enter__(self) -> "_Lock":
        _reject_symlinked_components(self.path.parent, self.root)
        _reject_symlinked_components(self.path, self.root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_: Any) -> None:
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def _envelopes(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.glob("msg_*.json"))


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise MessageError(f"{label} is invalid or unreadable: {path.name}") from exc
    if not isinstance(payload, dict):
        raise MessageError(f"{label} is invalid: {path.name}")
    return payload


def _append_receipt(base: Path, message_id: str, event: dict[str, Any]) -> None:
    receipts = base / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    path = receipts / f"{message_id}.jsonl"
    line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        stream.write(line)


def _read_receipts(base: Path, message_id: str) -> list[dict[str, Any]]:
    path = base / "receipts" / f"{message_id}.jsonl"
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _status_of(base: Path, message_id: str) -> str:
    path = base / "status" / f"{message_id}.json"
    if not path.is_file():
        raise MessageError(f"Message status is missing: {message_id}")
    payload = _load_json(path, "Message status")
    status = payload.get("status")
    if status not in STATUSES:
        raise MessageError(f"Message status is invalid: {message_id}")
    return status


def _is_expired(envelope: dict[str, Any], status: str) -> bool:
    if status in TERMINAL_STATUSES:
        return False
    return parse_time(envelope["expires_at"]) <= utc_now()


def _approval_of(base: Path, envelope: dict[str, Any]) -> str:
    if not envelope.get("requires_approval"):
        return "not-required"
    path = base / "approvals" / f"{envelope['id']}.json"
    if path.is_file():
        _load_json(path, "Message approval")
        return "approved"
    return "pending"


def _canonical_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _envelope_view(
    envelope: dict[str, Any], status: str, expired: bool, approval: str
) -> dict[str, Any]:
    return {
        "id": envelope["id"],
        "task": envelope["task"],
        "from": envelope["from"],
        "to": envelope["to"],
        "status": "expired" if expired else status,
        "created_at": envelope["created_at"],
        "expires_at": envelope["expires_at"],
        "reply_to": envelope.get("reply_to"),
        "pass": envelope["pass"],
        "summary": envelope["summary"],
        "conclusion": envelope.get("conclusion") or "",
        "evidence": list(envelope.get("evidence") or []),
        "requires_approval": bool(envelope.get("requires_approval")),
        "approval": approval,
        "expired": expired,
    }


def _load_envelope(base: Path, message_id: str) -> dict[str, Any]:
    path = base / "envelopes" / f"{message_id}.json"
    if not path.is_file():
        raise MessageError(f"Message not found in this task: {message_id}")
    envelope = _load_json(path, "Message envelope")
    if envelope.get("schema_version") != SCHEMA_VERSION or envelope.get("id") != message_id:
        raise MessageError(f"Message envelope is invalid: {message_id}")
    return envelope


def _next_pass(base: Path, reply_to: str | None, requested: int | None) -> int:
    if not reply_to:
        return requested or 1
    parent = _load_envelope(base, reply_to)
    expected = int(parent.get("pass") or 1) + 1
    if expected > MAX_PASSES:
        raise MessageError(
            f"Message chain reached {MAX_PASSES} passes; stop the exchange and ask the user"
        )
    if requested is not None and requested != expected:
        raise MessageError(f"A reply must use pass {expected}; got {requested}")
    return expected


def send(args: argparse.Namespace) -> dict[str, Any]:
    root = agent_handoff.repo_root(args.project)
    task = clean_task(args.task)
    sender = clean_agent(args.from_agent, "from")
    recipient = clean_agent(args.to, "to")
    summary = _text(args.summary, "summary", MAX_SUMMARY, required=True)
    conclusion = _text(args.conclusion, "conclusion", MAX_CONCLUSION)
    evidence = clean_evidence(args.evidence)
    ttl_hours = clean_ttl(args.ttl_hours)
    request_id = clean_request_id(args.request_id)
    reply_to = clean_message_id(args.reply_to) if args.reply_to else None
    requested_pass = clean_pass(args.pass_count)
    requires_approval = bool(args.requires_approval)

    # The digest covers every caller-supplied option, including the requested
    # chain pass and TTL, so a reused request ID with different options fails
    # instead of silently returning the earlier message.
    payload = {
        "task": task,
        "from": sender,
        "to": recipient,
        "summary": summary,
        "conclusion": conclusion,
        "evidence": evidence,
        "reply_to": reply_to,
        "requires_approval": requires_approval,
        "ttl_hours": ttl_hours,
        "pass": requested_pass,
    }
    digest = _canonical_digest(payload)

    with _Lock(root):
        base = _state_base(root, task)
        request_path = base / "requests" / f"{request_id}.json"
        # Idempotency is checked before any reply-chain validation: a retry must
        # return the recorded message even after its parent expired or was refused.
        if request_path.is_file():
            previous = _load_json(request_path, "Message request")
            if previous.get("content_hash") != digest:
                raise MessageError("This request ID was already used with different content")
            message_id = previous.get("message_id")
            envelope = _load_envelope(base, message_id)
            status_path = base / "status" / f"{message_id}.json"
            if not status_path.is_file():
                # Recover a send interrupted between the request record and the
                # status write instead of dead-ending the idempotency record.
                now = utc_now()
                _write_json_atomic(
                    status_path,
                    {
                        "schema_version": SCHEMA_VERSION,
                        "message_id": message_id,
                        "status": "queued",
                        "updated_at": iso(now),
                        "updated_by": envelope["from"],
                    },
                )
                _append_receipt(
                    base,
                    message_id,
                    {
                        "event": "queued",
                        "at": iso(now),
                        "agent": envelope["from"],
                        "approval": envelope.get("approval", "not-required"),
                        "note": "recovered interrupted send",
                    },
                )
            status = _status_of(base, message_id)
            expired = _is_expired(envelope, status)
            return {
                "status": "duplicate",
                "message_file": str(base / "envelopes" / f"{envelope['id']}.json"),
                "message": _envelope_view(envelope, status, expired, _approval_of(base, envelope)),
                "notes": "Local file transport only; the receiving agent has not been notified",
            }

        if reply_to:
            parent = _load_envelope(base, reply_to)
            parent_status = _status_of(base, reply_to)
            if parent_status == "refused":
                raise MessageError("The message being replied to was refused")
            if _is_expired(parent, parent_status):
                raise MessageError("The message being replied to has expired")
            if parent.get("task") != task:
                raise MessageError("A reply must stay inside the same task")
        pass_count = _next_pass(base, reply_to, requested_pass)

        if len(_envelopes(base / "envelopes")) >= MAX_MESSAGES_PER_TASK:
            raise MessageError(f"This task already holds {MAX_MESSAGES_PER_TASK} messages")

        now = utc_now()
        message_id = f"msg_{now.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:10]}"
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "id": message_id,
            "task": task,
            "from": sender,
            "to": recipient,
            "created_at": iso(now),
            "expires_at": iso(now + timedelta(hours=ttl_hours)),
            "request_id": request_id,
            "reply_to": reply_to,
            "pass": pass_count,
            "summary": summary,
            "conclusion": conclusion,
            "evidence": evidence,
            "requires_approval": requires_approval,
            "approval": "pending" if requires_approval else "not-required",
            "content_hash": digest,
        }
        _write_json_atomic(base / "envelopes" / f"{message_id}.json", envelope, exclusive=True)
        _write_json_atomic(
            request_path,
            {
                "schema_version": SCHEMA_VERSION,
                "request_id": request_id,
                "message_id": message_id,
                "content_hash": digest,
                "created_at": iso(now),
            },
            exclusive=True,
        )
        _write_json_atomic(
            base / "status" / f"{message_id}.json",
            {
                "schema_version": SCHEMA_VERSION,
                "message_id": message_id,
                "status": "queued",
                "updated_at": iso(now),
                "updated_by": sender,
            },
        )
        _append_receipt(
            base,
            message_id,
            {"event": "queued", "at": iso(now), "agent": sender, "approval": envelope["approval"]},
        )
        return {
            "status": "queued",
            "message_file": str(base / "envelopes" / f"{message_id}.json"),
            "message": _envelope_view(envelope, "queued", False, envelope["approval"]),
            "notes": "Local file transport only; the receiving agent has not been notified",
        }


def inbox(args: argparse.Namespace) -> dict[str, Any]:
    root = agent_handoff.repo_root(args.project)
    task = clean_task(args.task)
    recipient = clean_agent(args.agent)
    base = _state_base(root, task)
    selection = getattr(args, "status", "active") or "active"
    if selection not in ("active", "all", *STATUSES):
        raise MessageError("Unsupported inbox status filter")

    messages: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in _envelopes(base / "envelopes"):
        try:
            envelope = _load_envelope(base, path.stem)
            status = _status_of(base, envelope["id"])
        except MessageError as exc:
            warnings.append(f"unreadable message skipped: {path.name}: {exc}")
            continue
        if str(envelope.get("to", "")).casefold() != recipient.casefold():
            continue
        expired = _is_expired(envelope, status)
        if selection == "active":
            if status in TERMINAL_STATUSES:
                continue
            if expired and not args.include_expired:
                continue
        elif selection in STATUSES:
            if status != selection:
                continue
            if expired and not args.include_expired:
                continue
        else:  # "all" includes terminal messages but not expired ones unless asked
            if expired and not args.include_expired:
                continue
        messages.append(_envelope_view(envelope, status, expired, _approval_of(base, envelope)))

    messages.sort(key=lambda item: (item["created_at"], item["id"]))
    total = len(messages)
    return {
        "status": "ok",
        "task": task,
        "agent": recipient,
        "count": total,
        "returned": min(total, MAX_INBOX),
        "truncated": total > MAX_INBOX,
        "messages": messages[:MAX_INBOX],
        "warnings": warnings,
        "notes": "Read-only. Acknowledge with message ack; nothing is sent over the network",
    }


def show(args: argparse.Namespace) -> dict[str, Any]:
    root = agent_handoff.repo_root(args.project)
    task = clean_task(args.task)
    message_id = clean_message_id(args.id)
    base = _state_base(root, task)
    envelope = _load_envelope(base, message_id)
    status = _status_of(base, message_id)
    expired = _is_expired(envelope, status)
    return {
        "status": "ok",
        "task": task,
        "message": _envelope_view(envelope, status, expired, _approval_of(base, envelope)),
        "receipts": _read_receipts(base, message_id),
        "notes": "Read-only. Receipts are local append-only records",
    }


def ack(args: argparse.Namespace) -> dict[str, Any]:
    root = agent_handoff.repo_root(args.project)
    task = clean_task(args.task)
    message_id = clean_message_id(args.id)
    recipient = clean_agent(args.agent)
    target = args.status
    if target not in ("taken", "completed", "refused"):
        raise MessageError("Acknowledged status must be taken, completed or refused")
    note = _text(args.note, "note", MAX_NOTE)

    with _Lock(root):
        base = _state_base(root, task)
        envelope = _load_envelope(base, message_id)
        if str(envelope.get("to", "")).casefold() != recipient.casefold():
            raise MessageError("Only the addressed recipient may acknowledge this message")
        status = _status_of(base, message_id)
        expired = _is_expired(envelope, status)
        if expired:
            raise MessageError("This message has expired; ask the sender for a new one")
        if status in TERMINAL_STATUSES:
            if status == target:
                return {
                    "status": "duplicate",
                    "message": _envelope_view(envelope, status, False, _approval_of(base, envelope)),
                    "notes": "This message already has that status",
                }
            raise MessageError(f"Message is already {status}; it cannot become {target}")
        if target == "completed" and envelope.get("requires_approval"):
            if _approval_of(base, envelope) != "approved":
                raise MessageError(
                    "A person must approve this message before completion can be recorded"
                )
        now = utc_now()
        _write_json_atomic(
            base / "status" / f"{message_id}.json",
            {
                "schema_version": SCHEMA_VERSION,
                "message_id": message_id,
                "status": target,
                "updated_at": iso(now),
                "updated_by": recipient,
            },
        )
        _append_receipt(
            base,
            message_id,
            {"event": target, "at": iso(now), "agent": recipient, "note": note},
        )
        return {
            "status": target,
            "message": _envelope_view(envelope, target, False, _approval_of(base, envelope)),
            "notes": "Local receipt recorded; the sender must read it",
        }


def approve(args: argparse.Namespace) -> dict[str, Any]:
    root = agent_handoff.repo_root(args.project)
    task = clean_task(args.task)
    message_id = clean_message_id(args.id)
    approver = clean_agent(args.by, "by")
    note = _text(args.note, "note", MAX_NOTE)

    with _Lock(root):
        base = _state_base(root, task)
        envelope = _load_envelope(base, message_id)
        if not envelope.get("requires_approval"):
            raise MessageError("This message does not require human approval")
        status = _status_of(base, message_id)
        if _is_expired(envelope, status):
            raise MessageError("This message has expired; approval would have no effect")
        if status in TERMINAL_STATUSES:
            raise MessageError(f"Message is already {status}; nothing left to approve")
        path = base / "approvals" / f"{message_id}.json"
        if path.is_file():
            existing = _load_json(path, "Message approval")
            if existing.get("approver") == approver:
                return {
                    "status": "duplicate",
                    "message": _envelope_view(envelope, status, False, "approved"),
                    "approval_file": str(path),
                    "notes": "This approver already approved the message",
                }
            raise MessageError(
                f"This message was already approved by {existing.get('approver')}; "
                "ask that person to confirm"
            )
        now = utc_now()
        record = {
            "schema_version": SCHEMA_VERSION,
            "message_id": message_id,
            "approver": approver,
            "approved_at": iso(now),
            "note": note,
        }
        _write_json_atomic(path, record, exclusive=True)
        _append_receipt(
            base,
            message_id,
            {"event": "approved", "at": iso(now), "agent": approver, "note": note},
        )
        return {
            "status": "approved",
            "message": _envelope_view(envelope, status, False, "approved"),
            "approval_file": str(path),
            "notes": "Human approval recorded locally; it only covers this message",
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    handlers = {
        "send": send,
        "inbox": inbox,
        "show": show,
        "ack": ack,
        "approve": approve,
    }
    action = getattr(args, "action", None)
    if action not in handlers:
        raise MessageError("Unsupported message action")
    return handlers[action](args)


def emit_markdown(result: dict[str, Any]) -> None:
    action = result.get("status", "ok")
    print(f"# Agent message: {action}")
    message = result.get("message")
    if isinstance(message, dict):
        print(f"- id: `{message['id']}`")
        print(f"- task: {message['task']}")
        print(f"- from: {message['from']} -> {message['to']}")
        print(f"- state: {message['status']}")
        print(f"- pass: {message['pass']}")
        print(f"- approval: {message['approval']}")
        print(f"- expires: {message['expires_at']}")
        print(f"- summary: {message['summary']}")
        if message.get("conclusion"):
            print(f"- conclusion: {message['conclusion']}")
        if message.get("evidence"):
            print(f"- evidence: {', '.join(message['evidence'])}")
    if isinstance(result.get("messages"), list):
        print(f"- task: {result['task']}")
        print(f"- agent: {result['agent']}")
        print(f"- messages: {result['count']}")
        for item in result["messages"]:
            print(
                f"  - `{item['id']}` {item['from']} -> {item['to']} | {item['status']} | "
                f"{item['summary']}"
            )
    if result.get("message_file"):
        print(f"- file: `{result['message_file']}`")
    if result.get("truncated"):
        print("- note: inbox output was truncated")
    for warning in result.get("warnings") or []:
        print(f"- warning: {warning}")
    if result.get("notes"):
        print(f"- note: {result['notes']}")


def _common(action: argparse.ArgumentParser, task_required: bool = True) -> None:
    action.add_argument("--project", default=".")
    action.add_argument("--task", required=task_required, help="Stable task ID, e.g. issue-28")
    action.add_argument("--format", choices=("markdown", "json"), default="markdown")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)

    send_parser = actions.add_parser(
        "send", help="Queue one compact handoff message for another agent or person."
    )
    _common(send_parser)
    send_parser.add_argument("--from", dest="from_agent", required=True, help="Sending agent name")
    send_parser.add_argument("--to", required=True, help="Recipient agent or person name")
    send_parser.add_argument("--summary", required=True, help="One-line conclusion to hand over")
    send_parser.add_argument("--conclusion", default="", help="Short conclusion, no transcript")
    send_parser.add_argument("--evidence", action="append", default=[],
                             help="Short pointer to local evidence; may be repeated")
    send_parser.add_argument("--request-id", help="Idempotency key for safe retries")
    send_parser.add_argument("--ttl-hours", type=float, default=DEFAULT_TTL_HOURS,
                             help="Hours before the message expires (default 24)")
    send_parser.add_argument("--pass", dest="pass_count", type=int,
                             help="Chain pass number; replies derive this automatically")
    send_parser.add_argument("--reply-to", help="Message ID being answered")
    send_parser.add_argument("--requires-approval", action="store_true",
                             help="A person must approve before completion is recorded")

    inbox_parser = actions.add_parser(
        "inbox", help="List messages addressed to one agent. Read-only."
    )
    _common(inbox_parser)
    inbox_parser.add_argument("--agent", required=True, help="Recipient agent name")
    inbox_parser.add_argument("--status", choices=("active", "all", *STATUSES), default="active")
    inbox_parser.add_argument("--include-expired", action="store_true",
                              help="Include expired messages that are still open")

    show_parser = actions.add_parser("show", help="Show one message with its local receipts.")
    _common(show_parser)
    show_parser.add_argument("--id", required=True, help="Message ID")

    ack_parser = actions.add_parser("ack", help="Record taken, completed or refused.")
    _common(ack_parser)
    ack_parser.add_argument("--id", required=True, help="Message ID")
    ack_parser.add_argument("--agent", required=True, help="Recipient agent name")
    ack_parser.add_argument("--status", required=True, choices=("taken", "completed", "refused"))
    ack_parser.add_argument("--note", default="", help="Short receipt note")

    approve_parser = actions.add_parser(
        "approve", help="Record a person's approval for a message that requires one."
    )
    _common(approve_parser)
    approve_parser.add_argument("--id", required=True, help="Message ID")
    approve_parser.add_argument("--by", required=True, help="Person recording the approval")
    approve_parser.add_argument("--note", default="", help="What was approved")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = parser.parse_args()
    try:
        result = run(args)
    except (MessageError, agent_handoff.HandoffError) as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_markdown(result)


if __name__ == "__main__":
    main()
