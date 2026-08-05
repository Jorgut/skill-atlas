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

LOCAL_SKILL_ATLAS = {
    "name": "skill-atlas",
    "description": "Discover and orchestrate skills for CAD, Rhino, Blender, and product workflows",
    "path": "/skills/skill-atlas/SKILL.md",
    "root_class": "agents-loadable",
    "maintenance_class": "user-authored",
}

LOCAL_ARCHVIZ = {
    "name": "archviz",
    "description": "Architectural visualization in Blender for interiors and exteriors",
    "path": "/skills/archviz/SKILL.md",
    "root_class": "agents-loadable",
    "maintenance_class": "external-maintained",
}

LOCAL_PROCEDURAL_MODELING = {
    "name": "procedural-modeling",
    "description": "Procedural asset creation for buildings and terrain using Blender",
    "path": "/skills/procedural-modeling/SKILL.md",
    "root_class": "agents-loadable",
    "maintenance_class": "external-maintained",
}


class RecommendationModeTests(unittest.TestCase):
    def test_installed_architecture_skills_fill_instruction_capabilities(self) -> None:
        result = recommend_skills.build_recommendation(
            "Design an architectural interior and create a procedural Blender model",
            [LOCAL_ARCHVIZ, LOCAL_PROCEDURAL_MODELING],
            2,
            "quick",
        )

        matches = {
            (item["capability"], item["skill"])
            for item in result["use_now"]
        }

        self.assertIn(("architecture-interior", "archviz"), matches)
        self.assertIn(("cad-3d-modeling", "procedural-modeling"), matches)

    def test_meta_skill_does_not_fill_cad_execution_gap(self) -> None:
        result = recommend_skills.build_recommendation(
            "Automate Rhino CAD and BIM modeling",
            [LOCAL_SKILL_ATLAS],
            2,
            "quick",
        )

        cad_matches = [
            item for item in result["use_now"]
            if item["capability"] == "cad-3d-modeling"
        ]
        gaps = {item["capability"] for item in result["external_search_gaps"]}

        self.assertEqual(cad_matches, [])
        self.assertIn("cad-3d-modeling", gaps)

    def test_reviewed_candidates_are_filtered_and_ordered_by_role(self) -> None:
        candidates = [
            {
                "name": "apple-design",
                "url": "https://github.com/DavidHDev/react-bits",
                "capabilities": ["design-ux", "animation-motion"],
                "roles": ["design"],
                "keywords": ["react"],
                "platforms": ["codex", "claude"],
                "score": 92,
            },
            {
                "name": "motion-dev-animations",
                "url": "https://github.com/199-biotechnologies/motion-dev-animations-skill",
                "capabilities": ["animation-motion", "frontend-ui"],
                "roles": ["implementation"],
                "keywords": ["react", "next.js"],
                "platforms": ["codex", "claude"],
                "score": 88,
            },
            {
                "name": "review-animations",
                "url": "https://github.com/DavidHDev/react-bits",
                "capabilities": ["animation-motion", "design-validation"],
                "roles": ["review"],
                "keywords": ["react"],
                "platforms": ["codex", "claude"],
                "score": 90,
            },
            {
                "name": "rhino-modeling",
                "url": "https://github.com/example/rhino",
                "capabilities": ["animation-motion"],
                "roles": ["implementation"],
                "keywords": ["rhino"],
                "platforms": ["codex"],
                "score": 95,
            },
        ]

        matches = recommend_skills.match_market_candidates(
            "Build an interactive React interface with motion",
            ["frontend-ui", "design-ux", "design-validation", "animation-motion"],
            candidates,
            {"apple-design"},
            True,
        )
        plan = recommend_skills.build_reviewed_orchestration(matches)

        self.assertEqual([item["name"] for item in matches], [
            "apple-design", "review-animations", "motion-dev-animations"
        ])
        self.assertEqual(matches[0]["availability"], "installed")
        self.assertEqual(matches[1]["availability"], "install-required")
        self.assertEqual(matches[1]["review_status"], "current")
        self.assertEqual([item["role"] for item in plan], [
            "design", "implementation", "review"
        ])

    def test_stale_market_match_keeps_install_state(self) -> None:
        matches = recommend_skills.match_market_candidates(
            "React animation",
            ["animation-motion"],
            [{
                "name": "review-animations",
                "url": "https://github.com/DavidHDev/react-bits",
                "capabilities": ["animation-motion"],
                "roles": ["review"],
            }],
            {"review-animations"},
            False,
        )

        self.assertEqual(matches[0]["availability"], "installed")
        self.assertEqual(matches[0]["review_status"], "refresh-required")

    def test_component_library_keeps_its_type_through_orchestration(self) -> None:
        matches = recommend_skills.match_market_candidates(
            "Build a React liquid glass component library",
            ["frontend-ui", "design-ux"],
            [{
                "name": "@jorgut/liquid-glass",
                "artifact_type": "component-library",
                "url": "https://github.com/Jorgut/liquid-glass-design",
                "capabilities": ["frontend-ui", "design-ux"],
                "roles": ["implementation"],
                "keywords": ["react", "liquid glass"],
                "score": 90,
            }],
            set(),
            True,
        )
        plan = recommend_skills.build_reviewed_orchestration(matches)

        self.assertEqual(matches[0]["artifact_type"], "component-library")
        self.assertEqual(matches[0]["availability"], "dependency-required")
        self.assertEqual(plan[0]["artifact"], "@jorgut/liquid-glass")
        self.assertEqual(plan[0]["artifact_type"], "component-library")

    def test_explicit_ui_library_request_creates_component_research(self) -> None:
        targets = recommend_skills.research_targets(
            "Build a React liquid glass component library",
            ["frontend-ui", "design-ux"],
        )

        self.assertIn("component-library", {item["type"] for item in targets})

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
