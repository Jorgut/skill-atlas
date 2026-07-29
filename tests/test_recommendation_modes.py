from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import recommend_skills  # noqa: E402
import skill_atlas  # noqa: E402


LOCAL_UX = {
    "name": "ux-audit",
    "description": "UX usability accessibility audit and validation workflow",
    "path": "/skills/ux-audit/SKILL.md",
    "root_class": "agents-loadable",
    "maintenance_class": "user-authored",
}


class RecommendationModeTests(unittest.TestCase):
    def test_balanced_compares_even_when_local_match_exists(self) -> None:
        result = recommend_skills.build_recommendation(
            "Design and validate an automotive HMI UX",
            [LOCAL_UX],
            2,
            "balanced",
        )

        self.assertEqual(result["research_mode"], "balanced")
        self.assertEqual(result["recommendation_status"], "provisional")
        compared = {item["capability"] for item in result["external_comparison_plan"]}
        self.assertIn("design-validation", compared)
        validation = next(
            item for item in result["external_comparison_plan"]
            if item["capability"] == "design-validation"
        )
        self.assertEqual(validation["local_candidates"], ["ux-audit"])
        self.assertEqual(validation["candidate_target"], 3)
        self.assertEqual(
            validation["required_source_types"],
            ["marketplace", "official-or-github", "community"],
        )
        self.assertTrue(any("skills.sh" in query for query in validation["queries"]))

    def test_quick_only_generates_search_gaps(self) -> None:
        result = recommend_skills.build_recommendation(
            "Design and validate UX",
            [LOCAL_UX],
            2,
            "quick",
        )

        self.assertEqual(result["external_comparison_plan"], [])
        self.assertTrue(result["external_search_gaps"])

    def test_benchmark_expands_every_capability(self) -> None:
        result = recommend_skills.build_recommendation(
            "Build an animation product",
            [],
            2,
            "benchmark",
        )

        self.assertEqual(
            len(result["external_comparison_plan"]),
            len(result["detected_capabilities"]),
        )
        self.assertTrue(all(item["candidate_target"] == 8 for item in result["external_comparison_plan"]))
        self.assertTrue(all(len(item["queries"]) == 8 for item in result["external_comparison_plan"]))
        self.assertEqual(sum(item["weight"] for item in result["comparison_rubric"]), 100)

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported research mode"):
            recommend_skills.build_recommendation("A product", [], 2, "unknown")

    def test_orchestration_accepts_research_mode(self) -> None:
        args = skill_atlas.parse_args(
            ["orchestrate", "validate", "Design an HMI", "--mode", "benchmark"]
        )

        self.assertEqual(args.mode, "benchmark")

    def test_validation_separates_local_validity_from_external_comparison(self) -> None:
        result = recommend_skills.build_recommendation(
            "Design and validate UX",
            [LOCAL_UX],
            2,
            "balanced",
        )
        validation = skill_atlas.validate_orchestration(result)

        self.assertTrue(validation["external_comparison_pending"])
        self.assertEqual(validation["recommendation_status"], "provisional")


if __name__ == "__main__":
    unittest.main()
