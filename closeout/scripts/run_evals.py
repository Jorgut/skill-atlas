#!/usr/bin/env python3
"""Validate closeout evals and grade captured Agent results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


KINDS = {"trigger", "permission", "behavior", "regression"}


class EvalError(ValueError):
    """Raised when an eval suite or result file is invalid."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvalError(f"top-level JSON must be an object: {path}")
    return value


def validate_suite(suite: dict[str, Any]) -> list[dict[str, Any]]:
    if suite.get("schema_version") != 1 or suite.get("skill_name") != "closeout":
        raise EvalError("suite requires schema_version 1 and skill_name closeout")
    cases = suite.get("evals")
    if not isinstance(cases, list) or not cases:
        raise EvalError("suite requires a non-empty evals array")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise EvalError("every eval must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise EvalError(f"eval id must be unique and non-empty: {case_id!r}")
        seen.add(case_id)
        if case.get("kind") not in KINDS:
            raise EvalError(f"invalid kind for {case_id}: {case.get('kind')!r}")
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            raise EvalError(f"missing prompt for {case_id}")
        expected = case.get("expected")
        if not isinstance(expected, dict) or not isinstance(expected.get("triggered"), bool):
            raise EvalError(f"expected.triggered must be boolean for {case_id}")
        for key in ("must_include", "must_not_include", "forbidden_actions"):
            value = expected.get(key, [])
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise EvalError(f"expected.{key} must be a string array for {case_id}")
    return cases


def grade_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    failures: list[str] = []
    if result.get("triggered") is not expected["triggered"]:
        failures.append(f"triggered expected {expected['triggered']}")
    output = str(result.get("output", "")).lower()
    for phrase in expected.get("must_include", []):
        if phrase.lower() not in output:
            failures.append(f"missing output phrase: {phrase}")
    for phrase in expected.get("must_not_include", []):
        if phrase.lower() in output:
            failures.append(f"forbidden output phrase: {phrase}")
    actions = result.get("actions", [])
    if not isinstance(actions, list):
        failures.append("actions must be an array")
        actions = []
    for prefix in expected.get("forbidden_actions", []):
        if any(str(action).startswith(prefix) for action in actions):
            failures.append(f"forbidden action prefix: {prefix}")
    return {"id": case["id"], "passed": not failures, "failures": failures}


def grade(cases: list[dict[str, Any]], captured: dict[str, Any]) -> dict[str, Any]:
    results = captured.get("results")
    if not isinstance(results, list):
        raise EvalError("captured results require a results array")
    by_id = {item.get("id"): item for item in results if isinstance(item, dict)}
    graded = []
    for case in cases:
        result = by_id.get(case["id"])
        if result is None:
            graded.append({"id": case["id"], "passed": False, "failures": ["missing result"]})
        else:
            graded.append(grade_case(case, result))
    passed = sum(item["passed"] for item in graded)
    return {"passed": passed, "total": len(graded), "success": passed == len(graded), "cases": graded}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "grade"))
    parser.add_argument(
        "--suite", default=str(Path(__file__).resolve().parent.parent / "evals" / "evals.json")
    )
    parser.add_argument("--results")
    args = parser.parse_args()
    try:
        cases = validate_suite(load_json(Path(args.suite)))
        if args.command == "validate":
            output = {"valid": True, "cases": len(cases), "kinds": sorted({case["kind"] for case in cases})}
        else:
            if not args.results:
                raise EvalError("grade requires --results")
            output = grade(cases, load_json(Path(args.results)))
    except EvalError as exc:
        parser.error(str(exc))
    print(json.dumps(output, indent=2))
    if args.command == "grade" and not output["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
