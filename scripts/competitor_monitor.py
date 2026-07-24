#!/usr/bin/env python3
"""Persist competitor-monitor schedules and comparison snapshots."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "quarterly": timedelta(days=90),
}


class MonitorError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise MonitorError("Monitor name must contain at least one letter or number.")
    return slug


class MonitorStore:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir.expanduser()
        self.config_path = self.state_dir / "monitors.json"
        self.runs_dir = self.state_dir / "runs"

    def load(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"schema_version": 1, "monitors": []}
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not isinstance(data.get("monitors"), list):
            raise MonitorError(f"Unsupported monitor state: {self.config_path}")
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.config_path)

    def add(self, name: str, query: str, interval: str, now: datetime | None = None) -> dict[str, Any]:
        if interval not in INTERVALS:
            raise MonitorError(f"Unsupported interval: {interval}")
        now = now or utc_now()
        monitor_id = slugify(name)
        data = self.load()
        if any(item["id"] == monitor_id for item in data["monitors"]):
            raise MonitorError(f"Monitor already exists: {monitor_id}")
        monitor = {
            "id": monitor_id,
            "name": name.strip(),
            "query": query.strip(),
            "interval": interval,
            "created_at": format_time(now),
            "last_run_at": None,
            "last_packet_at": None,
            "next_run_at": format_time(now),
            "last_snapshot": None,
        }
        if not monitor["query"]:
            raise MonitorError("Competitor query cannot be empty.")
        data["monitors"].append(monitor)
        self.save(data)
        return monitor

    def get(self, monitor_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        data = self.load()
        for monitor in data["monitors"]:
            if monitor["id"] == monitor_id:
                return data, monitor
        raise MonitorError(f"Unknown monitor: {monitor_id}")

    def remove(self, monitor_id: str) -> dict[str, Any]:
        data, monitor = self.get(monitor_id)
        data["monitors"] = [item for item in data["monitors"] if item["id"] != monitor_id]
        self.save(data)
        return monitor

    def due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or utc_now()
        return [
            monitor for monitor in self.load()["monitors"]
            if parse_time(monitor["next_run_at"]) <= now
        ]

    def history(self, monitor_id: str) -> list[dict[str, Any]]:
        self.get(monitor_id)
        directory = self.runs_dir / monitor_id
        if not directory.exists():
            return []
        return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]

    def record_run(
        self,
        monitor_id: str,
        research_packet: dict[str, Any],
        results: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        data, monitor = self.get(monitor_id)
        previous = [item for item in self.history(monitor_id) if item.get("status") == "completed"]
        candidates = results.get("candidates", []) if results else []
        current_keys = {candidate_key(item) for item in candidates}
        previous_keys = {
            candidate_key(item) for item in previous[-1].get("candidates", [])
        } if previous else set()
        snapshot = {
            "monitor_id": monitor_id,
            "run_at": format_time(now),
            "status": "completed" if results else "research-required",
            "query": monitor["query"],
            "research_packet": research_packet,
            "candidates": candidates,
            "summary": results.get("summary", "") if results else "",
            "changes": {
                "added": sorted(current_keys - previous_keys),
                "removed": sorted(previous_keys - current_keys),
                "unchanged": sorted(current_keys & previous_keys),
            } if results else None,
        }
        run_dir = self.runs_dir / monitor_id
        run_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{snapshot['status']}.json"
        snapshot_path = run_dir / filename
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if results:
            monitor["last_run_at"] = format_time(now)
            monitor["next_run_at"] = format_time(now + INTERVALS[monitor["interval"]])
        else:
            monitor["last_packet_at"] = format_time(now)
        monitor["last_snapshot"] = str(snapshot_path)
        self.save(data)
        return snapshot


def candidate_key(candidate: dict[str, Any]) -> str:
    return str(candidate.get("url") or candidate.get("repository") or candidate.get("name") or "").strip()


def validate_results(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("candidates"), list):
        raise MonitorError("Results JSON must be an object with a candidates array.")
    for candidate in value["candidates"]:
        if not isinstance(candidate, dict) or not candidate_key(candidate):
            raise MonitorError("Every candidate must have a non-empty name, url, or repository.")
    if "summary" in value and not isinstance(value["summary"], str):
        raise MonitorError("Results summary must be a string.")
    return value
