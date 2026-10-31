from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import install_skill_atlas  # noqa: E402


class InstallSkillAtlasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.source = root / "source"
        self.home = root / "home"
        (self.source / "commands").mkdir(parents=True)
        (self.source / "SKILL.md").write_text(
            "---\nname: skill-atlas\ndescription: Test package\n---\n",
            encoding="utf-8",
        )
        (self.source / "skill.json").write_text(
            json.dumps({"name": "skill-atlas", "version": "1.0.0"}),
            encoding="utf-8",
        )
        (self.source / "commands/skill-atlas.md").write_text(
            "---\ndescription: Test command\n---\nUse skill-atlas.\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def args(self, **overrides: object) -> argparse.Namespace:
        values: dict[str, object] = {
            "all_platforms": True,
            "platform": [],
            "commands": True,
            "with_closeout": False,
            "source": str(self.source),
            "home": str(self.home),
            "apply": False,
            "confirm": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_preview_does_not_create_files(self) -> None:
        result = install_skill_atlas.run(self.args())

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["read_only"])
        self.assertFalse(self.home.exists())

    def test_apply_installs_once_and_is_idempotent(self) -> None:
        result = install_skill_atlas.run(self.args(apply=True, confirm=True))

        canonical = self.home / ".agents/skills/skill-atlas"
        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["slash_commands"], ["/skill-atlas"])
        self.assertTrue((canonical / "SKILL.md").is_file())
        for path in [
            self.home / ".codex/skills/skill-atlas",
            self.home / ".config/opencode/skills/skill-atlas",
            self.home / ".claude/skills/skill-atlas",
            self.home / ".config/opencode/commands/skill-atlas.md",
            self.home / ".claude/commands/skill-atlas.md",
        ]:
            self.assertTrue(path.is_symlink())
        self.assertFalse((self.home / ".codex/commands/skill-atlas.md").exists())

        repeated = install_skill_atlas.run(self.args(apply=True, confirm=True))
        self.assertEqual(repeated["status"], "already-installed")
        self.assertEqual(repeated["created"], [])

    def test_conflict_refuses_before_creating_canonical_install(self) -> None:
        conflict = self.home / ".config/opencode/commands/skill-atlas.md"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("do not overwrite", encoding="utf-8")

        with self.assertRaises(install_skill_atlas.InstallError):
            install_skill_atlas.run(self.args(apply=True, confirm=True))

        self.assertEqual(conflict.read_text(encoding="utf-8"), "do not overwrite")
        self.assertFalse((self.home / ".agents/skills/skill-atlas").exists())


    def test_optional_bundled_closeout_links(self) -> None:
        (self.source / "closeout/commands").mkdir(parents=True)
        (self.source / "closeout/SKILL.md").write_text("---\nname: closeout\n---\n")
        (self.source / "closeout/commands/closeout.md").write_text("Use closeout.")
        result = install_skill_atlas.run(self.args(with_closeout=True, apply=True, confirm=True))
        self.assertEqual(result["status"], "installed")
        for path in [
            self.home / ".agents/skills/closeout",
            self.home / ".codex/skills/closeout",
            self.home / ".config/opencode/skills/closeout",
            self.home / ".claude/skills/closeout",
            self.home / ".config/opencode/commands/closeout.md",
            self.home / ".claude/commands/closeout.md",
        ]:
            self.assertTrue(path.is_symlink(), str(path))
        self.assertEqual(install_skill_atlas.run(
            self.args(with_closeout=True, apply=True, confirm=True)
        )["status"], "already-installed")

    def test_existing_closeout_is_not_overwritten(self) -> None:
        (self.source / "closeout").mkdir()
        (self.source / "closeout/SKILL.md").write_text("---\nname: closeout\n---\n")
        old = self.home / ".agents/skills/closeout"
        old.parent.mkdir(parents=True)
        old.mkdir()
        (old / "SKILL.md").write_text("preserve this independent installation")
        plan = install_skill_atlas.run(self.args(with_closeout=True))
        self.assertEqual(plan["status"], "conflict")
        self.assertFalse((self.home / ".agents/skills/skill-atlas").exists())
        with self.assertRaises(install_skill_atlas.InstallError):
            install_skill_atlas.run(self.args(with_closeout=True, apply=True, confirm=True))
        self.assertEqual((old / "SKILL.md").read_text(), "preserve this independent installation")

    def test_apply_requires_matching_confirmation(self) -> None:
        with self.assertRaisesRegex(install_skill_atlas.InstallError, "both --apply and --confirm"):
            install_skill_atlas.run(self.args(apply=True, confirm=False))
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
