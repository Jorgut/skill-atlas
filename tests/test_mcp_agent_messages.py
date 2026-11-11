"""Subprocess tests for the MCP stdio adapter over local agent messages."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "mcp_agent_messages.py"
READ_TIMEOUT = 10.0
_OMIT = object()


def git(directory: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(directory), *argv], check=True, stdout=subprocess.PIPE)


class StdioServer:
    """One MCP server subprocess plus a small synchronous stdio client."""

    def __init__(self, project: Path, agent: str) -> None:
        self.process = subprocess.Popen(
            [sys.executable, str(SERVER), "--project", str(project), "--agent", agent],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._next_id = 0
        self._aborted = False
        self._reader = threading.Thread(target=self._pump_stdout, daemon=True)
        self._reader.start()

    def _pump_stdout(self) -> None:
        try:
            for line in self.process.stdout:
                self._lines.put(line)
        except (OSError, ValueError):  # pragma: no cover - process teardown race
            pass
        finally:
            self._lines.put(None)

    def send_raw(self, text: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()

    def _fail(self, message: str) -> None:
        self._aborted = True
        try:
            self.process.kill()
            self.process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):  # pragma: no cover - defensive
            pass
        stderr = self._diagnostics()
        raise AssertionError(f"{message}\nserver stderr:\n{stderr}")

    def _diagnostics(self) -> str:
        self._reader.join(timeout=5)
        if self.process.stderr is None:
            return ""
        try:
            return self.process.stderr.read()
        except (OSError, ValueError):  # pragma: no cover - defensive
            return ""

    def _close_streams(self) -> None:
        self._reader.join(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except (OSError, ValueError):  # pragma: no cover - defensive
                pass

    def read_response(self, timeout: float = READ_TIMEOUT) -> dict[str, Any]:
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self._fail(f"timed out after {timeout}s waiting for an MCP response")
        if line is None:
            self._fail("MCP server closed stdout before sending a response")
        try:
            payload = json.loads(line)
        except ValueError as exc:  # pragma: no cover - would mean protocol corruption
            self._fail(f"stdout carried non-JSON output: {line!r} ({exc})")
        if not isinstance(payload, dict):
            self._fail(f"stdout carried a non-object JSON-RPC message: {line!r}")
        return payload

    def request(
        self, method: str, params: Any = _OMIT, request_id: Any = None
    ) -> dict[str, Any]:
        if request_id is None:
            self._next_id += 1
            request_id = self._next_id
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not _OMIT:
            message["params"] = params
        self.send_raw(json.dumps(message))
        return self.read_response()

    def notify(self, method: str, params: Any = _OMIT) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not _OMIT:
            message["params"] = params
        self.send_raw(json.dumps(message))

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        response = self.request("tools/call", params)
        if "error" in response:
            raise AssertionError(f"unexpected JSON-RPC error for {name}: {response['error']}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise AssertionError(f"tools/call for {name} returned no result object")
        return result

    def tool_json(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.call_tool(name, arguments)
        if result.get("isError"):
            raise AssertionError(f"{name} failed: {_text_of(result)}")
        return json.loads(_text_of(result))

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                assert self.process.stdin is not None
                self.process.stdin.close()
            except (OSError, ValueError):  # pragma: no cover - defensive
                pass
        try:
            self.process.wait(timeout=READ_TIMEOUT)
        except subprocess.TimeoutExpired:  # pragma: no cover - would mean a hung server
            self.process.kill()
            self.process.wait(timeout=5)
        stderr = self._diagnostics()
        returncode = self.process.returncode
        self._close_streams()
        if returncode != 0 and not self._aborted:  # pragma: no cover - server crashes
            raise AssertionError(
                f"server exited with {returncode}\nserver stderr:\n{stderr}"
            )


def _text_of(result: dict[str, Any]) -> str:
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise AssertionError(f"tool result has no content: {result}")
    item = content[0]
    if not isinstance(item, dict) or item.get("type") != "text":
        raise AssertionError(f"tool result content is not text: {item}")
    return item["text"]


class McpAgentMessageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        git(self.project, "init", "-q")
        git(self.project, "config", "user.email", "test@example.invalid")
        git(self.project, "config", "user.name", "Tests")
        (self.project / "README.md").write_text("# test\n", encoding="utf-8")
        git(self.project, "add", "README.md")
        git(self.project, "commit", "-qm", "initial")

    def start(self, agent: str = "Claude Code") -> StdioServer:
        server = StdioServer(self.project, agent)
        self.addCleanup(server.close)
        return server

    def test_initialize_handshake_echoes_protocol_and_advertises_tools(self) -> None:
        server = self.start()
        response = server.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "unittest", "version": "1.0"},
            },
            request_id="init-1",
        )
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], "init-1")
        self.assertNotIn("error", response)
        result = response["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertIn("tools", result["capabilities"])
        self.assertIsInstance(result["capabilities"]["tools"], dict)
        self.assertEqual(result["serverInfo"]["name"], "skill-atlas-messages")
        self.assertEqual(result["serverInfo"]["version"], "0.7.0-beta")

        server.notify("notifications/initialized")
        ping = server.request("ping", request_id="ping-1")
        self.assertEqual(ping["id"], "ping-1")
        self.assertEqual(ping["result"], {})

    def test_initialize_falls_back_to_current_protocol_version(self) -> None:
        server = self.start()
        for params in ({}, {"protocolVersion": 42}, {"protocolVersion": ""}):
            with self.subTest(params=params):
                result = server.request("initialize", params)["result"]
                self.assertEqual(result["protocolVersion"], "2025-06-18")

    def test_tools_list_exposes_exactly_four_tools(self) -> None:
        server = self.start()
        tools = server.request("tools/list")["result"]["tools"]
        names = [tool["name"] for tool in tools]
        self.assertEqual(len(tools), 4)
        self.assertEqual(
            set(names), {"send_message", "get_inbox", "get_message", "ack_message"}
        )
        self.assertFalse(any("approve" in name.casefold() for name in names))
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertTrue(tool["description"])
        by_name = {tool["name"]: tool["inputSchema"] for tool in tools}
        self.assertEqual(
            set(by_name["send_message"]["required"]), {"task", "to", "summary"}
        )
        self.assertIn("from", by_name["send_message"]["properties"])
        self.assertEqual(set(by_name["get_inbox"]["required"]), {"task"})
        self.assertEqual(
            by_name["get_inbox"]["properties"]["status"]["enum"],
            ["active", "all", "queued", "taken", "completed", "refused"],
        )
        self.assertEqual(set(by_name["get_message"]["required"]), {"task", "id"})
        self.assertEqual(
            by_name["ack_message"]["properties"]["status"]["enum"],
            ["taken", "completed", "refused"],
        )

    def test_send_inbox_ack_roundtrip_over_stdio(self) -> None:
        server = self.start("Claude Code")
        sent = server.tool_json(
            "send_message",
            {
                "task": "issue-42",
                "from": "Codex",
                "to": "Claude Code",
                "summary": "Review the camera diff",
                "conclusion": "Camera works; selection remains",
                "evidence": ["src/camera.ts"],
                "request_id": "req-roundtrip",
            },
        )
        self.assertEqual(sent["status"], "queued")
        message = sent["message"]
        self.assertEqual(message["from"], "Codex")
        self.assertEqual(message["to"], "Claude Code")
        self.assertEqual(message["pass"], 1)
        self.assertEqual(message["approval"], "not-required")

        inbox = server.tool_json("get_inbox", {"task": "issue-42"})
        self.assertEqual(inbox["count"], 1)
        item = inbox["messages"][0]
        self.assertEqual(item["id"], message["id"])
        self.assertEqual(item["summary"], "Review the camera diff")
        self.assertEqual(item["evidence"], ["src/camera.ts"])

        acked = server.tool_json(
            "ack_message",
            {"task": "issue-42", "id": message["id"], "status": "taken", "note": "picked up"},
        )
        self.assertEqual(acked["status"], "taken")

        shown = server.tool_json(
            "get_message", {"task": "issue-42", "id": message["id"]}
        )
        self.assertEqual(shown["message"]["status"], "taken")
        self.assertEqual(
            [receipt["event"] for receipt in shown["receipts"]], ["queued", "taken"]
        )
        self.assertEqual(shown["receipts"][-1]["note"], "picked up")

    def test_default_agent_is_used_for_sender_recipient_and_ack(self) -> None:
        server = self.start("Codex")
        first = server.tool_json(
            "send_message", {"task": "issue-7", "to": "Claude Code", "summary": "Check defaults"}
        )
        self.assertEqual(first["message"]["from"], "Codex")

        second = server.tool_json(
            "send_message",
            {
                "task": "issue-7",
                "from": "Claude Code",
                "to": "Codex",
                "summary": "Defaults look right",
                "reply_to": first["message"]["id"],
            },
        )
        self.assertEqual(second["message"]["pass"], 2)

        inbox = server.tool_json("get_inbox", {"task": "issue-7"})
        self.assertEqual(inbox["agent"], "Codex")
        self.assertEqual(inbox["count"], 1)
        self.assertEqual(inbox["messages"][0]["id"], second["message"]["id"])

        acked = server.tool_json(
            "ack_message",
            {"task": "issue-7", "id": second["message"]["id"], "status": "completed"},
        )
        self.assertEqual(acked["status"], "completed")

    def test_tool_domain_errors_return_is_error_results(self) -> None:
        server = self.start("Claude Code")
        missing = server.call_tool(
            "get_message",
            {"task": "issue-42", "id": "msg_20260101T000000_0000000000"},
        )
        self.assertIs(missing["isError"], True)
        self.assertIn("not found", _text_of(missing).casefold())

        sent = server.tool_json(
            "send_message",
            {
                "task": "issue-42",
                "from": "Codex",
                "to": "Other Agent",
                "summary": "Do not acknowledge me",
            },
        )
        stolen = server.call_tool(
            "ack_message",
            {"task": "issue-42", "id": sent["message"]["id"], "status": "taken"},
        )
        self.assertIs(stolen["isError"], True)
        self.assertIn("recipient", _text_of(stolen).casefold())

        bad_status = server.call_tool(
            "ack_message",
            {"task": "issue-42", "id": sent["message"]["id"], "status": "approved"},
        )
        self.assertIs(bad_status["isError"], True)

        missing_summary = server.call_tool(
            "send_message", {"task": "issue-42", "to": "Codex"}
        )
        self.assertIs(missing_summary["isError"], True)

        self.assertEqual(server.request("ping")["result"], {})

    def test_unknown_method_returns_method_not_found(self) -> None:
        server = self.start()
        server.notify("notifications/initialized")
        server.notify("notifications/unknown")
        response = server.request(
            "approve_message", {"task": "issue-42"}, request_id="unknown-1"
        )
        self.assertEqual(response["id"], "unknown-1")
        self.assertNotIn("result", response)
        self.assertEqual(response["error"]["code"], -32601)
        # Unknown notifications produce no output, so the next response is the ping.
        ping = server.request("ping", request_id="after-unknown")
        self.assertEqual(ping["id"], "after-unknown")

    def test_malformed_json_returns_parse_error_and_keeps_serving(self) -> None:
        server = self.start()
        server.send_raw('{"jsonrpc": "2.0", "id": 1, "method": "tools/list"')
        parse_error = server.read_response()
        self.assertIsNone(parse_error["id"])
        self.assertEqual(parse_error["error"]["code"], -32700)
        self.assertNotIn("result", parse_error)

        server.send_raw("   ")  # Blank lines are ignored, not answered.
        ping = server.request("ping", request_id="still-alive")
        self.assertEqual(ping["id"], "still-alive")
        self.assertEqual(ping["result"], {})

    def test_invalid_params_return_invalid_params(self) -> None:
        server = self.start()
        cases: list[tuple[str, Any]] = [
            ("tools/call", {}),
            ("tools/call", {"name": "get_inbox", "arguments": []}),
            ("tools/call", {"name": "approve_message", "arguments": {}}),
            ("initialize", "not-an-object"),
        ]
        for method, params in cases:
            with self.subTest(method=method, params=params):
                response = server.request(method, params)
                self.assertEqual(response["error"]["code"], -32602)
                self.assertNotIn("result", response)
        self.assertEqual(server.request("ping")["result"], {})

    def test_approval_gate_blocks_completion_and_no_approve_tool_exists(self) -> None:
        server = self.start("Claude Code")
        sent = server.tool_json(
            "send_message",
            {
                "task": "issue-42",
                "from": "Codex",
                "to": "Claude Code",
                "summary": "Merge needs a person",
                "requires_approval": True,
            },
        )
        self.assertEqual(sent["message"]["approval"], "pending")
        blocked = server.call_tool(
            "ack_message",
            {"task": "issue-42", "id": sent["message"]["id"], "status": "completed"},
        )
        self.assertIs(blocked["isError"], True)
        self.assertIn("approve", _text_of(blocked).casefold())

        taken = server.tool_json(
            "ack_message",
            {"task": "issue-42", "id": sent["message"]["id"], "status": "taken"},
        )
        self.assertEqual(taken["message"]["status"], "taken")

        tools = server.request("tools/list")["result"]["tools"]
        names = [tool["name"] for tool in tools]
        self.assertEqual(len(names), 4)
        self.assertNotIn("approve_message", names)
        self.assertFalse(any("approve" in name.casefold() for name in names))


if __name__ == "__main__":
    unittest.main()
