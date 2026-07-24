from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import competitor_monitor  # noqa: E402


NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


class CompetitorMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = competitor_monitor.MonitorStore(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_add_is_due_immediately_and_remove(self) -> None:
        monitor = self.store.add("Closeout", "closeout", "weekly", NOW)

        self.assertEqual(monitor["id"], "closeout")
        self.assertEqual([item["id"] for item in self.store.due(NOW)], ["closeout"])
        self.assertEqual(self.store.remove("closeout")["query"], "closeout")
        self.assertEqual(self.store.load()["monitors"], [])

    def test_run_records_schedule_and_candidate_diff(self) -> None:
        self.store.add("UX audit", "ux audit", "monthly", NOW)
        packet = {"mode": "competitor-reference-only", "briefs": []}
        first = self.store.record_run(
            "ux-audit",
            packet,
            {"summary": "first", "candidates": [{"name": "Candidate A"}]},
            NOW,
        )
        second = self.store.record_run(
            "ux-audit",
            packet,
            {"summary": "second", "candidates": [{"name": "Candidate B"}]},
            datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["changes"]["added"], ["Candidate B"])
        self.assertEqual(second["changes"]["removed"], ["Candidate A"])
        monitor = self.store.load()["monitors"][0]
        self.assertEqual(monitor["next_run_at"], "2026-09-23T12:00:00Z")

    def test_research_only_run_is_honest_about_external_work(self) -> None:
        self.store.add("Animation", "animation models and skills", "weekly", NOW)
        snapshot = self.store.record_run("animation", {"briefs": [{"name": "animation"}]}, now=NOW)

        self.assertEqual(snapshot["status"], "research-required")
        self.assertIsNone(snapshot["changes"])
        self.assertEqual([item["id"] for item in self.store.due(NOW)], ["animation"])
        saved = json.loads(Path(self.store.load()["monitors"][0]["last_snapshot"]).read_text())
        self.assertEqual(saved["status"], "research-required")

    def test_results_require_identifiable_candidates(self) -> None:
        with self.assertRaisesRegex(competitor_monitor.MonitorError, "name, url, or repository"):
            competitor_monitor.validate_results({"candidates": [{}]})


if __name__ == "__main__":
    unittest.main()
