from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import skill_atlas  # noqa: E402


class MarketCliTests(unittest.TestCase):
    def test_cli_exposes_market_commands_and_refresh_flag(self) -> None:
        market_args = skill_atlas.parse_args(["market", "status", "--ttl-hours", "48"])
        recommend_args = skill_atlas.parse_args(
            ["recommend", "product", "Design an HMI", "--refresh"]
        )

        self.assertEqual(market_args.ttl_hours, 48)
        self.assertTrue(recommend_args.refresh)

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


if __name__ == "__main__":
    unittest.main()
