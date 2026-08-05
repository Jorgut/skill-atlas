from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import skill_atlas  # noqa: E402
import market_cache  # noqa: E402
import recommend_skills  # noqa: E402


RESULTS = {
    "summary": "Reviewed React interaction skills",
    "sources": [
        {"name": "skills.sh", "type": "marketplace", "url": "https://skills.sh"},
        {"name": "React Bits", "type": "official-or-github", "url": "https://github.com/DavidHDev/react-bits"},
        {"name": "Community list", "type": "community", "url": "https://github.com/example/skills"},
    ],
    "candidates": [
        {
            "name": "apple-design",
            "url": "https://github.com/DavidHDev/react-bits",
            "capabilities": ["design-ux", "animation-motion"],
            "roles": ["design"],
            "keywords": ["react"],
            "platforms": ["codex", "opencode", "claude"],
            "score": 92,
        },
        {
            "name": "review-animations",
            "url": "https://github.com/DavidHDev/react-bits",
            "capabilities": ["animation-motion", "design-validation"],
            "roles": ["review"],
            "keywords": ["react"],
            "platforms": ["codex", "opencode", "claude"],
            "score": 90,
        },
    ],
}


class MarketCliTests(unittest.TestCase):
    def test_cli_exposes_market_commands_and_refresh_flag(self) -> None:
        market_args = skill_atlas.parse_args(["market", "status", "--ttl-hours", "48"])
        recommend_args = skill_atlas.parse_args(
            ["recommend", "product", "Design an HMI", "--refresh"]
        )

        self.assertEqual(market_args.ttl_hours, 48)
        self.assertTrue(recommend_args.refresh)

    def test_recommendation_discovers_explicit_local_component_library(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "component-library.json").write_text(
                """{
  "artifact_type": "component-library",
  "name": "@jorgut/liquid-glass",
  "version": "0.1.0",
  "ecosystem": "react",
  "capabilities": ["frontend-ui", "design-ux"]
}
""",
                encoding="utf-8",
            )
            args = skill_atlas.parse_args([
                "orchestrate",
                "plan",
                "Build a React liquid glass component library",
                "--root",
                directory,
                "--component-root",
                directory,
                "--market-state-dir",
                directory,
                "--mode",
                "quick",
            ])

            result = skill_atlas.recommendation_result(args)

        self.assertEqual(
            result["local_component_libraries"][0]["name"],
            "@jorgut/liquid-glass",
        )
        component_steps = [
            item
            for item in result["artifact_orchestration"]
            if item["artifact_type"] == "component-library"
        ]
        self.assertEqual(component_steps[0]["role"], "implementation")

    def test_balanced_recommendation_checks_market_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = skill_atlas.parse_args(
                [
                    "recommend",
                    "product",
                    "Build a product",
                    "--root",
                    directory,
                    "--market-state-dir",
                    directory,
                ]
            )

            result = skill_atlas.recommendation_result(args)

        self.assertEqual(result["market_freshness"]["status"], "missing")
        self.assertEqual(result["market_freshness"]["ttl_hours"], 24)
        self.assertTrue(result["market_refresh_required"])

    def test_orchestration_uses_fresh_reviewed_market_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            market_cache.MarketCache(Path(directory)).save(RESULTS)
            args = skill_atlas.parse_args(
                [
                    "orchestrate",
                    "plan",
                    "Build an interactive React interface with motion and UX review",
                    "--root",
                    directory,
                    "--market-state-dir",
                    directory,
                ]
            )

            result = skill_atlas.recommendation_result(args)

            output = StringIO()
            with redirect_stdout(output):
                recommend_skills.emit_markdown(result, True)

            refresh_args = skill_atlas.parse_args(
                [
                    "orchestrate",
                    "plan",
                    "Build an interactive React interface with motion and UX review",
                    "--root",
                    directory,
                    "--market-state-dir",
                    directory,
                    "--refresh",
                ]
            )
            refresh_result = skill_atlas.recommendation_result(refresh_args)

        self.assertEqual(result["market_freshness"]["status"], "fresh")
        self.assertEqual(
            [item["name"] for item in result["reviewed_market_matches"]],
            ["apple-design", "review-animations"],
        )
        self.assertEqual(
            [item["role"] for item in result["reviewed_orchestration"]],
            ["design", "review"],
        )
        self.assertTrue(all(
            item["availability"] == "install-required"
            for item in result["reviewed_orchestration"]
        ))
        self.assertIn("## Public Market Freshness", output.getvalue())
        self.assertIn("## Reviewed Market Matches", output.getvalue())
        self.assertIn("## Reviewed Cross-Skill Plan", output.getvalue())
        self.assertTrue(all(
            item["review_status"] == "refresh-required"
            for item in refresh_result["reviewed_market_matches"]
        ))


if __name__ == "__main__":
    unittest.main()
