from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import agent_handoff  # noqa: E402


def git(directory: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(directory), *argv], check=True, stdout=subprocess.PIPE)


class HandoffTests(unittest.TestCase):
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

    def options(self, action="checkpoint", **overrides):
        params = dict(command=action, project=str(self.project), task="issue-28",
                      agent="Codex", summary="Completed basic camera",
                      next_action="Implement selection", completed=["camera"],
                      remaining=["selection"], test_command=None, test_result="not-run")
        params.update(overrides)
        return argparse.Namespace(**params)

    def test_checkpoint_and_resume_are_consistent(self):
        written = agent_handoff.run(self.options())
        self.assertEqual(written["status"], "recorded")
        self.assertTrue(Path(written["history_file"]).exists())
        resumed = agent_handoff.run(self.options("resume"))
        self.assertEqual(resumed["status"], "checkpoint-consistent")
        self.assertEqual(resumed["checkpoint"]["next_action"], "Implement selection")

    def test_resume_detects_changes_without_overwriting(self):
        agent_handoff.run(self.options("handoff"))
        (self.project / "README.md").write_text("# changed\n")
        result = agent_handoff.run(self.options("resume"))
        self.assertEqual(result["status"], "review-required")
        self.assertIn("working_tree_digest", result["changed_fields"])
        self.assertEqual((self.project / "README.md").read_text(), "# changed\n")

    def test_resume_without_checkpoint_is_read_only(self):
        result = agent_handoff.run(self.options("resume"))
        self.assertEqual(result["status"], "no-checkpoint")
        self.assertFalse((self.project / ".agent-state").exists())

    def test_rejects_unsafe_task_identifier(self):
        with self.assertRaises(agent_handoff.HandoffError):
            agent_handoff.run(self.options(task="../secrets"))

    def test_cannot_claim_passed_test_without_command(self):
        with self.assertRaises(agent_handoff.HandoffError):
            agent_handoff.run(self.options(test_result="passed"))

    def test_multiple_agents_create_history(self):
        agent_handoff.run(self.options())
        agent_handoff.run(self.options("handoff", agent="OpenCode", next_action="Review final build"))
        entries = list((self.project / ".agent-state/history/issue-28").glob("*.json"))
        self.assertEqual(len(entries), 2)
        self.assertEqual(agent_handoff.run(self.options("resume"))["checkpoint"]["agent"], "OpenCode")


if __name__ == "__main__":
    unittest.main()
