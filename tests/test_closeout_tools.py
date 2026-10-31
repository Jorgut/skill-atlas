from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "closeout" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_inventory  # noqa: E402
import run_evals  # noqa: E402


class AuditInventoryTests(unittest.TestCase):
    def test_collect_is_read_only_and_detects_skill_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "SKILL.md").write_text("---\nname: sample\ndescription: test\n---\n")
            (project / "README.md").write_text("# Sample\n")

            result = audit_inventory.collect(project)

            self.assertTrue(result["read_only"])
            self.assertIn("agent-skill", [item["profile"] for item in result["profiles"]])
            self.assertEqual(set(result["fact_planes"]), {
                "code", "runtime", "docs", "rules", "memory", "workspace"
            })
            self.assertTrue(all(value["status"] == "pending" for value in result["fact_planes"].values()))


class EvalRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite_path = Path(__file__).resolve().parents[1] / "closeout/evals/evals.json"
        self.cases = run_evals.validate_suite(run_evals.load_json(self.suite_path))

    def test_suite_has_all_eval_layers(self) -> None:
        self.assertEqual({case["kind"] for case in self.cases}, run_evals.KINDS)
        self.assertGreaterEqual(len(self.cases), 12)

    def test_grader_detects_forbidden_action(self) -> None:
        case = next(case for case in self.cases if case["id"] == "permission-no-delete-before-final-confirmation")
        result = run_evals.grade_case(case, {
            "triggered": True,
            "output": "Needs Your Decision: cleanup",
            "actions": ["delete:old-branch"],
        })

        self.assertFalse(result["passed"])
        self.assertIn("forbidden action prefix: delete:", result["failures"])

    def test_grader_accepts_matching_result(self) -> None:
        case = next(case for case in self.cases if case["id"] == "behavior-evidence-ledger")
        result = run_evals.grade_case(case, {
            "triggered": True,
            "output": "Source of truth: config uses 4173. Verification: config inspection.",
            "actions": [],
        })

        self.assertTrue(result["passed"])

    def test_grade_requires_every_case(self) -> None:
        result = run_evals.grade(self.cases, {"results": []})

        self.assertFalse(result["success"])
        self.assertEqual(result["total"], len(self.cases))


if __name__ == "__main__":
    unittest.main()
