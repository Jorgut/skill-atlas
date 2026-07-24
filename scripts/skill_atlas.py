#!/usr/bin/env python3
"""Unified command-line entry point for Skill Atlas."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import audit_skills
import competitor_monitor
import discovery_brief
import install_skill_atlas
import recommend_skills
import self_update


MANAGE_ACTIONS = {"scan", "status", "update", "dedupe", "sync", "self"}
DISCOVER_ACTIONS = {"similar", "competitors", "alternatives", "gaps"}
RECOMMEND_ACTIONS = {"product", "task", "model", "tool"}
ORCHESTRATE_ACTIONS = {"plan", "validate", "run"}
MONITOR_ACTIONS = {"add", "list", "status", "due", "run", "history", "remove"}


def add_output(parser: argparse.ArgumentParser, choices: list[str]) -> None:
    parser.add_argument("--format", choices=choices, default="markdown")


def add_roots(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", action="append", default=[], help="Skill root to scan. May be repeated.")


def roots_for(args: argparse.Namespace) -> list[Path]:
    return [Path(value).expanduser() for value in args.root] if args.root else audit_skills.DEFAULT_ROOTS


def records_for(args: argparse.Namespace, check_upstream: bool = False) -> list[audit_skills.SkillRecord]:
    return audit_skills.build_records(roots_for(args), check_upstream)


def json_print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def manage_plan(records: list[audit_skills.SkillRecord], action: str) -> dict[str, Any]:
    by_name: dict[str, list[audit_skills.SkillRecord]] = defaultdict(list)
    for record in records:
        by_name[record.name].append(record)

    if action == "update":
        candidates = [
            {
                "name": record.name,
                "path": record.path,
                "upstream": record.upstream_url,
                "status": record.update_status,
                "required_before_apply": ["backup", "diff review", "security review", "explicit confirmation"],
            }
            for record in records
            if record.update_status in {"differs", "fetch-failed"}
        ]
        return {"action": "update-plan", "read_only": True, "candidates": candidates}

    duplicates = []
    for name, items in sorted(by_name.items()):
        real_paths = {str(Path(item.path).resolve()) for item in items}
        if len(items) < 2 or len(real_paths) < 2:
            continue
        duplicates.append(
            {
                "name": name,
                "paths": [item.path for item in items],
                "physical_targets": len(real_paths),
                "maintenance_classes": sorted({item.maintenance_class for item in items}),
            }
        )
    if action == "dedupe":
        return {
            "action": "dedupe-plan",
            "read_only": True,
            "duplicates": duplicates,
            "rule": "Never replace user-authored skills or delete copies without explicit confirmation.",
        }
    return {
        "action": "sync-plan",
        "read_only": True,
        "candidates": duplicates,
        "rule": "Choose a user-controlled canonical directory, verify platform loading, back up copies, then request confirmation before creating symlinks.",
    }


def emit_plan_markdown(plan: dict[str, Any]) -> None:
    print(f"# Skill Atlas {plan['action'].replace('-', ' ').title()}")
    print()
    print("- mode: read-only planning")
    items = plan.get("candidates", plan.get("duplicates", []))
    print(f"- candidates: {len(items)}")
    print()
    for item in items:
        print(f"- {item['name']}")
        if item.get("status"):
            print(f"  - status: {item['status']}")
        if item.get("upstream"):
            print(f"  - upstream: {item['upstream']}")
        for path in item.get("paths", [item.get("path", "")]):
            if path:
                print(f"  - path: `{path}`")
    if plan.get("rule"):
        print()
        print(f"Safety: {plan['rule']}")
    print()
    print("No files, links, or installed skills were changed.")


def handle_manage(args: argparse.Namespace) -> None:
    if args.action in {"scan", "status"}:
        records = records_for(args, args.check_upstream)
        if args.format == "json":
            audit_skills.emit_json(records)
        elif args.format == "tsv":
            audit_skills.emit_tsv(records)
        else:
            audit_skills.emit_markdown(records)
        return
    plan = manage_plan(records_for(args, args.action == "update"), args.action)
    json_print(plan) if args.format == "json" else emit_plan_markdown(plan)


def handle_manage_self(args: argparse.Namespace) -> None:
    try:
        result = self_update.run(args)
    except (OSError, self_update.UpdateError) as exc:
        result = {"action": f"self-{args.action}", "status": "refused", "error": str(exc)}
        json_print(result) if args.format == "json" else self_update.emit_markdown(result)
        raise SystemExit(2) from None
    json_print(result) if args.format == "json" else self_update.emit_markdown(result)


def handle_install(args: argparse.Namespace) -> None:
    try:
        result = install_skill_atlas.run(args)
    except (OSError, install_skill_atlas.InstallError, self_update.UpdateError) as exc:
        result = {"action": "install", "status": "refused", "error": str(exc)}
        json_print(result) if args.format == "json" else print(f"Installation refused: {exc}")
        raise SystemExit(2) from None
    json_print(result) if args.format == "json" else install_skill_atlas.emit_markdown(result)


def discovery_records(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [asdict(record) for record in records_for(args)]


def discovery_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "gaps":
        result = recommend_skills.build_recommendation(
            args.query, discovery_records(args), min(args.limit, 5)
        )
        return {
            "mode": "capability-gaps",
            "request": args.query,
            "gaps": result["external_search_gaps"],
            "research_targets": result["external_research_targets"],
        }
    briefs = discovery_brief.skill_briefs(discovery_records(args), args.query)
    mode = {
        "similar": "similar-skills",
        "competitors": "competitor-reference-only",
        "alternatives": "replacement-or-complement",
    }[args.action]
    return {
        "mode": mode,
        "focus": args.query,
        "briefs": briefs[: args.limit],
        "rule": "Do not replace user-authored skills; competitor results are references only."
        if args.action == "competitors"
        else "Review source, license, maintenance, compatibility, and security before adoption.",
    }


def emit_discovery_markdown(payload: dict[str, Any]) -> None:
    print("# Skill Atlas Discovery")
    print()
    print(f"- mode: {payload['mode']}")
    if payload.get("focus"):
        print(f"- focus: {payload['focus']}")
    print()
    if "briefs" in payload:
        for brief in payload["briefs"]:
            print(f"- {brief['name']}")
            for query in brief["discovery_queries"]:
                print(f"  - `{query}`")
    else:
        for gap in payload["gaps"]:
            print(f"- {gap['capability_label']}")
            for query in gap["queries"]:
                print(f"  - `{query}`")
        for target in payload["research_targets"]:
            print(f"- {target['subject']} ({target['type']})")
            for query in target["queries"]:
                print(f"  - `{query}`")
    if payload.get("rule"):
        print()
        print(f"Safety: {payload['rule']}")


def handle_discover(args: argparse.Namespace) -> None:
    payload = discovery_payload(args)
    json_print(payload) if args.format == "json" else emit_discovery_markdown(payload)


def monitor_store(args: argparse.Namespace) -> competitor_monitor.MonitorStore:
    return competitor_monitor.MonitorStore(Path(args.state_dir))


def monitor_status(store: competitor_monitor.MonitorStore, monitor: dict[str, Any]) -> dict[str, Any]:
    result = dict(monitor)
    result["due"] = competitor_monitor.parse_time(monitor["next_run_at"]) <= competitor_monitor.utc_now()
    result["history_count"] = len(store.history(monitor["id"]))
    return result


def emit_monitor_markdown(payload: dict[str, Any]) -> None:
    print(f"# Skill Atlas Monitor {payload['action'].title()}")
    print()
    if payload.get("message"):
        print(payload["message"])
        print()
    monitors = payload.get("monitors", [])
    for monitor in monitors:
        print(f"- {monitor['id']}: {monitor['query']}")
        if monitor.get("interval"):
            print(f"  - interval: {monitor['interval']}")
        if monitor.get("next_run_at"):
            print(f"  - next run: {monitor['next_run_at']}")
        if "due" in monitor:
            print(f"  - due: {str(monitor['due']).lower()}")
        if "history_count" in monitor:
            print(f"  - snapshots: {monitor['history_count']}")
    if payload.get("snapshot"):
        snapshot = payload["snapshot"]
        print(f"- monitor: {snapshot['monitor_id']}")
        print(f"- status: {snapshot['status']}")
        print(f"- snapshot: {payload['snapshot_path']}")
        if snapshot["status"] == "research-required":
            print("- next step: let an Agent perform the packet's web research, security review, and scoring, then rerun with --results")
        elif snapshot.get("changes"):
            print(f"- added: {len(snapshot['changes']['added'])}")
            print(f"- removed: {len(snapshot['changes']['removed'])}")
            print(f"- unchanged: {len(snapshot['changes']['unchanged'])}")
    if payload.get("history") is not None:
        for snapshot in payload["history"]:
            print(f"- {snapshot['run_at']}: {snapshot['status']} ({len(snapshot.get('candidates', []))} candidates)")


def handle_monitor(args: argparse.Namespace) -> None:
    store = monitor_store(args)
    try:
        if args.action == "add":
            monitor = store.add(args.name, args.query or args.name, args.interval)
            payload = {"action": "add", "monitors": [monitor], "message": "Monitor created and due immediately."}
        elif args.action == "list":
            payload = {"action": "list", "monitors": store.load()["monitors"]}
        elif args.action == "status":
            _, monitor = store.get(args.monitor_id)
            payload = {"action": "status", "monitors": [monitor_status(store, monitor)]}
        elif args.action == "due":
            payload = {"action": "due", "monitors": store.due()}
        elif args.action == "remove":
            if not args.confirm:
                raise competitor_monitor.MonitorError("Removing a monitor requires --confirm.")
            removed = store.remove(args.monitor_id)
            payload = {"action": "remove", "monitors": [removed], "message": "Monitor configuration removed; snapshots were retained."}
        elif args.action == "history":
            payload = {"action": "history", "history": store.history(args.monitor_id), "monitors": []}
        else:
            _, monitor = store.get(args.monitor_id)
            discovery_args = argparse.Namespace(
                action="competitors",
                query=monitor["query"],
                root=args.root,
                limit=args.limit,
            )
            packet = discovery_payload(discovery_args)
            results = competitor_monitor.validate_results(
                json.loads(Path(args.results).read_text(encoding="utf-8"))
            ) if args.results else None
            snapshot = store.record_run(args.monitor_id, packet, results)
            _, updated_monitor = store.get(args.monitor_id)
            payload = {
                "action": "run",
                "snapshot": snapshot,
                "snapshot_path": updated_monitor["last_snapshot"],
                "monitors": [],
            }
    except (OSError, json.JSONDecodeError, competitor_monitor.MonitorError) as exc:
        print(f"Monitor refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    json_print(payload) if args.format == "json" else emit_monitor_markdown(payload)


def recommendation_result(args: argparse.Namespace) -> dict[str, Any]:
    request = args.request
    if args.action == "model":
        request = f"Compare and select current AI models for: {request}"
    elif args.action == "tool":
        request = f"Find software integrations, APIs, plugins, MCP connectors, and skills for: {request}"
    result = recommend_skills.build_recommendation(request, discovery_records(args), args.limit)
    if args.action == "model" and not any(
        item["type"] == "model" for item in result["external_research_targets"]
    ):
        result["external_research_targets"].append(
            {
                "type": "model",
                "subject": f"current AI models for {args.request}",
                "reason": "Compare current quality, benchmarks, licensing, cost, latency, controllability, API availability, and deployment constraints.",
                "queries": [
                    f"best current AI models for {args.request} benchmark comparison",
                    f"{args.request} AI model leaderboard license API pricing",
                ],
            }
        )
    return result


def filter_recommendation(result: dict[str, Any], action: str) -> dict[str, Any]:
    result = {key: value for key, value in result.items() if key != "orchestration"}
    result["recommendation_type"] = action
    if action == "model":
        result["external_research_targets"] = [
            item for item in result["external_research_targets"] if item["type"] == "model"
        ]
    elif action == "tool":
        result["external_research_targets"] = [
            item for item in result["external_research_targets"] if item["type"] == "software-integration"
        ]
    return result


def handle_recommend(args: argparse.Namespace) -> None:
    result = filter_recommendation(recommendation_result(args), args.action)
    if args.format == "json":
        json_print(result)
    else:
        recommend_skills.emit_markdown(result, False)


def validate_orchestration(result: dict[str, Any]) -> dict[str, Any]:
    phases = result["orchestration"]
    skills = [item["skill"] for phase in phases for item in phase["skills"]]
    primary_count = sum(
        item["role"] == "primary" for phase in phases for item in phase["skills"]
    )
    issues = []
    if not phases:
        issues.append("No executable local skill chain was assembled.")
    if len(skills) != len(set(skills)):
        issues.append("The same skill appears more than once in the execution chain.")
    if not primary_count:
        issues.append("No primary design or production skill was selected.")
    if result["external_search_gaps"]:
        issues.append("One or more required capabilities still need external discovery.")
    return {
        "valid": not issues,
        "issues": issues,
        "phases": phases,
        "external_gaps": result["external_search_gaps"],
    }


def emit_validation_markdown(validation: dict[str, Any]) -> None:
    print("# Skill Atlas Orchestration Validation")
    print()
    print(f"- valid: {str(validation['valid']).lower()}")
    print(f"- phases: {len(validation['phases'])}")
    print(f"- external gaps: {len(validation['external_gaps'])}")
    print()
    for issue in validation["issues"]:
        print(f"- {issue}")


def handle_orchestrate(args: argparse.Namespace) -> None:
    result = recommendation_result(args)
    if args.action == "validate":
        validation = validate_orchestration(result)
        json_print(validation) if args.format == "json" else emit_validation_markdown(validation)
        return
    if args.action == "run":
        result["execution"] = {
            "status": "awaiting-explicit-confirmation",
            "automatic_execution": False,
            "next_step": "Review the ordered plan, external gaps, permissions, and side effects before approving execution.",
        }
    if args.format == "json":
        json_print(result)
    else:
        recommend_skills.emit_markdown(result, True)
        if args.action == "run":
            print("## Execution Gate")
            print()
            print("- status: awaiting explicit confirmation")
            print("- no skill, model, tool, or external action has been executed")


def normalize_legacy_args(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    command = argv[0]
    actions = {
        "manage": MANAGE_ACTIONS,
        "discover": DISCOVER_ACTIONS,
        "recommend": RECOMMEND_ACTIONS,
        "orchestrate": ORCHESTRATE_ACTIONS,
        "monitor": MONITOR_ACTIONS,
    }.get(command)
    if not actions or len(argv) > 1 and argv[1] in actions | {"-h", "--help"}:
        return argv
    defaults = {"manage": "scan", "discover": "similar", "recommend": "task", "orchestrate": "plan", "monitor": "list"}
    return [command, defaults[command], *argv[1:]]


def add_manage_commands(subparsers: argparse._SubParsersAction) -> None:
    manage = subparsers.add_parser("manage", help="Inventory, update-plan, deduplicate, and sync skills.")
    actions = manage.add_subparsers(dest="action", required=True)
    for name, help_text in [
        ("scan", "Inventory all configured skill roots."),
        ("status", "Check sources and upstream freshness."),
        ("update", "Generate a reviewed update plan without applying it."),
        ("dedupe", "Generate a duplicate and consolidation plan."),
        ("sync", "Generate a cross-platform canonical-directory and symlink plan."),
    ]:
        action = actions.add_parser(name, help=help_text)
        add_roots(action)
        add_output(action, ["markdown", "json", "tsv"] if name in {"scan", "status"} else ["markdown", "json"])
        action.add_argument("--check-upstream", action="store_true")
        action.set_defaults(handler=handle_manage)
    self_parser = actions.add_parser("self", help="Check, update, or roll back Skill Atlas itself.")
    self_actions = self_parser.add_subparsers(dest="self_action", required=True)
    for name, help_text in [
        ("status", "Inspect the installed version or a reviewed release candidate."),
        ("update", "Plan an update, or apply it with explicit confirmation."),
        ("rollback", "List backups, or restore one with explicit confirmation."),
    ]:
        action = self_actions.add_parser(name, help=help_text)
        action.set_defaults(action=name, handler=handle_manage_self)
        action.add_argument(
            "--install-root",
            default=str(Path(__file__).resolve().parent.parent),
            help="Skill Atlas installation to inspect or update.",
        )
        action.add_argument("--source", help="Reviewed local release directory or archive.")
        action.add_argument("--checksum", help="Expected SHA-256; required for archives.")
        action.add_argument("--backup", help="Backup path or name to restore.")
        action.add_argument("--apply", action="store_true")
        action.add_argument("--confirm", action="store_true")
        add_output(action, ["markdown", "json"])


def add_discover_commands(subparsers: argparse._SubParsersAction) -> None:
    discover = subparsers.add_parser("discover", help="Find similar skills, competitors, alternatives, and gaps.")
    actions = discover.add_subparsers(dest="action", required=True)
    for name, help_text in [
        ("similar", "Find similar public skills."),
        ("competitors", "Find competitors for a user-authored skill without replacing it."),
        ("alternatives", "Find replacement or complementary candidates."),
        ("gaps", "Find missing capabilities for a task or product."),
    ]:
        action = actions.add_parser(name, help=help_text)
        action.add_argument("query", help="Skill name, category, product, or task.")
        add_roots(action)
        add_output(action, ["markdown", "json"])
        action.add_argument("--limit", type=int, default=20)
        action.set_defaults(handler=handle_discover)


def add_install_command(subparsers: argparse._SubParsersAction) -> None:
    install = subparsers.add_parser(
        "install", help="Install Skill Atlas and optional platform command adapters."
    )
    selection = install.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all-platforms", action="store_true")
    selection.add_argument(
        "--platform", action="append", choices=install_skill_atlas.PLATFORMS, default=[]
    )
    install.add_argument("--commands", action="store_true", help="Register slash commands where supported.")
    install.add_argument("--source", help="Skill Atlas package root; defaults to this package.")
    install.add_argument("--home", default=str(Path.home()), help="Target user home directory.")
    install.add_argument("--apply", action="store_true")
    install.add_argument("--confirm", action="store_true")
    add_output(install, ["markdown", "json"])
    install.set_defaults(handler=handle_install)


def add_recommend_commands(subparsers: argparse._SubParsersAction) -> None:
    recommend = subparsers.add_parser("recommend", help="Recommend skills for products, tasks, models, or tools.")
    actions = recommend.add_subparsers(dest="action", required=True)
    for name, help_text in [
        ("product", "Recommend a skill stack for a product."),
        ("task", "Recommend a skill stack for a concrete task."),
        ("model", "Recommend evaluation skills and current model research."),
        ("tool", "Recommend skills and software integration research."),
    ]:
        action = actions.add_parser(name, help=help_text)
        action.add_argument("request")
        add_roots(action)
        add_output(action, ["markdown", "json"])
        action.add_argument("--limit", type=int, default=2)
        action.set_defaults(handler=handle_recommend)


def add_orchestrate_commands(subparsers: argparse._SubParsersAction) -> None:
    orchestrate = subparsers.add_parser("orchestrate", help="Plan, validate, or stage a multi-skill workflow.")
    actions = orchestrate.add_subparsers(dest="action", required=True)
    for name, help_text in [
        ("plan", "Build an ordered multi-skill workflow."),
        ("validate", "Check roles, duplication, and capability gaps."),
        ("run", "Stage a run plan and wait for explicit confirmation."),
    ]:
        action = actions.add_parser(name, help=help_text)
        action.add_argument("request")
        add_roots(action)
        add_output(action, ["markdown", "json"])
        action.add_argument("--limit", type=int, default=2)
        action.set_defaults(handler=handle_orchestrate)


def add_monitor_commands(subparsers: argparse._SubParsersAction) -> None:
    monitor = subparsers.add_parser("monitor", help="Schedule and track recurring competitor comparisons.")
    actions = monitor.add_subparsers(dest="action", required=True)
    default_state = str(Path.home() / ".local/share/skill-atlas")

    add = actions.add_parser("add", help="Create a recurring competitor monitor.")
    add.add_argument("name", help="Stable monitor name.")
    add.add_argument("query", nargs="?", help="Comparison focus; defaults to the monitor name.")
    add.add_argument("--interval", choices=competitor_monitor.INTERVALS, default="monthly")
    add.add_argument("--state-dir", default=default_state)
    add_output(add, ["markdown", "json"])
    add.set_defaults(handler=handle_monitor)

    for name, help_text in [
        ("list", "List configured monitors."),
        ("due", "List monitors whose next comparison is due."),
    ]:
        action = actions.add_parser(name, help=help_text)
        action.add_argument("--state-dir", default=default_state)
        add_output(action, ["markdown", "json"])
        action.set_defaults(handler=handle_monitor)

    for name, help_text in [
        ("status", "Show schedule and snapshot status for one monitor."),
        ("history", "Show saved comparison snapshots."),
        ("remove", "Remove a monitor configuration while retaining snapshots."),
    ]:
        action = actions.add_parser(name, help=help_text)
        action.add_argument("monitor_id")
        action.add_argument("--state-dir", default=default_state)
        if name == "remove":
            action.add_argument("--confirm", action="store_true")
        add_output(action, ["markdown", "json"])
        action.set_defaults(handler=handle_monitor)

    run = actions.add_parser("run", help="Create a research packet or record completed comparison results.")
    run.add_argument("monitor_id")
    run.add_argument("--results", help="Agent-produced JSON containing summary and candidates.")
    run.add_argument("--state-dir", default=default_state)
    add_roots(run)
    run.add_argument("--limit", type=int, default=20)
    add_output(run, ["markdown", "json"])
    run.set_defaults(handler=handle_monitor)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage, discover, recommend, orchestrate, and monitor agent skills.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_manage_commands(subparsers)
    add_install_command(subparsers)
    add_discover_commands(subparsers)
    add_recommend_commands(subparsers)
    add_orchestrate_commands(subparsers)
    add_monitor_commands(subparsers)
    return parser.parse_args(normalize_legacy_args(list(sys.argv[1:] if argv is None else argv)))


def main() -> None:
    args = parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
