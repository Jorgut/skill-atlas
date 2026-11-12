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

    def make_remote(self, name="remote.git"):
        temp = tempfile.TemporaryDirectory(prefix="skill-atlas-remote-")
        self.addCleanup(temp.cleanup)
        remote = Path(temp.name) / name
        remote.mkdir()
        git(remote, "init", "--bare", "-q")
        return remote

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

    def test_modified_content_with_same_git_status_is_detected(self):
        (self.project / "README.md").write_text("# alpha\n")
        agent_handoff.run(self.options())
        (self.project / "README.md").write_text("# beta\n")
        result = agent_handoff.run(self.options("resume"))
        self.assertEqual(result["status"], "review-required")
        self.assertIn("content_digest", result["changed_fields"])
        self.assertNotIn("working_tree_digest", result["changed_fields"])

    def test_untracked_content_change_is_detected(self):
        path = self.project / "draft.ts"
        path.write_text("console.log(1)\n")
        agent_handoff.run(self.options())
        path.write_text("console.log(12)\n")
        result = agent_handoff.run(self.options("resume"))
        self.assertEqual(result["status"], "review-required")
        self.assertIn("content_digest", result["changed_fields"])

    def test_resume_without_checkpoint_is_read_only(self):
        result = agent_handoff.run(self.options("resume"))
        self.assertEqual(result["status"], "no-checkpoint")
        self.assertFalse((self.project / ".agent-state").exists())

    def test_sync_status_without_upstream_warns(self):
        status = agent_handoff.sync_status(self.project)
        self.assertFalse(status["has_upstream"])
        self.assertTrue(any("no upstream" in warning for warning in status["warnings"]))

    def test_checkpoint_embeds_local_only_warning(self):
        written = agent_handoff.run(self.options())
        sync = written["checkpoint"]["git"]["sync"]
        self.assertFalse(sync["has_upstream"])
        self.assertTrue(written["warnings"])
        resumed = agent_handoff.run(self.options("resume"))
        self.assertTrue(resumed["warnings"])

    def test_sync_status_reports_ahead_after_local_commit(self):
        remote = self.make_remote("remote.git")
        git(self.project, "remote", "add", "origin", str(remote))
        git(self.project, "push", "-q", "-u", "origin", "HEAD")
        (self.project / "README.md").write_text("# ahead\n")
        git(self.project, "add", "README.md")
        git(self.project, "commit", "-qm", "ahead")
        status = agent_handoff.sync_status(self.project)
        self.assertTrue(status["has_upstream"])
        self.assertEqual(status["ahead"], 1)
        self.assertTrue(any("not on the remote" in warning for warning in status["warnings"]))

    def test_sync_status_reports_behind_after_fetch(self):
        remote = self.make_remote("remote-behind.git")
        git(self.project, "remote", "add", "origin", str(remote))
        git(self.project, "push", "-q", "-u", "origin", "HEAD")
        other_temp = tempfile.TemporaryDirectory(prefix="skill-atlas-other-")
        self.addCleanup(other_temp.cleanup)
        other = Path(other_temp.name) / "other"
        subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
        git(other, "config", "user.email", "test@example.invalid")
        git(other, "config", "user.name", "Tests")
        (other / "remote.txt").write_text("remote\n")
        git(other, "add", "remote.txt")
        git(other, "commit", "-qm", "remote change")
        git(other, "push", "-q")
        git(self.project, "fetch", "-q")
        status = agent_handoff.sync_status(self.project)
        self.assertEqual(status["behind"], 1)
        self.assertTrue(any("Remote-tracking" in warning for warning in status["warnings"]))

    def test_sync_status_reports_dirty_and_detached(self):
        (self.project / "README.md").write_text("# dirty\n")
        dirty = agent_handoff.sync_status(self.project)
        self.assertGreater(dirty["dirty"], 0)
        self.assertTrue(any("uncommitted" in warning for warning in dirty["warnings"]))
        git(self.project, "checkout", "--detach", "-q")
        detached = agent_handoff.sync_status(self.project)
        self.assertTrue(detached["detached"])
        self.assertTrue(any("Detached HEAD" in warning for warning in detached["warnings"]))

    def test_sync_report_is_read_only(self):
        before = sorted(str(p) for p in self.project.rglob("*"))
        report = agent_handoff.sync_report(argparse.Namespace(project=str(self.project)))
        after = sorted(str(p) for p in self.project.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual(report["status"], "ok")
        self.assertIn("warnings", report)

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
