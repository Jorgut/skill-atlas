from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import skill_atlas  # noqa: E402
import start_guide  # noqa: E402


class StartGuideTests(unittest.TestCase):
    def test_guide_has_quickstart_and_links(self):
        guide = start_guide.guide()
        self.assertEqual(guide["version"], json.loads((ROOT / "skill.json").read_text())["version"])
        self.assertEqual(len(guide["quickstart"]), 5)
        self.assertTrue(any("agents scan" in item["command"] for item in guide["quickstart"]))
        self.assertTrue(any("sync setup" in item["command"] for item in guide["quickstart"]))
        self.assertTrue(all(item["doc"].startswith("https://github.com/Jorgut/skill-atlas") for item in guide["workflows"]))

    def test_markdown_output(self):
        out = StringIO()
        with redirect_stdout(out):
            start_guide.emit_markdown(start_guide.guide())
        text = out.getvalue()
        self.assertIn("# Welcome to Skill Atlas", text)
        self.assertIn("## Quickstart", text)
        self.assertIn("sync setup", text)

    def test_cli_json_output(self):
        args = skill_atlas.parse_args(["start", "--format", "json"])
        out = StringIO()
        with redirect_stdout(out):
            args.handler(args)
        result = json.loads(out.getvalue())
        self.assertIn("quickstart", result)
        self.assertIn("safety", result)


if __name__ == "__main__":
    unittest.main()
