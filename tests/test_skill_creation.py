from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import skill_creation  # noqa: E402


class SkillCreationTests(unittest.TestCase):
    def test_explicit_source_selects_method(self):
        result = skill_creation.build_plan("Build a UX research skill", "masters", None)
        self.assertEqual(result["selected_method"], "skill-from-masters")
        self.assertEqual(result["status"], "plan-only")
        self.assertFalse(result["executed"])

    def test_ambiguous_source_requires_selection(self):
        result = skill_creation.build_plan("Build a useful skill", "auto", None)
        self.assertIsNone(result["selected_method"])

    def test_notebook_source_with_installed_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / "skills/skill-from-notebook/SKILL.md"
            entry.parent.mkdir(parents=True)
            entry.write_text("---\nname: skill-from-notebook\n---")
            result = skill_creation.build_plan("make a skill from my notes", "auto", tmp)
            self.assertEqual(result["status"], "ready-to-invoke")
            self.assertEqual(result["skill_entry"], str(entry))
            self.assertTrue(result["read_only"])
            self.assertFalse(result["executed"])

    def test_missing_kit_does_not_claim_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = skill_creation.build_plan("from GitHub", "github", tmp)
            self.assertEqual(result["status"], "plan-only")
            self.assertIsNone(result["skill_entry"])


if __name__ == "__main__":
    unittest.main()
