from __future__ import annotations
import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import feedback_loop  # noqa: E402
import skill_atlas  # noqa: E402

class FeedbackLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "report.json"
        self.report = feedback_loop.make_report("Handoff failed", "Checkpoint mismatch", "handoff", "JANSO")
        self.path.write_text(json.dumps(self.report))

    def test_deterministic_fingerprint(self):
        self.assertEqual(self.report["fingerprint"],
                         feedback_loop.make_report("Handoff failed", "Checkpoint mismatch", "handoff")["fingerprint"])

    def test_redactions(self):
        report = feedback_loop.make_report("Key sk-" + "a"*20,
            "Contact jane@example.org; /Users/alice/private and password=abc123", "other")
        self.assertNotIn("jane@example.org", report["body"])
        self.assertNotIn("password=abc123", report["body"])
        self.assertNotIn("/Users/alice", report["body"])
        self.assertNotIn("sk-" + "a"*20, report["title"])

    def test_preview_without_network(self):
        args = argparse.Namespace(file=str(self.path), confirm=False, team_auto=False)
        with patch.object(feedback_loop, "github") as api:
            value = feedback_loop.handle_submit(args)
        self.assertEqual(value["status"], "preview")
        api.assert_not_called()

    def test_manual_submission_requires_confirm(self):
        with self.assertRaises(feedback_loop.FeedbackError):
            feedback_loop.submit(self.report)

    def test_auto_team_restricted(self):
        with patch.dict(os.environ, {"SKILL_ATLAS_TEAM_AUTOREPORT": "1", "GITHUB_TOKEN": "fake"}):
            with self.assertRaises(feedback_loop.FeedbackError):
                feedback_loop.submit(self.report, team_auto=True)

    def test_duplicate_prevents_posting(self):
        issue = {"title": self.report["title"], "body": self.report["body"], "html_url": "https://github.com/Jorgut/skill-atlas/issues/123"}
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake"}), patch.object(feedback_loop, "github", return_value=[issue]) as api:
            value = feedback_loop.submit(self.report, confirm=True)
        self.assertEqual(value["status"], "duplicate")
        api.assert_called_once()

    def test_submit_after_review(self):
        calls = []
        def fake(method, url, token, body=None):
            calls.append(method)
            return [] if method == "GET" else {"html_url": "https://github.com/Jorgut/skill-atlas/issues/124"}
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake"}), patch.object(feedback_loop, "github", side_effect=fake):
            value = feedback_loop.submit(self.report, confirm=True)
        self.assertEqual(value["status"], "created")
        self.assertEqual(calls, ["GET", "POST"])

    def test_fail_closed_on_duplicate_query_failure(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fake"}), patch.object(feedback_loop, "github", side_effect=feedback_loop.FeedbackError("network")):
            with self.assertRaises(feedback_loop.FeedbackError):
                feedback_loop.submit(self.report, confirm=True)

    def test_modified_report_rejected(self):
        report = dict(self.report)
        report["title"] += " unverified"
        with self.assertRaises(feedback_loop.FeedbackError):
            feedback_loop.validate(report)

    def test_command_registered(self):
        self.assertEqual(skill_atlas.parse_args(["feedback", "prepare", "--title", "Bug", "--summary", "Issue"]).feedback_action, "prepare")
        self.assertEqual(skill_atlas.parse_args(["handoff", "--agent", "Codex", "--task", "issue-3",
                                                 "--summary", "Done", "--next-action", "Next"]).command, "handoff")
