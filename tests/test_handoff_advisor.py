from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import agent_handoff  # noqa: E402
import handoff_advisor  # noqa: E402
import skill_atlas  # noqa: E402


def git(folder, *args):
    subprocess.run(["git", "-C", str(folder), *args],
                   stdout=subprocess.PIPE, check=True)


class AdvisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        git(self.project, "init", "-q")
        git(self.project, "config", "user.email", "test@example.invalid")
        git(self.project, "config", "user.name", "Tests")
        (self.project / "README.md").write_text("# Fixture\n")
        git(self.project, "add", ".")
        git(self.project, "commit", "-qm", "initial")

    def params(self, **kw):
        data = dict(project=str(self.project), task="issue-10", description=None,
                    task_type=None, required_tool=[], profiles=None, format="json")
        data.update(kw)
        return argparse.Namespace(**data)

    def checkpoint(self, next_action="Fix React canvas zoom bug"):
        return agent_handoff.write_checkpoint(argparse.Namespace(
            command="handoff", project=str(self.project), task="issue-10",
            agent="Codex", summary="Previous step finished",
            next_action=next_action, completed=[], remaining=[],
            test_command=None, test_result="not-run"))

    def registry(self, *, costs=True, evaluations=True):
        measured = datetime.now(timezone.utc).isoformat()
        model = dict(id="model-coding-A", capabilities=["code"],
                     capability_evidence="reviewed project tests", access_status="configured")
        if evaluations:
            model["task_evaluations"] = {
                "code": {"success_rate": 0.9, "sample_size": 10, "measured_at": measured}}
        if costs:
            model["user_cost_score"] = 0.6
        result = {
            "schema_version": 1,
            "models": [model],
            "agents": [
                {"id": "agent-A", "supported_models": ["model-coding-A"],
                 "tools": ["filesystem", "terminal", "git"], "access_status": "configured",
                 "handoff_safety_score": 0.8},
                {"id": "agent-B", "supported_models": ["model-coding-A"],
                 "tools": ["filesystem"], "access_status": "configured"},
            ]}
        path = self.project / "model-agent-profiles.json"
        path.write_text(json.dumps(result))
        return path

    def test_missing_profiles_and_no_writes(self):
        self.checkpoint()
        before = set(self.project.rglob("*"))
        result = handoff_advisor.advise(self.params())
        self.assertEqual(result["status"], "needs-profiles")
        self.assertTrue(result["handoff_ready"])
        self.assertEqual(before, set(self.project.rglob("*")))

    def test_evidence_ranked_eligible_candidate(self):
        self.checkpoint()
        path = self.registry()
        result = handoff_advisor.advise(self.params(profiles=str(path)))
        self.assertEqual(result["status"], "evidence-ranked")
        self.assertEqual(result["primary"]["agent"], "agent-A")
        self.assertEqual(len(result["shortlist"]), 1)
        self.assertFalse(result["shortlist"][0]["live_availability_verified"])
        self.assertTrue(any("missing required tools" in x["reason"] for x in result["exclusions"]))

    def test_missing_evidence_never_gets_fake_score(self):
        self.checkpoint()
        path = self.registry(costs=False, evaluations=False)
        result = handoff_advisor.advise(self.params(profiles=str(path)))
        self.assertEqual(result["status"], "provisional-shortlist")
        self.assertIsNone(result["primary"])
        entry = result["shortlist"][0]
        self.assertGreater(entry["score_upper_bound"], entry["score_lower_bound"])
        self.assertIn("measured_quality", entry["missing_evidence"])

    def test_dirty_git_state_blocks_handoff_ready(self):
        self.checkpoint()
        path = self.registry()
        (self.project / "README.md").write_text("# Changed\n")
        result = handoff_advisor.advise(self.params(profiles=str(path)))
        self.assertEqual(result["checkpoint_status"], "review-required")
        self.assertFalse(result["handoff_ready"])
        self.assertIn("content_digest", result["checkpoint_changed_fields"])

    def test_stale_evaluation_is_excluded(self):
        self.checkpoint()
        path = self.registry()
        data = json.loads(path.read_text())
        data["models"][0]["task_evaluations"]["code"]["measured_at"] = "2025-01-01T00:00:00+00:00"
        path.write_text(json.dumps(data))
        result = handoff_advisor.advise(self.params(profiles=str(path)))
        self.assertEqual(result["status"], "provisional-shortlist")

    def test_model_access_unavailable_is_excluded(self):
        self.checkpoint()
        path = self.registry()
        data = json.loads(path.read_text())
        data["models"][0]["access_status"] = "unavailable"
        path.write_text(json.dumps(data))
        result = handoff_advisor.advise(self.params(profiles=str(path)))
        self.assertEqual(result["status"], "no-eligible-candidates")

    def test_unknown_task_and_no_checkpoint(self):
        result = handoff_advisor.advise(self.params(description="Continue the feature"))
        self.assertEqual(result["status"], "needs-task-description-or-type")
        self.assertFalse(result["handoff_ready"])

    def test_override_task_type(self):
        path = self.registry()
        result = handoff_advisor.advise(
            self.params(description="Do something", task_type="code", profiles=str(path)))
        self.assertEqual(result["task_type"], "code")
        self.assertFalse(result["handoff_ready"])

    def test_reject_invalid_profile(self):
        self.checkpoint()
        path = self.registry()
        path.write_text('{"schema_version":1,"models":[],"agents":[{"id":"A","id":"A"}]}')
        with self.assertRaises(handoff_advisor.AdviceError):
            handoff_advisor.advise(self.params(profiles=str(path)))

    def test_backward_compatible_handoff_parser(self):
        args = skill_atlas.parse_args(["handoff", "--project", str(self.project),
                "--task", "issue-10", "--agent", "Codex", "--summary", "Done",
                "--next-action", "Fix canvas bug"])
        self.assertEqual(args.command, "handoff")
        new = skill_atlas.parse_args(["handoff", "advise", "--project", str(self.project),
                                     "--task", "issue-10", "--task-type", "code"])
        self.assertEqual(new.command, "handoff-advise")
        self.assertEqual(new.task_type, "code")


if __name__ == "__main__":
    unittest.main()
