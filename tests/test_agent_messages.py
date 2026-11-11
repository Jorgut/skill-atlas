from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import agent_messages  # noqa: E402


def git(directory: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(directory), *argv], check=True, stdout=subprocess.PIPE)


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        git(self.project, "init", "-q")
        git(self.project, "config", "user.email", "test@example.invalid")
        git(self.project, "config", "user.name", "Tests")
        (self.project / "README.md").write_text("# test\n")
        git(self.project, "add", "README.md")
        git(self.project, "commit", "-qm", "initial")

    def options(self, action: str, **overrides: object) -> argparse.Namespace:
        params: dict[str, object] = {
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

    def send(self, **overrides: object) -> dict:
        return agent_messages.send(self.options("send", **overrides))

    def inbox(self, **overrides: object) -> dict:
        return agent_messages.inbox(self.options("inbox", **overrides))

    def test_send_and_inbox_roundtrip(self):
        sent = self.send()
        self.assertEqual(sent["status"], "queued")
        self.assertEqual(sent["message"]["status"], "queued")
        self.assertEqual(sent["message"]["pass"], 1)
        self.assertEqual(sent["message"]["approval"], "not-required")
        self.assertIn("not been notified", sent["notes"])
        inbox = self.inbox()
        self.assertEqual(inbox["count"], 1)
        item = inbox["messages"][0]
        self.assertEqual(item["id"], sent["message"]["id"])
        self.assertEqual(item["from"], "Codex")
        self.assertEqual(item["to"], "Claude Code")
        self.assertEqual(item["summary"], "Review the camera diff")
        self.assertEqual(item["evidence"], ["src/camera.ts"])

    def test_recipient_lookup_is_case_insensitive_and_display_name_is_preserved(self):
        sent = self.send(to="Claude Code")
        inbox = self.inbox(agent="claude code")
        self.assertEqual(inbox["count"], 1)
        self.assertEqual(sent["message"]["to"], "Claude Code")

    def test_idempotent_request_returns_the_same_message(self):
        first = self.send(request_id="req-1")
        second = self.send(request_id="req-1")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(first["message"]["id"], second["message"]["id"])
        self.assertEqual(len(list((self.project / ".agent-state" / "messages" / "issue-28" / "envelopes").iterdir())), 1)

    def test_request_id_with_different_content_is_refused(self):
        self.send(request_id="req-1")
        with self.assertRaises(agent_messages.MessageError):
            self.send(request_id="req-1", summary="Different words")

    def test_terminal_messages_leave_the_active_inbox(self):
        sent = self.send()
        message_id = sent["message"]["id"]
        agent_messages.ack(self.options("ack", id=message_id, status="completed"))
        self.assertEqual(self.inbox()["count"], 0)
        self.assertEqual(self.inbox(status="completed")["count"], 1)
        self.assertEqual(self.inbox(status="all")["count"], 1)

    def test_ack_lifecycle_records_receipts(self):
        message_id = self.send()["message"]["id"]
        taken = agent_messages.ack(self.options("ack", id=message_id, status="taken", note="picked up"))
        self.assertEqual(taken["status"], "taken")
        done = agent_messages.ack(self.options("ack", id=message_id, status="completed", note="merged"))
        self.assertEqual(done["status"], "completed")
        shown = agent_messages.show(self.options("show", id=message_id))
        self.assertEqual(shown["message"]["status"], "completed")
        events = [receipt["event"] for receipt in shown["receipts"]]
        self.assertEqual(events, ["queued", "taken", "completed"])
        self.assertEqual(shown["receipts"][-1]["note"], "merged")

    def test_only_the_recipient_may_acknowledge(self):
        message_id = self.send()["message"]["id"]
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.ack(self.options("ack", id=message_id, agent="Codex"))

    def test_terminal_status_cannot_change(self):
        message_id = self.send()["message"]["id"]
        agent_messages.ack(self.options("ack", id=message_id, status="refused"))
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.ack(self.options("ack", id=message_id, status="completed"))
        duplicate = agent_messages.ack(self.options("ack", id=message_id, status="refused"))
        self.assertEqual(duplicate["status"], "duplicate")

    def test_approval_gate_blocks_completion_until_a_person_approves(self):
        message_id = self.send(requires_approval=True)["message"]["id"]
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.ack(self.options("ack", id=message_id, status="completed"))
        approved = agent_messages.approve(self.options("approve", id=message_id, by="AJ", note="merge approved"))
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["message"]["approval"], "approved")
        done = agent_messages.ack(self.options("ack", id=message_id, status="completed"))
        self.assertEqual(done["status"], "completed")

    def test_approval_is_single_and_idempotent_per_person(self):
        message_id = self.send(requires_approval=True)["message"]["id"]
        agent_messages.approve(self.options("approve", id=message_id, by="AJ"))
        duplicate = agent_messages.approve(self.options("approve", id=message_id, by="AJ"))
        self.assertEqual(duplicate["status"], "duplicate")
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.approve(self.options("approve", id=message_id, by="Someone Else"))

    def test_approval_is_refused_when_not_requested(self):
        message_id = self.send()["message"]["id"]
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.approve(self.options("approve", id=message_id, by="AJ"))

    def test_expired_messages_are_hidden_refused_and_not_acknowledged(self):
        message_id = self.send(ttl_hours=0.0001)["message"]["id"]
        time.sleep(0.6)
        inbox = self.inbox()
        self.assertEqual(inbox["count"], 0)
        shown = agent_messages.show(self.options("show", id=message_id))
        self.assertTrue(shown["message"]["expired"])
        self.assertEqual(shown["message"]["status"], "expired")
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.ack(self.options("ack", id=message_id, status="taken"))
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.approve(self.options("approve", id=message_id, by="AJ"))

    def test_expired_messages_can_be_listed_on_request(self):
        self.send(ttl_hours=0.0001)
        time.sleep(0.6)
        listed = self.inbox(include_expired=True)
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["messages"][0]["status"], "expired")
        self.assertTrue(listed["messages"][0]["expired"])

    def test_replies_derive_the_next_pass(self):
        parent = self.send()
        reply = self.send(
            from_agent="Claude Code",
            to="Codex",
            summary="Review complete",
            reply_to=parent["message"]["id"],
            pass_count=None,
        )
        self.assertEqual(reply["message"]["pass"], 2)
        self.assertEqual(reply["message"]["reply_to"], parent["message"]["id"])
        with self.assertRaises(agent_messages.MessageError):
            self.send(
                from_agent="Claude Code",
                to="Codex",
                summary="Wrong pass",
                reply_to=parent["message"]["id"],
                pass_count=3,
            )

    def test_message_chain_stops_after_ten_passes(self):
        current = self.send()
        for expected in range(2, agent_messages.MAX_PASSES + 1):
            current = self.send(
                from_agent="Claude Code" if expected % 2 == 0 else "Codex",
                to="Codex" if expected % 2 == 0 else "Claude Code",
                summary=f"Pass {expected}",
                reply_to=current["message"]["id"],
            )
            self.assertEqual(current["message"]["pass"], expected)
        with self.assertRaises(agent_messages.MessageError):
            self.send(
                from_agent="Codex",
                to="Claude Code",
                summary="Eleventh pass",
                reply_to=current["message"]["id"],
            )

    def test_reply_to_missing_or_expired_parent_is_refused(self):
        parent = self.send(ttl_hours=0.0001)
        with self.assertRaises(agent_messages.MessageError):
            self.send(reply_to="msg_20260101T000000_0000000000")
        time.sleep(0.6)
        with self.assertRaises(agent_messages.MessageError):
            self.send(reply_to=parent["message"]["id"])

    def test_invalid_inputs_are_refused(self):
        for overrides in (
            {"task": "../escape"},
            {"from_agent": ""},
            {"to": "x" * 65},
            {"summary": ""},
            {"summary": "x" * (agent_messages.MAX_SUMMARY + 1)},
            {"conclusion": "x" * (agent_messages.MAX_CONCLUSION + 1)},
            {"evidence": ["x"] * (agent_messages.MAX_EVIDENCE_ITEMS + 1)},
            {"evidence": ["x" * (agent_messages.MAX_EVIDENCE_LENGTH + 1)]},
            {"summary": "bad\u0000value"},
            {"ttl_hours": 0},
            {"ttl_hours": agent_messages.MAX_TTL_HOURS + 1},
            {"request_id": "bad id"},
            {"pass_count": 0},
            {"pass_count": agent_messages.MAX_PASSES + 1},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(agent_messages.MessageError):
                    self.send(**overrides)

    def test_unknown_message_id_is_refused(self):
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.show(self.options("show", id="msg_20260101T000000_0000000000"))
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.ack(self.options("ack", id="msg_20260101T000000_0000000000"))

    def test_state_files_and_receipts_are_local_and_deterministic(self):
        sent = self.send(request_id="req-files")
        message_id = sent["message"]["id"]
        base = self.project / ".agent-state" / "messages" / "issue-28"
        self.assertTrue((base / "envelopes" / f"{message_id}.json").is_file())
        self.assertTrue((base / "status" / f"{message_id}.json").is_file())
        self.assertTrue((base / "requests" / "req-files.json").is_file())
        self.assertTrue((base / "receipts" / f"{message_id}.jsonl").is_file())
        envelope = json.loads((base / "envelopes" / f"{message_id}.json").read_text())
        self.assertEqual(envelope["schema_version"], 1)
        self.assertNotIn("password", json.dumps(envelope).casefold())

    def test_concurrent_sends_keep_distinct_messages(self):
        ids: list[str] = []
        errors: list[Exception] = []

        def worker(index: int) -> None:
            try:
                result = agent_messages.send(
                    self.options("send", summary=f"Message {index}", request_id=f"req-{index}")
                )
                ids.append(result["message"]["id"])
            except Exception as exc:  # pragma: no cover - surfaced by the assertion below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(ids), 8)
        self.assertEqual(len(set(ids)), 8)
        self.assertEqual(self.inbox()["count"], 8)

    def test_inbox_warns_about_unreadable_messages_instead_of_failing(self):
        broken = self.send(summary="Broken message")["message"]["id"]
        healthy = self.send(summary="Healthy message")["message"]["id"]
        status_path = (
            self.project / ".agent-state" / "messages" / "issue-28" / "status" / f"{broken}.json"
        )
        status_path.write_text("{not json", encoding="utf-8")
        result = self.inbox()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["messages"][0]["id"], healthy)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("unreadable", result["warnings"][0])

    def test_markdown_output_is_compact(self):
        sent = self.send(requires_approval=True)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            agent_messages.emit_markdown(sent)
        output = buffer.getvalue()
        self.assertIn("# Agent message: queued", output)
        self.assertIn(sent["message"]["id"], output)
        self.assertIn("approval: pending", output)

    def test_run_rejects_unknown_action(self):
        with self.assertRaises(agent_messages.MessageError):
            agent_messages.run(argparse.Namespace(action="broadcast"))


if __name__ == "__main__":
    unittest.main()
