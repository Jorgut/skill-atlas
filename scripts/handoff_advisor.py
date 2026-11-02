#!/usr/bin/env python3
"""Read-only, evidence-aware model and agent advice before a task handoff."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_handoff

TASK_AREAS = ("code", "visual-understanding", "image-generation",
              "writing", "research", "3d")
DEFAULT_TOOLS = {
    "code": ("filesystem", "terminal", "git"),
    "visual-understanding": ("image-input",),
    "image-generation": ("image-generation",),
    "writing": (),
    "research": ("web",),
    "3d": ("filesystem", "terminal"),
}
PATTERNS = [
    ("image-generation", r"generate (an? )?image|create (an? )?image|render image|生成.{0,4}(图|画)|出图|文生图"),
    ("visual-understanding", r"image review|screenshot|visual audit|视觉审查|截图|识别图片|看图"),
    ("3d", r"blender|rhino|three\.js|3d|建模|三维"),
    ("code", r"code|debug|fix|react|python|javascript|typescript|frontend|backend|canvas|test|api|bug|"
     r"代码|修复|开发|编程|交互|画布|测试|缩放|拖拽"),
    ("research", r"research|search|investigate|研究|调研|检索|搜集"),
    ("writing", r"write|edit article|translate|memo|draft|文字|撰写|翻译|文章|写作"),
]
WEIGHTS = {"task_fit": 35, "measured_quality": 25, "tool_fit": 20,
           "user_cost_assessment": 15, "user_risk_assessment": 5}
FRESH_DAYS = 90


class AdviceError(ValueError):
    """Refuse malformed data instead of inventing candidate attributes."""


def _check_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdviceError(f"{name} must be a nonempty string")
    return value.strip()


def _names(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise AdviceError(f"{name} must be a list of strings")
    return list(dict.fromkeys(value))


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _recent(date_str: Any, max_days: int = FRESH_DAYS) -> bool:
    if not isinstance(date_str, str):
        return False
    try:
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if date.tzinfo is None:
            return False
        age = datetime.now(timezone.utc) - date.astimezone(timezone.utc)
        return -1 <= age.total_seconds() / 86400 <= max_days
    except (ValueError, OverflowError):
        return False


def read_registry(project_root: Path, profiles: str | None) -> tuple[dict[str, Any] | None, str]:
    target = (Path(profiles).expanduser().resolve() if profiles else
              project_root / ".skill-atlas" / "model-agent-profiles.json")
    if not target.is_file():
        return None, str(target)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdviceError("Model/Agent profile JSON could not be read") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise AdviceError("Profiles require schema_version=1")
    for category in ("models", "agents"):
        if not isinstance(data.get(category), list):
            raise AdviceError(f"Profiles require a {category} list")
        ids: set[str] = set()
        for entry in data[category]:
            if not isinstance(entry, dict):
                raise AdviceError(f"{category} entries must be objects")
            id_ = _check_str(entry.get("id"), f"{category}.id")
            if id_ in ids:
                raise AdviceError(f"Duplicate {category} id: {id_}")
            ids.add(id_)
            if category == "models":
                _names(entry.get("capabilities"), f"{id_}.capabilities")
                _check_str(entry.get("capability_evidence"), f"{id_}.capability_evidence")
            else:
                _names(entry.get("supported_models"), f"{id_}.supported_models")
                _names(entry.get("tools"), f"{id_}.tools")
            access = entry.get("access_status", "unknown")
            if access not in {"unknown", "configured", "unavailable"}:
                raise AdviceError(f"{id_}.access_status must be unknown/configured/unavailable")
    return data, str(target)


def task_area(description: str, override: str | None = None) -> str | None:
    if override is not None:
        if override not in TASK_AREAS:
            raise AdviceError(f"Unknown task type: {override}")
        return override
    for area, expression in PATTERNS:
        if re.search(expression, description, flags=re.IGNORECASE):
            return area
    return None


def _quality(model: dict[str, Any], area: str) -> tuple[float | None, str]:
    value = model.get("task_evaluations", {})
    if not isinstance(value, dict):
        return None, "invalid evaluation format"
    evaluation = value.get(area, {})
    if not isinstance(evaluation, dict):
        return None, "no comparable evaluation"
    rate = evaluation.get("success_rate")
    count = evaluation.get("sample_size")
    if not _number(rate) or not isinstance(count, int) or isinstance(count, bool) or count < 5:
        return None, "insufficient task-specific trials (minimum 5)"
    if not _recent(evaluation.get("measured_at")):
        return None, "evaluation missing or stale (90-day window)"
    return float(rate), f"{count} task-specific trials, updated {evaluation['measured_at']}"


def _declared_score(entry: dict[str, Any], key: str) -> float | None:
    value = entry.get(key)
    return float(value) if _number(value) else None


def evaluate(registry: dict[str, Any], area: str, required_tools: list[str]) -> dict[str, Any]:
    models = {m["id"]: m for m in registry["models"]}
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for agent in registry["agents"]:
        for model_id in agent["supported_models"]:
            model = models.get(model_id)
            if model is None:
                exclusions.append({"agent": agent["id"], "model": model_id,
                                   "reason": "model not present in local registry"})
                continue
            missing = sorted(set(required_tools) - set(agent["tools"]))
            if area not in model["capabilities"] or missing:
                exclusions.append({
                    "agent": agent["id"], "model": model_id,
                    "reason": "model capability mismatch" if area not in model["capabilities"]
                              else "missing required tools: " + ", ".join(missing),
                })
                continue
            if agent.get("access_status") == "unavailable" or model.get("access_status") == "unavailable":
                exclusions.append({"agent": agent["id"], "model": model_id,
                                   "reason": "marked unavailable in local registry"})
                continue
            quality, quality_evidence = _quality(model, area)
            cost = _declared_score(model, "user_cost_score")
            risk = _declared_score(agent, "handoff_safety_score")
            minimum = WEIGHTS["task_fit"] + WEIGHTS["tool_fit"]
            maximum = minimum
            evidence: list[str] = [
                "declared model task capability: " + model["capability_evidence"],
                "declared Agent tool coverage: " + ", ".join(required_tools or ["none"]),
                "access status is local configuration only, not live quota availability",
            ]
            missing_evidence = []
            for weight, value, label in [
                (WEIGHTS["measured_quality"], quality, "measured_quality"),
                (WEIGHTS["user_cost_assessment"], cost, "user_cost_assessment"),
                (WEIGHTS["user_risk_assessment"], risk, "user_risk_assessment"),
            ]:
                if value is None:
                    maximum += weight
                    missing_evidence.append(label)
                else:
                    minimum += weight * value
                    maximum += weight * value
            evidence.append("quality: " + quality_evidence)
            if cost is not None:
                evidence.append("user-supplied cost score (not a live quote)")
            if risk is not None:
                evidence.append("user-supplied handoff safety score")
            candidates.append({
                "agent": agent["id"],
                "model": model_id,
                "score_lower_bound": round(minimum, 1),
                "score_upper_bound": round(maximum, 1),
                "missing_evidence": missing_evidence,
                "evidence": evidence,
                "access_status": {
                    "agent": agent.get("access_status", "unknown"),
                    "model": model.get("access_status", "unknown"),
                },
                "live_availability_verified": False,
            })
    candidates.sort(key=lambda x: (-x["score_lower_bound"], x["agent"], x["model"]))
    if not candidates:
        return {"status": "no-eligible-candidates", "shortlist": [],
                "exclusions": exclusions, "primary": None}
    first = candidates[0]
    # Never declare a numerical winner while outcomes can overlap or access is unverified.
    guaranteed = (
        len(candidates) == 1 or
        first["score_lower_bound"] > max(x["score_upper_bound"] for x in candidates[1:])
    )
    comparable = not first["missing_evidence"] and guaranteed
    return {
        "status": "evidence-ranked" if comparable else "provisional-shortlist",
        "primary": {"agent": first["agent"], "model": first["model"]} if comparable else None,
        "shortlist": candidates,
        "exclusions": exclusions,
        "why_no_primary": None if comparable else "Insufficient comparable evidence or overlapping score intervals",
    }


def advise(args: argparse.Namespace) -> dict[str, Any]:
    root = agent_handoff.repo_root(args.project)
    state = agent_handoff.inspect_checkpoint(argparse.Namespace(project=str(root), task=args.task))
    checkpoint = state.get("checkpoint") or {}
    description = (args.description or checkpoint.get("next_action") or "").strip()
    area = task_area(description, args.task_type)
    result: dict[str, Any] = {
        "action": "handoff-advise",
        "read_only": True,
        "automatic_dispatch": False,
        "no_provider_authentication_or_quota_checks": True,
        "task": args.task,
        "task_description": description,
        "task_type": area,
        "checkpoint_status": state["status"],
        "handoff_ready": state["status"] == "checkpoint-consistent",
        "checkpoint_changed_fields": state.get("changed_fields", []),
        "weights": WEIGHTS,
        "profiles_file": None,
    }
    registry, path = read_registry(root, args.profiles)
    result["profiles_file"] = path
    if not description or area is None:
        result.update(status="needs-task-description-or-type", shortlist=[], primary=None)
        return result
    required = sorted(set(DEFAULT_TOOLS[area]) | set(args.required_tool or []))
    result["required_tools"] = required
    if registry is None:
        result.update(status="needs-profiles", shortlist=[], primary=None,
                      next_action="Provide a reviewed local model-agent-profiles.json; no model scores were assumed")
        return result
    result.update(evaluate(registry, area, required))
    if state["status"] != "checkpoint-consistent":
        result["handoff_ready"] = False
        result["next_action"] = "Reconcile Git status and task ownership before transfer"
    elif result["status"] != "evidence-ranked":
        result["next_action"] = "Review candidate capability, access, and missing benchmarks manually"
    else:
        result["next_action"] = "Verify current provider access and select the proposed pair manually"
    return result


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", default=".")
    parser.add_argument("--task", required=True)
    parser.add_argument("--description", help="Next task; defaults to the saved checkpoint next action")
    parser.add_argument("--task-type", choices=TASK_AREAS)
    parser.add_argument("--required-tool", action="append", default=[],
                        help="Additional required tool, repeatable")
    parser.add_argument("--profiles", help="Explicit local Model/Agent JSON registry")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")


def emit_markdown(result: dict[str, Any]) -> None:
    print("# Skill Atlas Model-Aware Handoff")
    print(f"- status: {result['status']}")
    print(f"- task: {result['task']}")
    print(f"- task area: {result['task_type']}")
    print(f"- checkpoint status: {result['checkpoint_status']}")
    print(f"- handoff ready: {result['handoff_ready']}")
    print(f"- profiles: {result['profiles_file']}")
    if result.get("primary"):
        pair = result["primary"]
        print(f"- proposed pair: {pair['agent']} + {pair['model']} (not live-verified)")
    for item in result.get("shortlist", []):
        print(f"- candidate: {item['agent']} + {item['model']}, "
              f"evidence score range {item['score_lower_bound']}..{item['score_upper_bound']}")
        print(f"  - missing evidence: {', '.join(item['missing_evidence']) or 'none'}")
    if result.get("next_action"):
        print(f"- next: {result['next_action']}")
    print("- no authentication, quota check, model switch, file modification or agent dispatch executed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = parser.parse_args()
    try:
        result = advise(args)
    except (agent_handoff.HandoffError, AdviceError) as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_markdown(result)


if __name__ == "__main__":
    main()
