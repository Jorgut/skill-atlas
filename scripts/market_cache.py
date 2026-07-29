#!/usr/bin/env python3
"""Persist reviewed public skill-market snapshots and report freshness."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_SOURCE_TYPES = ("marketplace", "official-or-github", "community")
SOURCE_TYPES = set(REQUIRED_SOURCE_TYPES)
MODE_TTL_HOURS = {"quick": 168, "balanced": 24, "benchmark": 0}


class MarketCacheError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_results(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MarketCacheError("Market results must be a JSON object.")
    sources = value.get("sources")
    candidates = value.get("candidates")
    if not isinstance(sources, list) or not isinstance(candidates, list):
        raise MarketCacheError("Market results require sources and candidates arrays.")

    covered: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise MarketCacheError("Every source must be an object.")
        source_type = source.get("type")
        if source_type not in SOURCE_TYPES:
            raise MarketCacheError(f"Unsupported market source type: {source_type}")
        if not str(source.get("name", "")).strip() or not str(source.get("url", "")).strip():
            raise MarketCacheError("Every source requires a name and URL.")
        covered.add(source_type)

    missing = [source_type for source_type in REQUIRED_SOURCE_TYPES if source_type not in covered]
    if missing:
        raise MarketCacheError(f"Market results are missing source coverage: {', '.join(missing)}")

    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise MarketCacheError("Every candidate must be an object.")
        if not str(candidate.get("name", "")).strip() or not str(candidate.get("url", "")).strip():
            raise MarketCacheError("Every candidate requires a name and URL.")
        capabilities = candidate.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities or not all(
            isinstance(item, str) and item.strip() for item in capabilities
        ):
            raise MarketCacheError("Every candidate requires a non-empty capabilities array.")
    return value


class MarketCache:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir.expanduser()
        self.snapshot_path = self.state_dir / "market" / "latest.json"

    def load(self) -> dict[str, Any] | None:
        if not self.snapshot_path.exists():
            return None
        value = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        if value.get("schema_version") != 1 or value.get("status") != "completed":
            raise MarketCacheError(f"Unsupported market snapshot: {self.snapshot_path}")
        validate_results(value)
        if not isinstance(value.get("researched_at"), str):
            raise MarketCacheError("Market snapshot requires researched_at.")
        try:
            parse_time(value["researched_at"])
        except ValueError as exc:
            raise MarketCacheError("Market snapshot has an invalid researched_at value.") from exc
        return value

    def status(self, ttl_hours: int, now: datetime | None = None) -> dict[str, Any]:
        if ttl_hours < 0:
            raise MarketCacheError("Market TTL cannot be negative.")
        now = now or utc_now()
        snapshot = self.load()
        if snapshot is None:
            return {
                "status": "missing",
                "fresh": False,
                "ttl_hours": ttl_hours,
                "age_hours": None,
                "researched_at": None,
                "snapshot": None,
                "source_types": [],
                "candidate_count": 0,
            }
        researched_at = parse_time(snapshot["researched_at"])
        age_hours = max(0.0, (now - researched_at).total_seconds() / 3600)
        fresh = age_hours <= ttl_hours
        return {
            "status": "fresh" if fresh else "stale",
            "fresh": fresh,
            "ttl_hours": ttl_hours,
            "age_hours": round(age_hours, 2),
            "researched_at": snapshot["researched_at"],
            "snapshot": str(self.snapshot_path),
            "source_types": sorted({source["type"] for source in snapshot["sources"]}),
            "candidate_count": len(snapshot["candidates"]),
        }

    def save(self, results: Any, now: datetime | None = None) -> dict[str, Any]:
        reviewed = validate_results(results)
        now = now or utc_now()
        snapshot = {
            "schema_version": 1,
            "status": "completed",
            "researched_at": format_time(now),
            "sources": reviewed["sources"],
            "candidates": reviewed["candidates"],
            "summary": reviewed.get("summary", ""),
        }
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.snapshot_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.snapshot_path)
        return snapshot


def refresh_required(
    mode: str,
    cache_status: dict[str, Any],
    force_refresh: bool,
    has_gaps: bool,
) -> bool:
    if force_refresh or mode == "benchmark":
        return True
    if mode == "balanced":
        return not cache_status["fresh"]
    return has_gaps and not cache_status["fresh"]
