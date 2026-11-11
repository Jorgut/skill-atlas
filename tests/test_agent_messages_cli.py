from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import skill_atlas  # noqa: E402


def git(directory: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(directory), *argv], check=True, stdout=subprocess.PIPE)


class MessageCliTests(unittest.TestCase):
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

    def invoke(self, argv: list[str]) -> str:
        args = skill_atlas.parse_args(argv)
        out = StringIO()
        err = StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as raised:
                args.handler(args)
        self.assertEqual(raised.exception.code, 2, err.getvalue())
        return err.getvalue()

    def run_cli(self, argv: list[str]) -> str:
        args = skill_atlas.parse_args(argv)
        out = StringIO()
        with redirect_stdout(out):
            args.handler(args)
        return out.getvalue()

    def send(self, *extra: str) -> str:
        return self.run_cli(
            [
                "message",
                "send",
                "--project",
                str(self.project),
                "--task",
                "issue-28",
                "--from",
                "Codex",
                "--to",
                "Claude Code",
                "--summary",
                "Review the camera diff",
                "--format",
                "json",
                *extra,
            ]
        )

    def test_send_inbox_ack_roundtrip_over_the_unified_cli(self):
        sent = json.loads(self.send())
        self.assertEqual(sent["status"], "queued")
        message_id = sent["message"]["id"]

        inbox = json.loads(
            self.run_cli(
                [
                    "message",
                    "inbox",
                    "--project",
                    str(self.project),
                    "--task",
                    "issue-28",
                    "--agent",
                    "Claude Code",
                    "--format",
                    "json",
                ]
            )
        )
        self.assertEqual(inbox["count"], 1)
        self.assertEqual(inbox["messages"][0]["id"], message_id)

        acked = json.loads(
            self.run_cli(
                [
                    "message",
                    "ack",
                    "--project",
                    str(self.project),
                    "--task",
                    "issue-28",
                    "--id",
                    message_id,
                    "--agent",
                    "Claude Code",
                    "--status",
                    "completed",
                    "--format",
                    "json",
                ]
            )
        )
        self.assertEqual(acked["status"], "completed")

    def test_markdown_is_the_default_output(self):
        output = self.run_cli(
            [
                "message",
                "send",
                "--project",
                str(self.project),
                "--task",
                "issue-28",
                "--from",
                "Codex",
                "--to",
                "Claude Code",
                "--summary",
                "Review the camera diff",
            ]
        )
        self.assertIn("# Agent message: queued", output)
        self.assertIn("from: Codex -> Claude Code", output)

    def test_request_id_makes_retries_safe(self):
        first = json.loads(self.send("--request-id", "cli-req-1"))
        second = json.loads(self.send("--request-id", "cli-req-1"))
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(first["message"]["id"], second["message"]["id"])

    def test_human_approval_is_required_before_completion(self):
        sent = json.loads(self.send("--requires-approval"))
        message_id = sent["message"]["id"]
        ack = [
            "message",
            "ack",
            "--project",
            str(self.project),
            "--task",
            "issue-28",
            "--id",
            message_id,
            "--agent",
            "Claude Code",
            "--status",
            "completed",
            "--format",
            "json",
        ]
        self.assertIn("approve", self.invoke(ack))
        approved = json.loads(
            self.run_cli(
                [
                    "message",
                    "approve",
                    "--project",
                    str(self.project),
                    "--task",
                    "issue-28",
                    "--id",
                    message_id,
                    "--by",
                    "AJ",
                    "--format",
                    "json",
                ]
            )
        )
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(json.loads(self.run_cli(ack))["status"], "completed")

    def test_refusal_uses_exit_code_two_and_stderr(self):
        sent = json.loads(self.send())
        message_id = sent["message"]["id"]
        error = self.invoke(
            [
                "message",
                "ack",
                "--project",
                str(self.project),
                "--task",
                "issue-28",
                "--id",
                message_id,
                "--agent",
                "Codex",
                "--status",
                "taken",
            ]
        )
        self.assertIn("recipient", error)

    def test_non_git_project_is_refused(self):
        with tempfile.TemporaryDirectory() as plain:
            error = self.invoke(
                [
                    "message",
                    "inbox",
                    "--project",
                    plain,
                    "--task",
                    "issue-28",
                    "--agent",
                    "Claude Code",
                ]
            )
        self.assertIn("Git", error)

    def test_message_help_lists_every_action(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "skill_atlas.py"), "message", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for action in ("send", "inbox", "show", "ack", "approve"):
            self.assertIn(action, completed.stdout)


if __name__ == "__main__":
    unittest.main()
