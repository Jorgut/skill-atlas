#!/usr/bin/env python3
"""Minimal MCP (Model Context Protocol) stdio adapter for local agent messages.

Speaks newline-delimited JSON-RPC 2.0 on stdin/stdout and exposes four tools
backed by :mod:`agent_messages`: ``send_message``, ``get_inbox``,
``get_message`` and ``ack_message``. The transport stays local and file based;
nothing is sent over the network and no agent is started.

Approvals intentionally remain CLI-only. There is no MCP approval tool: a
person must run ``skill_atlas.py message approve`` before an approval-gated
message can be completed.

stdout is reserved for protocol messages. Diagnostics and unexpected internal
errors go to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any, Callable

import agent_handoff
import agent_messages

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", PROTOCOL_VERSION)
SERVER_NAME = "skill-atlas-messages"
SERVER_VERSION = "0.7.0-beta"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

INBOX_STATUSES = ("active", "all", "queued", "taken", "completed", "refused")
ACK_STATUSES = ("taken", "completed", "refused")

_TASK_SCHEMA = {
    "type": "string",
    "description": "Stable task ID, e.g. issue-28",
    "minLength": 1,
    "maxLength": 80,
}
_AGENT_SCHEMA = {
    "type": "string",
    "description": "Agent or person name; defaults to the server's --agent value",
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "send_message",
        "description": (
            "Queue one compact local handoff message for another agent or person. "
            "The envelope is written under .agent-state; nothing is sent over the "
            "network and the recipient is not notified."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": _TASK_SCHEMA,
                "to": {"type": "string", "description": "Recipient agent or person name"},
                "summary": {
                    "type": "string",
                    "description": "One-line conclusion to hand over",
                    "maxLength": agent_messages.MAX_SUMMARY,
                },
                "conclusion": {
                    "type": "string",
                    "maxLength": agent_messages.MAX_CONCLUSION,
                },
                "evidence": {
                    "type": "array",
                    "description": "Short local evidence pointers",
                    "items": {"type": "string", "maxLength": agent_messages.MAX_EVIDENCE_LENGTH},
                    "maxItems": agent_messages.MAX_EVIDENCE_ITEMS,
                },
                "request_id": {
                    "type": "string",
                    "description": "Idempotency key for safe retries",
                },
                "ttl_hours": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": agent_messages.MAX_TTL_HOURS,
                },
                "reply_to": {"type": "string", "description": "Message ID being answered"},
                "requires_approval": {
                    "type": "boolean",
                    "description": (
                        "A person must approve with the CLI before completion can be recorded"
                    ),
                },
                "from": {
                    "type": "string",
                    "description": "Sending agent or person name; defaults to the server's --agent value",
                },
            },
            "required": ["task", "to", "summary"],
        },
    },
    {
        "name": "get_inbox",
        "description": (
            "List messages addressed to one agent inside one task. Read-only; "
            "acknowledge with ack_message."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": _TASK_SCHEMA,
                "agent": {
                    "type": "string",
                    "description": "Recipient name to look up; defaults to the server's --agent value",
                },
                "status": {
                    "type": "string",
                    "enum": list(INBOX_STATUSES),
                    "default": "active",
                },
                "include_expired": {"type": "boolean", "default": False},
            },
            "required": ["task"],
        },
    },
    {
        "name": "get_message",
        "description": "Show one message with its local receipt trail. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": _TASK_SCHEMA,
                "id": {"type": "string", "description": "Message ID, e.g. msg_<token>"},
            },
            "required": ["task", "id"],
        },
    },
    {
        "name": "ack_message",
        "description": (
            "Record taken, completed or refused for a message. Only the addressed "
            "recipient may acknowledge; a message that requires approval cannot be "
            "completed until a person approves it with the CLI."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": _TASK_SCHEMA,
                "id": {"type": "string", "description": "Message ID, e.g. msg_<token>"},
                "status": {"type": "string", "enum": list(ACK_STATUSES)},
                "note": {
                    "type": "string",
                    "maxLength": agent_messages.MAX_NOTE,
                },
                "agent": {
                    "type": "string",
                    "description": "Recipient name; defaults to the server's --agent value",
                },
            },
            "required": ["task", "id", "status"],
        },
    },
]

TOOL_NAMES = tuple(tool["name"] for tool in TOOLS)


class RpcError(Exception):
    """Protocol-level JSON-RPC error that becomes an ``error`` response."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_success(result: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _valid_request_id(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (str, int, float))


def _reject_json_constant(token: str) -> Any:
    raise ValueError(f"non-JSON constant in protocol input: {token}")


def _boolean(arguments: dict[str, Any], key: str, default: bool = False) -> bool:
    value = arguments.get(key, default)
    if not isinstance(value, bool):
        raise agent_messages.MessageError(f"--{key.replace('_', '-')} must be true or false")
    return value


def _send_message(project: str, default_agent: str, arguments: dict[str, Any]) -> dict[str, Any]:
    namespace = argparse.Namespace(
        action="send",
        project=project,
        task=arguments.get("task"),
        from_agent=arguments.get("from", default_agent),
        to=arguments.get("to"),
        summary=arguments.get("summary"),
        conclusion=arguments.get("conclusion", ""),
        evidence=arguments.get("evidence"),
        request_id=arguments.get("request_id"),
        ttl_hours=arguments.get("ttl_hours", agent_messages.DEFAULT_TTL_HOURS),
        pass_count=None,
        reply_to=arguments.get("reply_to"),
        requires_approval=_boolean(arguments, "requires_approval"),
    )
    return agent_messages.send(namespace)


def _get_inbox(project: str, default_agent: str, arguments: dict[str, Any]) -> dict[str, Any]:
    namespace = argparse.Namespace(
        action="inbox",
        project=project,
        task=arguments.get("task"),
        agent=arguments.get("agent", default_agent),
        status=arguments.get("status", "active"),
        include_expired=_boolean(arguments, "include_expired"),
    )
    return agent_messages.inbox(namespace)


def _get_message(project: str, default_agent: str, arguments: dict[str, Any]) -> dict[str, Any]:
    del default_agent  # The message's own recipient is recorded on the envelope.
    namespace = argparse.Namespace(
        action="show",
        project=project,
        task=arguments.get("task"),
        id=arguments.get("id"),
    )
    return agent_messages.show(namespace)


def _ack_message(project: str, default_agent: str, arguments: dict[str, Any]) -> dict[str, Any]:
    namespace = argparse.Namespace(
        action="ack",
        project=project,
        task=arguments.get("task"),
        id=arguments.get("id"),
        agent=arguments.get("agent", default_agent),
        status=arguments.get("status"),
        note=arguments.get("note", ""),
    )
    return agent_messages.ack(namespace)


_TOOL_HANDLERS: dict[str, Callable[[str, str, dict[str, Any]], dict[str, Any]]] = {
    "send_message": _send_message,
    "get_inbox": _get_inbox,
    "get_message": _get_message,
    "ack_message": _ack_message,
}


def _initialize(params: Any) -> dict[str, Any]:
    if params is not None and not isinstance(params, dict):
        raise RpcError(INVALID_PARAMS, "Invalid params: initialize expects an object")
    requested = params.get("protocolVersion") if isinstance(params, dict) else None
    # Answer with a version this server supports; never echo an unknown one back
    # as if it were supported.
    protocol_version = (
        requested
        if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS
        else PROTOCOL_VERSION
    )
    return {
        "protocolVersion": protocol_version,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    }


def _call_tool(params: Any, *, project: str, agent: str) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise RpcError(INVALID_PARAMS, "Invalid params: tools/call expects an object")
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise RpcError(INVALID_PARAMS, "Invalid params: tools/call requires a tool name")
    arguments = params.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise RpcError(INVALID_PARAMS, "Invalid params: tool arguments must be an object")
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        raise RpcError(INVALID_PARAMS, f"Invalid params: unknown tool: {name}")
    try:
        result = handler(project, agent, arguments)
    except (agent_messages.MessageError, agent_handoff.HandoffError) as exc:
        # Domain refusals are tool results, not JSON-RPC errors.
        return _tool_error(str(exc))
    except Exception as exc:  # pragma: no cover - defensive against unexpected bugs
        traceback.print_exc(file=sys.stderr)
        return _tool_error(f"Internal tool error: {exc}")
    return _tool_success(result)


def handle_request(payload: Any, *, project: str, agent: str) -> dict[str, Any] | None:
    """Handle one decoded JSON-RPC message; return a response dict or None."""

    if not isinstance(payload, dict):
        return _error(None, INVALID_REQUEST, "Invalid Request: expected a JSON object")
    request_id = payload.get("id")
    is_notification = "id" not in payload
    if not is_notification and not _valid_request_id(request_id):
        return _error(None, INVALID_REQUEST, "Invalid Request: id must be a string or number")
    if payload.get("jsonrpc") not in (None, "2.0"):
        if is_notification:
            return None
        return _error(request_id, INVALID_REQUEST, 'Invalid Request: jsonrpc must be "2.0"')
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        if is_notification:
            return None
        return _error(request_id, INVALID_REQUEST, "Invalid Request: method must be a string")
    params = payload.get("params")
    try:
        if method == "initialize":
            result = _initialize(params)
        elif method == "notifications/initialized":
            return None
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = _call_tool(params, project=project, agent=agent)
        else:
            if is_notification:
                return None
            return _error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
    except RpcError as exc:
        if is_notification:
            return None
        return _error(request_id, exc.code, exc.message)
    except Exception as exc:  # pragma: no cover - defensive
        traceback.print_exc(file=sys.stderr)
        if is_notification:
            return None
        return _error(request_id, INTERNAL_ERROR, f"Internal error: {exc}")
    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _write_response(payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _configure_streams() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):  # pragma: no cover - exotic streams
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except (AttributeError, ValueError, OSError):  # pragma: no cover - exotic streams
        pass


def serve(project: str, agent: str) -> int:
    """Run the line-delimited JSON-RPC loop until stdin closes."""

    _configure_streams()
    while True:
        try:
            line = sys.stdin.readline()
        except (OSError, ValueError):  # pragma: no cover - closed stdin
            break
        if not line:
            break
        if not line.strip():
            continue
        try:
            payload = json.loads(line, parse_constant=_reject_json_constant)
        except ValueError:
            try:
                _write_response(_error(None, PARSE_ERROR, "Parse error"))
            except (BrokenPipeError, OSError):  # pragma: no cover - client went away
                break
            continue
        response = handle_request(payload, project=project, agent=agent)
        if response is None:
            continue
        try:
            _write_response(response)
        except (BrokenPipeError, OSError):  # pragma: no cover - client went away
            break
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Expose Skill Atlas local agent messages over the Model Context Protocol "
            "(stdio, newline-delimited JSON-RPC 2.0)."
        )
    )
    parser.add_argument(
        "--project", default=".", help="Project or Git checkout to read and write messages in"
    )
    parser.add_argument(
        "--agent", required=True, help="Default sending/recipient agent for tool calls"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return serve(args.project, args.agent)
    except KeyboardInterrupt:  # pragma: no cover - interactive Ctrl-C
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
