from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import component_libraries  # noqa: E402


class ComponentLibraryTests(unittest.TestCase):
    def test_discovers_and_matches_explicit_component_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "artifact_type": "component-library",
                "name": "@jorgut/liquid-glass",
                "version": "0.1.0",
                "ecosystem": "react",
                "capabilities": ["frontend-ui", "design-ux"],
            }
            (root / "component-library.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            libraries = component_libraries.discover([root])
            matches = component_libraries.match(libraries, ["frontend-ui"])

        self.assertEqual(libraries[0]["availability"], "available-local")
        self.assertEqual(matches[0]["name"], "@jorgut/liquid-glass")
        self.assertEqual(matches[0]["matched_capabilities"], ["frontend-ui"])

    def test_rejects_untyped_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "component-library.json"
            path.write_text('{"name": "not-enough"}', encoding="utf-8")

            with self.assertRaises(component_libraries.ComponentLibraryError):
                component_libraries.discover([Path(directory)])


if __name__ == "__main__":
    unittest.main()
