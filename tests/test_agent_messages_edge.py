"""Adversarial edge-case tests for the local agent-message transport and MCP adapter.

This module started as the adversarial review of the feature and now stays as a
regression guard. It contains two kinds of tests:

* ``test_defect_*`` methods reproduce defects the review found in the first
  implementation. Every one was fixed before merge; each docstring keeps the
  reproduction so the guard cannot silently regress, and the test name keeps the
  historical defect label.
* Every other ``test_*`` method pins down behaviour the review verified sound.

Run::

    python3 -m unittest tests.test_agent_messages_edge -v
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import agent_messages  # noqa: E402
import mcp_agent_messages  # noqa: E402

MCP_SERVER = SCRIPTS / "mcp_agent_messages.py"
READ_TIMEOUT = 10.0
_OMIT = object()


def git(directory: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(directory), *argv], check=True, stdout=subprocess.PIPE)


class _RepoTestCase(unittest.TestCase):
    """One disposable Git repository per test."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.base = Path(self._temp.name)
        self.project = self.base / "repo"
        self.project.mkdir()
        git(self.project, "init", "-q")
        git(self.project, "config", "user.email", "test@example.invalid")
        git(self.project, "config", "user.name", "Tests")
        (self.project / "README.md").write_text("# test\n", encoding="utf-8")
        git(self.project, "add", "README.md")
        git(self.project, "commit", "-qm", "initial")

    # -- argparse.Namespace helpers mirroring the CLI ----------------------

    def options(self, action: str, **overrides: Any) -> argparse.Namespace:
        params: dict[str, Any] = {
            "action": action,
            "project": str(self.project),
            "task": "issue-28",
            "format": "json",
        }
        if action == "send":
            params.update(
                from_agent="Codex",
                to="Claude Code",
                summary="Review the camera diff",
                conclusion="Camera works; selection remains",
                evidence=["src/camera.ts"],
                request_id=None,
                ttl_hours=agent_messages.DEFAULT_TTL_HOURS,
                pass_count=None,
                reply_to=None,
                requires_approval=False,
            )
        elif action == "inbox":
            params.update(agent="Claude Code", status="active", include_expired=False)
        elif action in ("show", "ack", "approve"):
            params.update(id="msg_20260101T000000_0000000000")
        if action == "ack":
            params.update(agent="Claude Code", status="taken", note="")
        if action == "approve":
            params.update(by="AJ", note="")
        params.update(overrides)
        return argparse.Namespace(**params)

    def send(self, **overrides: Any) -> dict[str, Any]:
        return agent_messages.send(self.options("send", **overrides))

    def inbox(self, **overrides: Any) -> dict[str, Any]:
        return agent_messages.inbox(self.options("inbox", **overrides))

    def show(self, message_id: str, **overrides: Any) -> dict[str, Any]:
        return agent_messages.show(self.options("show", id=message_id, **overrides))

    def ack(self, message_id: str, **overrides: Any) -> dict[str, Any]:
        return agent_messages.ack(self.options("ack", id=message_id, **overrides))

    def approve(self, message_id: str, **overrides: Any) -> dict[str, Any]:
        return agent_messages.approve(self.options("approve", id=message_id, **overrides))

    def state_dir(self, task: str = "issue-28") -> Path:
        return self.project / ".agent-state" / "messages" / task

    def envelope_path(self, message_id: str, task: str = "issue-28") -> Path:
        return self.state_dir(task) / "envelopes" / f"{message_id}.json"

    def rewrite_envelope(self, message_id: str, **changes: Any) -> None:
        path = self.envelope_path(message_id)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope.update(changes)
        path.write_text(json.dumps(envelope), encoding="utf-8")

    def start_mcp_server(self, agent: str = "Claude Code") -> "_McpServer":
        server = _McpServer(self.project, agent)
        self.addCleanup(server.close)
        return server


# ---------------------------------------------------------------------------
# Confirmed defects.  Each test must keep failing until the defect is fixed.
# ---------------------------------------------------------------------------


class ConfirmedDefectTests(_RepoTestCase):
    """Guards for defects found in review and fixed before merge."""

    def test_defect_d1a_reply_retry_is_refused_once_the_parent_expires(self) -> None:
        """Regression guard (defect fixed before merge). Was DEFECT D1 (medium): idempotent retries are validated *after* the reply chain.

        docs/agent-messaging.md promises "``--request-id`` makes retries safe.
        Repeating the same request ID with the same content returns ``duplicate``
        and the original message".  ``send()`` validates the parent status/expiry
        and derives the pass (scripts/agent_messages.py:348-357) *before* it
        looks up the request-id record (scripts/agent_messages.py:359-372).

        Reproduction: send a parent with a very short TTL, send one reply with
        ``request_id="reply-retry"``, wait for the parent to expire, then retry
        the identical reply.  The retry raises "The message being replied to has
        expired" instead of returning ``duplicate``.
        """

        parent = self.send(ttl_hours=0.0001, summary="Parent with short TTL")
        parent_id = parent["message"]["id"]
        first = self.send(
            from_agent="Claude Code",
            to="Codex",
            summary="Reply queued before the parent expired",
            reply_to=parent_id,
            request_id="reply-retry",
        )
        self.assertEqual(first["status"], "queued")
        time.sleep(0.6)  # parent TTL is 0.36 s

        try:
            retry = self.send(
                from_agent="Claude Code",
                to="Codex",
                summary="Reply queued before the parent expired",
                reply_to=parent_id,
                request_id="reply-retry",
            )
        except agent_messages.MessageError as exc:
            self.fail(f"safe retry was refused after the parent expired: {exc}")
        self.assertEqual(retry["status"], "duplicate")
        self.assertEqual(retry["message"]["id"], first["message"]["id"])

    def test_defect_d1b_reply_retry_is_refused_once_the_parent_is_refused(self) -> None:
        """Regression guard (defect fixed before merge). Was DEFECT D1 (medium), second trigger: a refused parent blocks the retry.

        Same ordering bug as D1a: after the recipient refuses the parent, an
        identical retry of an already-queued reply raises "The message being
        replied to was refused" (scripts/agent_messages.py:351-352) instead of
        returning the original message as the retry contract promises.
        """

        parent = self.send(summary="Parent to be refused")
        parent_id = parent["message"]["id"]
        first = self.send(
            from_agent="Claude Code",
            to="Codex",
            summary="Reply sent before the parent was refused",
            reply_to=parent_id,
            request_id="reply-retry-refused",
        )
        self.assertEqual(first["status"], "queued")
        self.ack(parent_id, status="refused", note="declined")

        try:
            retry = self.send(
                from_agent="Claude Code",
                to="Codex",
                summary="Reply sent before the parent was refused",
                reply_to=parent_id,
                request_id="reply-retry-refused",
            )
        except agent_messages.MessageError as exc:
            self.fail(f"safe retry was refused after the parent was refused: {exc}")
        self.assertEqual(retry["status"], "duplicate")
        self.assertEqual(retry["message"]["id"], first["message"]["id"])

    def test_defect_d2_request_id_digest_ignores_the_chain_pass(self) -> None:
        """Regression guard (defect fixed before merge). Was DEFECT D2 (low): the idempotency digest omits ``pass``.

        The digest payload (scripts/agent_messages.py:334-345) covers task,
        sender, recipient, summary, conclusion, evidence, reply_to,
        requires_approval and ttl_hours but not the stored ``pass``.  A top-level
        message may set ``--pass`` explicitly (``_next_pass`` returns
        ``requested or 1``, scripts/agent_messages.py:305-307), so two messages
        whose envelopes differ only in ``pass`` hash identically.

        Reproduction: send with ``request_id="pass-digest", pass=1``, then send
        different content (``pass=2``) under the same request ID.  docs promise
        that "reusing the request ID with different content is refused", but the
        second send returns ``duplicate`` and silently hands back the pass-1
        message.
        """

        first = self.send(request_id="pass-digest", pass_count=1, summary="Pass one")
        self.assertEqual(first["message"]["pass"], 1)
        with self.assertRaises(agent_messages.MessageError):
            self.send(request_id="pass-digest", pass_count=2, summary="Pass one")

    def test_defect_d3_status_all_ignores_include_expired(self) -> None:
        """Regression guard (defect fixed before merge). Was DEFECT D3 (low): ``inbox --status all`` returns expired messages unconditionally.

        docs/agent-messaging.md says the ``active`` view "hides terminal
        (``completed``, ``refused``) and expired messages" and that
        "``--include-expired`` includes expired open messages".  The
        ``include_expired`` switch is honoured for ``active`` and for each
        concrete status, but the ``all`` branch (scripts/agent_messages.py:453-462)
        has no expiry filter at all, so expired messages leak into the default
        ``all`` view.

        Reproduction: queue a message with a 0.0001 h TTL, wait, then call
        ``inbox(status="all")`` with ``include_expired=False``.  It returns the
        expired message (count 1) even though nothing asked for expired records.
        """

        self.send(ttl_hours=0.0001, summary="Will expire")
        time.sleep(0.6)

        without_flag = self.inbox(status="all")
        self.assertEqual(
            without_flag["count"],
            0,
            "expired open messages must stay hidden until --include-expired",
        )
        with_flag = self.inbox(status="all", include_expired=True)
        self.assertEqual(with_flag["count"], 1)
        self.assertTrue(with_flag["messages"][0]["expired"])

    def test_defect_d4_mcp_initialize_echoes_unsupported_protocol_versions(self) -> None:
        """Regression guard (defect fixed before merge). Was DEFECT D4 (low): MCP ``initialize`` echoes any requested protocol version.

        ``_initialize`` (scripts/mcp_agent_messages.py:262-273) returns the
        client's ``protocolVersion`` verbatim whenever it is a non-empty string.
        The MCP lifecycle specification requires the server to answer with a
        version it supports (the same version only when supported, otherwise its
        latest supported version).  A client asking for ``"9999-12-31"`` is told
        the server speaks ``"9999-12-31"``.

        Reproduction: send ``initialize`` with ``protocolVersion: "9999-12-31"``;
        the result must report ``mcp_agent_messages.PROTOCOL_VERSION``.
        """

        server = self.start_mcp_server()
        response = server.request(
            "initialize",
            {"protocolVersion": "9999-12-31", "capabilities": {}, "clientInfo": {"name": "t"}},
            request_id="init-bogus",
        )
        self.assertNotIn("error", response)
        self.assertEqual(
            response["result"]["protocolVersion"],
            mcp_agent_messages.PROTOCOL_VERSION,
            "unsupported protocol versions must not be echoed back as if supported",
        )

    def test_defect_d5_mcp_request_ids_break_jsonrpc_and_stdout_json(self) -> None:
        """Regression guard (defect fixed before merge). Was DEFECT D5 (low): malformed JSON-RPC request ids are accepted, and NaN leaks to stdout.

        * ``json.loads`` in ``serve`` runs with default ``allow_nan=True``
          (scripts/mcp_agent_messages.py:378), so the non-JSON token ``NaN`` is
          accepted as a request id.  ``_write_response`` then serialises it with
          ``json.dumps`` defaults (scripts/mcp_agent_messages.py:347-350),
          writing ``{"...","id":NaN,...}`` to stdout: not valid JSON, so a strict
          client parser breaks on protocol output.
        * A request id that is an array/object is not a valid JSON-RPC id, so the
          server must answer ``-32600`` with ``id: null`` (scripts/mcp_agent_messages.py:304-316
          never validates the id type and simply echoes it).

        Reproduction: feed ``{"jsonrpc":"2.0","id":NaN,"method":"ping"}`` and
        ``{"jsonrpc":"2.0","id":[1,2],"method":"ping"}``; the first stdout line
        is unparsable JSON, the second returns a ``result`` with an array id.
        """

        def reject_constant(token: str) -> Any:
            raise ValueError(f"non-JSON constant in protocol output: {token}")

        server = self.start_mcp_server()
        try:
            with self.subTest(case="NaN request id"):
                server.send_raw('{"jsonrpc":"2.0","id":NaN,"method":"ping"}')
                raw = server.read_raw()
                try:
                    payload = json.loads(raw, parse_constant=reject_constant)
                except ValueError as exc:
                    self.fail(f"MCP stdout was not valid JSON: {raw!r} ({exc})")
                self.assertIsNone(payload["id"])
                self.assertIn("error", payload)
                self.assertIn(payload["error"]["code"], (-32700, -32600))

            with self.subTest(case="object request id"):
                server.send_raw('{"jsonrpc":"2.0","id":{"bad":1},"method":"ping"}')
                payload = json.loads(server.read_raw())
                self.assertNotIn("result", payload)
                self.assertIsNone(payload["id"])
                self.assertEqual(payload["error"]["code"], -32600)

            # The server must survive both malformed requests.
            response = server.request("ping", request_id="after-bad-ids")
            self.assertEqual(response["result"], {})
        finally:
            server.close()

    def test_defect_d6_symlinked_state_directory_writes_outside_the_git_root(self) -> None:
        """Regression guard (defect fixed before merge). Was DEFECT D6 (low): message state escapes the checkout through a symlink.

        docs/agent-messaging.md: "Messages are written under
        ``.agent-state/messages/<task>/`` inside the receiving project's Git
        root."  The transport joins ``repo_root() / STATE_DIR / ...`` and writes
        there without checking for symlinks (scripts/agent_messages.py:158-160,
        332, 397-418).  A repository that ships ``.agent-state`` (or
        ``.agent-state/messages``) as a symlink therefore redirects envelopes,
        status, request and receipt files outside the Git root the moment an
        agent queues a message.

        Reproduction: ``git init`` a repository, replace ``.agent-state`` with a
        symlink to a directory outside the checkout, run ``message send``.  The
        command succeeds and every state file resolves outside the Git root.
        Refusing the symlink outright would also satisfy this test.
        """

        outside = self.base / "outside-state"
        outside.mkdir()
        os.symlink(outside, self.project / ".agent-state")
        try:
            sent = self.send(summary="Queue through a symlinked state directory")
        except agent_messages.MessageError:
            return  # Refusing the symlinked state directory is an acceptable fix.
        self.assertEqual(sent["status"], "queued")

        created = [path for path in outside.rglob("*") if path.is_file()]
        self.assertTrue(created, "send() reported success but wrote no state")
        git_root = self.project.resolve()
        for path in created:
            self.assertIn(
                git_root,
                path.resolve().parents,
                f"message state escaped the Git root: {path.resolve()}",
            )

    def test_defect_d7_interrupted_send_dead_ends_the_idempotency_record(self) -> None:
        """Regression guard (defect fixed before merge). Was DEFECT D7 (low): the request-id record is written before the message status.

        ``send`` persists the envelope, then the idempotency record, then the
        status file (scripts/agent_messages.py:397-418).  A crash between the
        last two writes leaves a request record pointing at an envelope that has
        no status.  The documented retry then dies in ``_status_of``
        (scripts/agent_messages.py:360-366): "Message status is missing".  The
        message can never be acknowledged and the retry can never return the
        original message, so the lost-response retry contract is broken in that
        window.

        Reproduction: send with ``request_id="crash-1"``, delete the generated
        ``status/<id>.json`` (exactly the on-disk shape of that crash), retry
        the identical send.  The retry must not raise; it must return the
        original message as ``duplicate`` (writing the missing status back is an
        acceptable fix).
        """

        first = self.send(request_id="crash-1", summary="Interrupted send")
        message_id = first["message"]["id"]
        status_path = self.state_dir() / "status" / f"{message_id}.json"
        status_path.unlink()  # simulate a crash after the request record was persisted
        self.assertFalse(status_path.exists())

        try:
            retry = self.send(request_id="crash-1", summary="Interrupted send")
        except agent_messages.MessageError as exc:
            self.fail(f"retry after the interrupted send raised instead of recovering: {exc}")
        self.assertEqual(retry["status"], "duplicate")
        self.assertEqual(retry["message"]["id"], message_id)


# ---------------------------------------------------------------------------
# Regression coverage for areas the review verified as sound.
# ---------------------------------------------------------------------------


class TransportRegressionTests(_RepoTestCase):
    def test_concurrent_retries_with_one_request_id_create_one_message(self) -> None:
        """Concurrent identical sends collapse to exactly one envelope."""

        barrier = threading.Barrier(8)
        results: list[dict[str, Any]] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker() -> None:
            barrier.wait()
            try:
                result = self.send(request_id="concurrent-same", summary="One message only")
            except Exception as exc:  # pragma: no cover - surfaced by assertions
                with lock:
                    errors.append(exc)
                return
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 8)
        self.assertEqual({item["message"]["id"] for item in results}.__len__(), 1)
        self.assertEqual(sum(item["status"] == "queued" for item in results), 1)
        envelopes = list((self.state_dir() / "envelopes").glob("msg_*.json"))
        self.assertEqual(len(envelopes), 1)

    def test_concurrent_conflicting_request_id_is_refused_with_one_envelope(self) -> None:
        """Concurrent same request ID + different content keeps one message."""

        barrier = threading.Barrier(8)
        results: list[dict[str, Any]] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            barrier.wait()
            try:
                result = self.send(request_id="concurrent-different", summary=f"content {index}")
            except agent_messages.MessageError as exc:
                with lock:
                    errors.append(exc)
                return
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "queued")
        self.assertEqual(len(errors), 7)
        envelopes = list((self.state_dir() / "envelopes").glob("msg_*.json"))
        self.assertEqual(len(envelopes), 1)

    def test_concurrent_terminal_acks_leave_one_terminal_state(self) -> None:
        """``completed`` and ``refused`` racing each other cannot both apply."""

        message_id = self.send(summary="Racy termination")["message"]["id"]
        barrier = threading.Barrier(2)
        results: list[dict[str, Any]] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker(status: str) -> None:
            barrier.wait()
            try:
                result = self.ack(message_id, status=status)
            except agent_messages.MessageError as exc:
                with lock:
                    errors.append(exc)
                return
            with lock:
                results.append(result)

        threads = [
            threading.Thread(target=worker, args=("completed",)),
            threading.Thread(target=worker, args=("refused",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(results), 1)
        final = self.show(message_id)
        self.assertIn(final["message"]["status"], ("completed", "refused"))
        self.assertEqual(results[0]["status"], final["message"]["status"])
        events = [receipt["event"] for receipt in final["receipts"]]
        self.assertEqual(len(events), 2)  # queued + exactly one terminal transition
        self.assertEqual(events[0], "queued")

    def test_request_ids_and_message_ids_are_scoped_per_task(self) -> None:
        first = self.send(task="issue-1", request_id="same-key", summary="Same key")
        second = self.send(task="issue-2", request_id="same-key", summary="Same key")
        self.assertEqual(first["status"], "queued")
        self.assertEqual(second["status"], "queued")
        self.assertNotEqual(first["message"]["id"], second["message"]["id"])

        with self.assertRaises(agent_messages.MessageError):
            self.show(first["message"]["id"], task="issue-2")
        with self.assertRaises(agent_messages.MessageError):
            self.ack(first["message"]["id"], task="issue-2", status="taken")

    def test_duplicate_retry_reports_the_current_state(self) -> None:
        sent = self.send(request_id="stateful-retry", summary="Retry after ack")
        message_id = sent["message"]["id"]
        self.ack(message_id, status="taken", note="picked up")
        retry = self.send(request_id="stateful-retry", summary="Retry after ack")
        self.assertEqual(retry["status"], "duplicate")
        self.assertEqual(retry["message"]["id"], message_id)
        self.assertEqual(retry["message"]["status"], "taken")

    def test_path_traversal_inputs_are_rejected(self) -> None:
        for overrides in (
            {"task": "../escape"},
            {"task": "a/b"},
            {"request_id": "../escape"},
            {"request_id": "a/../../b"},
            {"reply_to": "../msg_20260101T000000_0000000000"},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(agent_messages.MessageError):
                    self.send(**overrides)
        for message_id in ("../etc/passwd", "msg_../../escape", "msg_" + "a" * 90):
            with self.subTest(message_id=message_id):
                with self.assertRaises(agent_messages.MessageError):
                    self.show(message_id)
                with self.assertRaises(agent_messages.MessageError):
                    self.ack(message_id, status="taken")
        self.assertFalse((self.base / "escape").exists())

    def test_terminal_messages_never_expire_but_expired_open_messages_are_refused(self) -> None:
        completed_id = self.send(summary="Completed before expiry")["message"]["id"]
        self.ack(completed_id, status="completed")
        self.rewrite_envelope(completed_id, expires_at="2000-01-01T00:00:00+00:00")
        shown = self.show(completed_id)
        self.assertEqual(shown["message"]["status"], "completed")
        self.assertFalse(shown["message"]["expired"])

        open_id = self.send(requires_approval=True, summary="Open but expired")["message"]["id"]
        self.rewrite_envelope(open_id, expires_at="2000-01-01T00:00:00+00:00")
        shown_open = self.show(open_id)
        self.assertEqual(shown_open["message"]["status"], "expired")
        self.assertTrue(shown_open["message"]["expired"])
        with self.assertRaises(agent_messages.MessageError):
            self.ack(open_id, status="taken")
        with self.assertRaises(agent_messages.MessageError):
            self.approve(open_id, by="AJ")

    def test_approval_gate_cannot_be_satisfied_after_a_terminal_transition(self) -> None:
        message_id = self.send(requires_approval=True, summary="Refused before approval")[
            "message"
        ]["id"]
        self.ack(message_id, status="refused")
        with self.assertRaises(agent_messages.MessageError):
            self.approve(message_id, by="AJ")
        with self.assertRaises(agent_messages.MessageError):
            self.ack(message_id, status="completed")

    def test_approval_gate_is_required_and_approval_is_single_person(self) -> None:
        message_id = self.send(requires_approval=True, summary="Needs a person")["message"]["id"]
        self.ack(message_id, status="taken")
        with self.assertRaises(agent_messages.MessageError):
            self.ack(message_id, status="completed")
        approved = self.approve(message_id, by="AJ")
        self.assertEqual(approved["status"], "approved")
        duplicate = self.approve(message_id, by="AJ")
        self.assertEqual(duplicate["status"], "duplicate")
        with self.assertRaises(agent_messages.MessageError):
            self.approve(message_id, by="Someone Else")
        self.assertEqual(self.ack(message_id, status="completed")["status"], "completed")
        with self.assertRaises(agent_messages.MessageError):
            self.approve(message_id, by="AJ")

    def test_reply_to_refused_parent_is_refused_but_completed_parent_is_allowed(self) -> None:
        refused = self.send(summary="Will be refused")["message"]["id"]
        self.ack(refused, status="refused")
        with self.assertRaises(agent_messages.MessageError):
            self.send(
                from_agent="Claude Code",
                to="Codex",
                summary="Reply to a refused parent",
                reply_to=refused,
            )

        completed = self.send(summary="Will be completed")["message"]["id"]
        self.ack(completed, status="completed")
        reply = self.send(
            from_agent="Claude Code",
            to="Codex",
            summary="Reply after completion",
            reply_to=completed,
        )
        self.assertEqual(reply["message"]["pass"], 2)
        self.assertEqual(reply["message"]["reply_to"], completed)

    def test_gitignore_keeps_message_state_local_and_checkpoints_portable(self) -> None:
        """The documented .gitignore split must hold: messages/lock ignored, checkpoints not."""

        ignore_file = ROOT / ".gitignore"
        self.assertTrue(ignore_file.is_file(), "repository .gitignore is missing")
        (self.project / ".gitignore").write_text(
            ignore_file.read_text(encoding="utf-8"), encoding="utf-8"
        )

        ignored = [
            ".agent-state/messages/issue-28/envelopes/msg_x.json",
            ".agent-state/messages/issue-28/receipts/msg_x.jsonl",
            ".agent-state/.lock",
        ]
        visible = [
            ".agent-state/tasks/issue-28.json",
            ".agent-state/history/issue-28/20260101T000000Z-abcdef12.json",
        ]
        for relative in ignored:
            result = subprocess.run(
                ["git", "-C", str(self.project), "check-ignore", "-q", relative],
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{relative} must be ignored")
        for relative in visible:
            result = subprocess.run(
                ["git", "-C", str(self.project), "check-ignore", "-q", relative],
                check=False,
            )
            self.assertEqual(result.returncode, 1, f"{relative} must stay visible to Git")


class McpRegressionTests(_RepoTestCase):
    """Sound MCP behaviour that the review verified over a real stdio subprocess."""

    def test_mcp_domain_errors_stay_tool_results_and_stdout_stays_pure_json(self) -> None:
        server = self.start_mcp_server()
        sent = server.tool_json(
            "send_message",
            {"task": "issue-28", "from": "Codex", "to": "Another Agent", "summary": "hello"},
        )
        message_id = sent["message"]["id"]
        stolen = server.call_tool(
            "ack_message", {"task": "issue-28", "id": message_id, "status": "taken"}
        )
        self.assertIs(stolen["isError"], True)
        self.assertIn("recipient", json.dumps(stolen).casefold())
        self.assertEqual(server.request("ping", request_id="after-domain-error")["result"], {})
        server.close()
        self.assertNotIn("Traceback", server.stderr_text())
        for line in server.stdout_lines():
            payload = json.loads(line)
            self.assertEqual(payload.get("jsonrpc"), "2.0")
            self.assertIn("id", payload)

    def test_mcp_tool_lists_every_documented_tool_and_never_an_approval_tool(self) -> None:
        server = self.start_mcp_server()
        tools = server.request("tools/list")["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertEqual(
            names, {"send_message", "get_inbox", "get_message", "ack_message"}
        )
        self.assertFalse(any("approve" in name.casefold() for name in names))
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertTrue(tool["inputSchema"].get("required"))

    def test_mcp_notifications_get_no_response_and_are_ignored(self) -> None:
        server = self.start_mcp_server()
        server.notify("notifications/initialized")
        server.notify("notifications/unknown-notification")
        response = server.request("ping", request_id="after-notifications")
        self.assertEqual(response["id"], "after-notifications")
        self.assertEqual(response["result"], {})


# ---------------------------------------------------------------------------
# Minimal blocking stdio client for the MCP subprocess.
# ---------------------------------------------------------------------------


class _McpServer:
    def __init__(self, project: Path, agent: str) -> None:
        self.process = subprocess.Popen(
            [sys.executable, str(MCP_SERVER), "--project", str(project), "--agent", agent],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._raw_lines: list[str] = []
        self._stderr: str | None = None
        self._closed = False
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        try:
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self._raw_lines.append(line.rstrip("\n"))
                self._lines.put(line)
        except (OSError, ValueError):  # pragma: no cover - teardown race
            pass
        finally:
            self._lines.put(None)

    def send_raw(self, text: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()

    def notify(self, method: str, params: Any = _OMIT) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not _OMIT:
            message["params"] = params
        self.send_raw(json.dumps(message))

    def read_raw(self, timeout: float = READ_TIMEOUT) -> str:
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self._fail(f"timed out after {timeout}s waiting for an MCP response")
        if line is None:
            self._fail("MCP server closed stdout before sending a response")
        return line.rstrip("\n")

    def request(self, method: str, params: Any = _OMIT, request_id: Any = "rpc-1") -> dict[str, Any]:
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not _OMIT:
            message["params"] = params
        self.send_raw(json.dumps(message))
        payload = json.loads(self.read_raw())
        if not isinstance(payload, dict):
            self._fail(f"stdout carried a non-object JSON-RPC message: {payload!r}")
        return payload

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        response = self.request("tools/call", params)
        if "error" in response:
            self._fail(f"unexpected JSON-RPC error for {name}: {response['error']}")
        result = response.get("result")
        if not isinstance(result, dict):
            self._fail(f"tools/call for {name} returned no result object")
        return result

    def tool_json(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.call_tool(name, arguments)
        if result.get("isError"):
            self._fail(f"{name} failed: {self._text_of(result)}")
        return json.loads(self._text_of(result))

    def _text_of(self, result: dict[str, Any]) -> str:
        content = result.get("content")
        if not isinstance(content, list) or not content:
            self._fail(f"tool result has no content: {result}")
        item = content[0]
        if not isinstance(item, dict) or item.get("type") != "text":
            self._fail(f"tool result content is not text: {item}")
        return item["text"]

    def stdout_lines(self) -> list[str]:
        return list(self._raw_lines)

    def stderr_text(self) -> str:
        if self._stderr is not None:
            return self._stderr
        if self.process.stderr is None or self.process.poll() is None:
            return ""  # a live pipe would block; only read after the process exits
        try:
            return self.process.stderr.read()
        except (OSError, ValueError):  # pragma: no cover - defensive
            return ""

    def _fail(self, message: str) -> None:
        try:
            self.process.kill()
            self.process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):  # pragma: no cover - defensive
            pass
        stderr = self.stderr_text()
        raise AssertionError(f"{message}\nserver stderr:\n{stderr}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.process.poll() is None:
            try:
                assert self.process.stdin is not None
                self.process.stdin.close()
            except (OSError, ValueError):  # pragma: no cover - defensive
                pass
        try:
            self.process.wait(timeout=READ_TIMEOUT)
        except subprocess.TimeoutExpired:  # pragma: no cover - hung server
            self.process.kill()
            self.process.wait(timeout=5)
        self._reader.join(timeout=5)
        self._stderr = self.stderr_text()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except (OSError, ValueError):  # pragma: no cover - defensive
                pass


if __name__ == "__main__":
    unittest.main()
