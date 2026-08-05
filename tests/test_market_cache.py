from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import market_cache  # noqa: E402


NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
RESULTS = {
    "summary": "Reviewed market snapshot",
    "sources": [
        {"name": "skills.sh", "type": "marketplace", "url": "https://skills.sh"},
        {"name": "GitHub", "type": "official-or-github", "url": "https://github.com"},
        {"name": "Awesome skills", "type": "community", "url": "https://github.com/example/awesome"},
    ],
    "candidates": [
        {
            "name": "UX candidate",
            "url": "https://github.com/example/ux",
            "capabilities": ["design-ux"],
            "roles": ["design", "review"],
            "keywords": ["ux"],
            "platforms": ["codex", "claude"],
            "score": 91,
        }
    ],
}


class MarketCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cache = market_cache.MarketCache(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_missing_fresh_and_stale_status(self) -> None:
        self.assertEqual(self.cache.status(24, NOW)["status"], "missing")
        self.cache.save(RESULTS, NOW)

        self.assertEqual(self.cache.status(24, NOW)["status"], "fresh")
        later = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(self.cache.status(24, later)["status"], "stale")

    def test_results_require_all_source_types(self) -> None:
        incomplete = {**RESULTS, "sources": RESULTS["sources"][:2]}

        with self.assertRaisesRegex(market_cache.MarketCacheError, "community"):
            market_cache.validate_results(incomplete)

        no_capability = {
            **RESULTS,
            "candidates": [
                {"name": "Unknown", "url": "https://github.com/Jorgut/unknown", "capabilities": []}
            ],
        }
        with self.assertRaisesRegex(market_cache.MarketCacheError, "non-empty capabilities"):
            market_cache.validate_results(no_capability)

        invalid_role = {
            **RESULTS,
            "candidates": [{**RESULTS["candidates"][0], "roles": ["generate-everything"]}],
        }
        with self.assertRaisesRegex(market_cache.MarketCacheError, "role vocabulary"):
            market_cache.validate_results(invalid_role)

        invalid_score = {
            **RESULTS,
            "candidates": [{**RESULTS["candidates"][0], "score": 101}],
        }
        with self.assertRaisesRegex(market_cache.MarketCacheError, "0 to 100"):
            market_cache.validate_results(invalid_score)

        invalid_artifact = {
            **RESULTS,
            "candidates": [{**RESULTS["candidates"][0], "artifact_type": "source-code-copy"}],
        }
        with self.assertRaisesRegex(market_cache.MarketCacheError, "artifact type"):
            market_cache.validate_results(invalid_artifact)

    def test_component_library_is_a_supported_artifact(self) -> None:
        results = {
            **RESULTS,
            "candidates": [{
                **RESULTS["candidates"][0],
                "name": "@jorgut/liquid-glass",
                "artifact_type": "component-library",
                "roles": ["implementation"],
            }],
        }

        self.assertEqual(
            market_cache.validate_results(results)["candidates"][0]["artifact_type"],
            "component-library",
        )

    def test_refresh_policy_depends_on_mode_and_freshness(self) -> None:
        fresh = {"fresh": True}
        stale = {"fresh": False}

        self.assertFalse(market_cache.refresh_required("quick", fresh, False, True))
        self.assertFalse(market_cache.refresh_required("quick", stale, False, False))
        self.assertTrue(market_cache.refresh_required("quick", stale, False, True))
        self.assertFalse(market_cache.refresh_required("balanced", fresh, False, False))
        self.assertTrue(market_cache.refresh_required("balanced", stale, False, False))
        self.assertTrue(market_cache.refresh_required("benchmark", fresh, False, False))
        self.assertTrue(market_cache.refresh_required("quick", fresh, True, False))

if __name__ == "__main__":
    unittest.main()
