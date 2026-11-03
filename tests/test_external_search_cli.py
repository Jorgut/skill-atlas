from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import skill_atlas
import external_search
import market_cache
from test_external_search import FakeClient, github, repository
from test_market_cli import RESULTS


class SearchCliTests(unittest.TestCase):
    def invoke(self, argv):
        args = skill_atlas.parse_args(argv)
        out = StringIO()
        with redirect_stdout(out):
            args.handler(args)
        return json.loads(out.getvalue()) if args.format == "json" else out.getvalue()

    def test_legacy_discovery_is_offline_and_explicit_about_scope(self):
        with tempfile.TemporaryDirectory() as root, patch.object(external_search.PublicClient, "get", side_effect=AssertionError("must not access network")):
            result = self.invoke(["discover", "pdf", "--root", root, "--format", "json"])
        self.assertEqual(result["search_mode"], "local")
        self.assertFalse(result["network_attempted"])
        self.assertNotIn("external_search", result)

    def test_web_discovery_without_any_local_candidates_or_scan(self):
        with patch.object(skill_atlas, "discovery_records", side_effect=AssertionError("must not scan local roots")), patch.object(external_search.PublicClient, "get", return_value=github(repository())):
            result = self.invoke(["discover", "similar", "pdf", "--search-mode", "web", "--provider", "github", "--format", "json"])
        self.assertFalse(result["local_inventory_scanned"])
        self.assertTrue(result["network_attempted"])
        self.assertTrue(result["external_search"]["candidates"])
        self.assertEqual(result["briefs"], [])

    def test_hybrid_keeps_local_records_and_sends_only_explicit_query(self):
        local = [{"name": "pdf", "description": "PRIVATE LOCAL DESCRIPTION", "path": "/private/user/skill", "root_class": "custom"}]
        with patch.object(skill_atlas, "discovery_records", return_value=local), patch.object(external_search.PublicClient, "get", return_value=github(repository())) as get:
            result = self.invoke(["discover", "pdf", "--search-mode", "hybrid", "--provider", "github", "--format", "json"])
        self.assertEqual(result["briefs"][0]["name"], "pdf")
        self.assertTrue(result["external_search"]["candidates"])
        self.assertNotIn("PRIVATE", str(get.call_args_list))
        self.assertNotIn("/private/user", str(get.call_args_list))

    def test_web_recommend_does_not_enumerate_local_skills_or_components(self):
        with tempfile.TemporaryDirectory() as root, patch.object(skill_atlas, "discovery_records", side_effect=AssertionError("local scan")), patch.object(skill_atlas.component_libraries, "discover", side_effect=AssertionError("component scan")), patch.object(external_search.PublicClient, "get", return_value=github(repository())) as get:
            result = self.invoke(["recommend", "tool", "pdf", "--search-mode", "web", "--provider", "github", "--market-state-dir", root, "--format", "json"])
            self.assertFalse(list(Path(root).iterdir()))
        self.assertEqual(result["external_search"]["query"], "pdf")
        self.assertFalse(result["local_inventory_scanned"])
        self.assertEqual(result["reviewed_market_matches"], [])
        self.assertTrue(result["external_candidates_review_required"])
        self.assertNotIn("Find+software", get.call_args.args[0])

    def test_reviewed_market_cache_not_changed_by_live_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = market_cache.MarketCache(Path(directory))
            cache.save(RESULTS)
            before = {p: p.read_bytes() for p in Path(directory).rglob("*") if p.is_file()}
            with patch.object(external_search.PublicClient, "get", return_value=github(repository())):
                result = self.invoke(["market", "refresh", "--category", "pdf", "--search-mode", "web", "--provider", "github", "--state-dir", directory, "--format", "json"])
            after = {p: p.read_bytes() for p in Path(directory).rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result["status"], "search-review-required")
        self.assertFalse(result["reviewed_cache_updated"])
        self.assertEqual(result["searches"][0]["query"], "pdf")

    def test_market_failure_does_not_claim_empty_success_or_refresh(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(external_search.PublicClient, "get", side_effect=external_search.SearchError("timeout")):
            result = self.invoke(["market", "refresh", "--category", "pdf", "--search-mode", "web", "--provider", "github", "--state-dir", directory, "--format", "json"])
        self.assertEqual(result["status"], "search-failed")
        self.assertEqual(result["searches"][0]["status"], "failed")
        self.assertEqual(result["freshness"]["status"], "missing")

    def test_reviewed_import_and_network_mode_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.json"
            path.write_text(json.dumps(RESULTS))
            with patch.object(external_search.PublicClient, "get") as get, redirect_stderr(StringIO()), self.assertRaises(SystemExit) as caught:
                self.invoke(["market", "refresh", "--results", str(path), "--search-mode", "web", "--state-dir", directory, "--format", "json"])
            get.assert_not_called()
            self.assertEqual(caught.exception.code, 2)

    def test_multiple_market_categories_are_separate_queries_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(external_search.PublicClient, "get", return_value=github(repository())):
            result = self.invoke(["market", "refresh", "--category", "pdf", "--category", "design", "--search-mode", "hybrid", "--provider", "github", "--state-dir", directory, "--format", "json"])
            self.assertEqual([r["query"] for r in result["searches"]], ["pdf", "design"])
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                self.invoke(["market", "refresh", *sum((["--category", str(i)] for i in range(4)), []), "--search-mode", "web", "--state-dir", directory, "--format", "json"])

    def test_research_depth_and_search_scope_remain_independent(self):
        args = skill_atlas.parse_args(["recommend", "pdf", "--mode", "benchmark", "--search-mode", "hybrid"])
        self.assertEqual(args.mode, "benchmark")
        self.assertEqual(args.search_mode, "hybrid")

    def test_bad_search_limits_exit_cleanly_before_requests(self):
        with patch.object(external_search.PublicClient, "get") as get, redirect_stderr(StringIO()), self.assertRaises(SystemExit) as caught:
            self.invoke(["discover", "pdf", "--search-mode", "web", "--web-limit", "0", "--format", "json"])
        get.assert_not_called()
        self.assertEqual(caught.exception.code, 2)

    def test_orchestration_retains_external_search_without_executing_candidates(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(external_search.PublicClient, "get", return_value=github(repository())):
            result = self.invoke(["orchestrate", "run", "pdf", "--search-mode", "web", "--provider", "github", "--market-state-dir", directory, "--format", "json"])
        self.assertIn("external_search", result)
        self.assertFalse(result["execution"]["automatic_execution"])

    def test_markdown_recommendation_and_market_include_actual_citations(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(external_search.PublicClient, "get", return_value=github(repository())):
            for command in [["recommend", "tool", "pdf", "--market-state-dir", directory], ["market", "refresh", "--category", "pdf", "--state-dir", directory]]:
                out = self.invoke(command + ["--search-mode", "web", "--provider", "github"])
                self.assertIn("https://github.com/example/pdf-tool", out)
                self.assertIn("review-required", out)


if __name__ == "__main__":
    unittest.main()
