#!/usr/bin/env python3
"""Discover explicitly scoped component-library manifests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


MANIFEST_NAME = "component-library.json"
EXCLUDE_DIRS = {".git", ".next", "coverage", "dist", "node_modules"}


class ComponentLibraryError(ValueError):
    pass


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("artifact_type") != "component-library":
        raise ComponentLibraryError(f"Invalid component-library manifest: {path}")
    for field in ("name", "version", "ecosystem"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ComponentLibraryError(f"Component-library manifest requires {field}: {path}")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities or not all(
        isinstance(item, str) and item.strip() for item in capabilities
    ):
        raise ComponentLibraryError(
            f"Component-library manifest requires non-empty capabilities: {path}"
        )
    return {
        **value,
        "manifest_path": str(path),
        "repository_path": str(path.parent),
        "availability": "available-local",
    }


def discover(roots: list[Path]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        root = root.expanduser()
        if root.is_file() and root.name == MANIFEST_NAME:
            paths = [root]
        elif root.is_dir():
            paths = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [name for name in dirnames if name not in EXCLUDE_DIRS]
                if MANIFEST_NAME in filenames:
                    paths.append(Path(dirpath) / MANIFEST_NAME)
        else:
            continue
        for path in paths:
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            found.append(load_manifest(path))
    return sorted(found, key=lambda item: item["name"])


def match(
    libraries: list[dict[str, Any]], capabilities: list[str]
) -> list[dict[str, Any]]:
    requested = set(capabilities)
    matches = []
    for library in libraries:
        matched = [item for item in library["capabilities"] if item in requested]
        if matched:
            matches.append({**library, "matched_capabilities": matched})
    return matches
