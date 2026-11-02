#!/usr/bin/env python3
"""Opt-in Skill Atlas feedback reporting; no uploads without authorization."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import agent_handoff

REPO = "Jorgut/skill-atlas"
API = "https://api.github.com/repos/" + REPO
CATEGORIES = ("handoff", "skill-load", "model-advice", "ci-failure", "other")
REDACTIONS = [
    (r"(?i)(authorization:\s*bearer\s+)\S+", r"\1[REDACTED]"),
    (r"(?i)(gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{16,})", "[REDACTED-TOKEN]"),
    (r"(?i)\b((?:password|token|api[_-]?key|secret)\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]"),
    (r"(?i)([?&](?:token|api_key|access_token)=)[^&\s]+", r"\1[REDACTED]"),
    (r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED-EMAIL]"),
    (r"(?:(?:/Users|/home)/)[^\s\"'<>]+", "[REDACTED-PATH]"),
]

class FeedbackError(ValueError):
    pass

def clean(value: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FeedbackError("Nonempty text required")
    value = value.strip()[:limit]
    for expression, replacement in REDACTIONS:
        value = re.sub(expression, replacement, value)
    return value

def make_report(title: str, summary: str, category: str, source: str = "") -> dict:
    if category not in CATEGORIES:
        raise FeedbackError("Invalid feedback category")
    title, summary = clean(title, 110), clean(summary, 1200)
    source = clean(source, 80) if source else "not-provided"
    normalized = " ".join(re.findall(r"[a-z0-9]+", title.casefold()))
    marker = hashlib.sha256((category + "|" + normalized).encode()).hexdigest()[:32]
    return {"schema_version": 1, "repository": REPO, "category": category,
            "source": source, "fingerprint": marker,
            "title": f"[Skill Atlas/{category}] {title}",
            "body": "## Skill Atlas feedback\n\n"
                    f"Category: {category}\n\nSource project: {source}\n\n"
                    f"Observed behavior:\n\n{summary}\n\n"
                    "Reproduction evidence must be reviewed. No logs or files attached automatically.\n\n"
                    f"<!-- skill-atlas-fingerprint: {marker} -->\n"}

def validate(report: dict) -> dict:
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise FeedbackError("Invalid report schema")
    if report.get("repository") != REPO or report.get("category") not in CATEGORIES:
        raise FeedbackError("Only Skill Atlas reports are supported")
    prefix = f"[Skill Atlas/{report['category']}] "
    if not isinstance(report.get("title"), str) or not report["title"].startswith(prefix):
        raise FeedbackError("Invalid report title")
    title = report["title"][len(prefix):]
    if clean(title, 110) != title:
        raise FeedbackError("Report title is not sanitized")
    normalized = " ".join(re.findall(r"[a-z0-9]+", title.casefold()))
    marker = hashlib.sha256((report["category"] + "|" + normalized).encode()).hexdigest()[:32]
    body = report.get("body")
    if not isinstance(body, str) or len(body) > 3500 or not body.endswith(f"<!-- skill-atlas-fingerprint: {marker} -->\n"):
        raise FeedbackError("Invalid report body")
    if report.get("fingerprint") != marker or clean(body, 3500) != body.strip():
        raise FeedbackError("Report was modified or contains sensitive strings; regenerate it")
    if report.get("source") is None or clean(report["source"], 80) != report["source"]:
        raise FeedbackError("Invalid report source")
    return report

def github(method: str, endpoint: str, token: str, body: dict | None = None):
    if not endpoint.startswith(API + "/issues"):
        raise FeedbackError("Only the Skill Atlas Issues API is allowed")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "skill-atlas-feedback",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(endpoint, headers=headers, data=data, method=method), timeout=15) as response:
            return json.load(response)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise FeedbackError("GitHub request failed. No submission confirmed.") from exc

def duplicates(report: dict, token: str) -> dict | None:
    # Check both open and closed reports. Errors fail closed.
    for page in range(1, 6):
        url = API + "/issues?" + urlencode({"state": "all", "per_page": 100, "page": page})
        issues = github("GET", url, token)
        if not isinstance(issues, list):
            raise FeedbackError("Invalid GitHub Issue response")
        for issue in issues:
            if "pull_request" in issue:
                continue
            if report["fingerprint"] in (issue.get("body") or "") or (
                issue.get("title", "").startswith(f"[Skill Atlas/{report['category']}]")
                and SequenceMatcher(None, issue["title"].casefold(),
                                    report["title"].casefold()).ratio() > 0.92
            ):
                return {"status": "duplicate", "issue_url": issue.get("html_url")}
        if len(issues) < 100:
            return None
    raise FeedbackError("Issue history too large to deduplicate safely")

def submit(report: dict, confirm: bool = False, team_auto: bool = False) -> dict:
    report = validate(report)
    if confirm == team_auto:
        raise FeedbackError("Choose exactly one: --confirm or --team-auto")
    if team_auto and not (os.environ.get("SKILL_ATLAS_TEAM_AUTOREPORT") == "1"
                          and report["category"] == "ci-failure"
                          and report["source"] == "skill-atlas"):
        raise FeedbackError("Auto submission only allowed for approved Skill Atlas CI failures")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise FeedbackError("GitHub issue-write token unavailable; no report uploaded")
    duplicate = duplicates(report, token)
    if duplicate:
        return duplicate
    posted = github("POST", API + "/issues", token, {"title": report["title"], "body": report["body"]})
    if not isinstance(posted, dict) or not posted.get("html_url"):
        raise FeedbackError("Issue creation was not confirmed")
    return {"status": "created", "issue_url": posted["html_url"]}

def detect(project: str, task: str) -> dict:
    state = agent_handoff.inspect_checkpoint(argparse.Namespace(project=project, task=task))
    if state["status"] != "review-required":
        return {"status": "no-report", "checkpoint_status": state["status"], "report": None}
    fields = state.get("changed_fields", [])
    return {"status": "report-ready", "checkpoint_status": state["status"],
            "report": make_report(
                "Checkpoint Git evidence mismatch",
                "Resume requires review; changed evidence fields: " + ", ".join(fields)
                + ". Inspect the Git state locally before transfer.",
                "handoff", "withheld")}

def add_arguments(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="feedback_action", required=True)
    prepare = actions.add_parser("prepare", help="Create a local sanitized issue draft.")
    prepare.add_argument("--title", required=True)
    prepare.add_argument("--summary", required=True)
    prepare.add_argument("--category", choices=CATEGORIES, default="other")
    prepare.add_argument("--source-project", default="")
    prepare.add_argument("--output")
    prepare.add_argument("--format", choices=("markdown", "json"), default="json")
    prepare.set_defaults(feedback_handler=handle_prepare)
    inspect = actions.add_parser("detect", help="Read-only Git checkpoint mismatch detector.")
    inspect.add_argument("--project", default=".")
    inspect.add_argument("--task", required=True)
    inspect.add_argument("--format", choices=("markdown", "json"), default="json")
    inspect.set_defaults(feedback_handler=handle_detect)
    post = actions.add_parser("submit", help="Preview, or post after explicit permission.")
    post.add_argument("--file", required=True)
    post.add_argument("--confirm", action="store_true")
    post.add_argument("--team-auto", action="store_true")
    post.add_argument("--format", choices=("markdown", "json"), default="json")
    post.set_defaults(feedback_handler=handle_submit)

def handle_prepare(args):
    report = make_report(args.title, args.summary, args.category, args.source_project)
    if args.output:
        path = Path(args.output).expanduser()
        if path.exists():
            raise FeedbackError("Report exists; refusing overwrite")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return {"status": "draft", "uploaded": False, "report": report, "output_file": args.output}

def handle_detect(args):
    return detect(args.project, args.task)

def handle_submit(args):
    try:
        report = json.loads(Path(args.file).expanduser().read_text())
    except (OSError, ValueError) as exc:
        raise FeedbackError("Cannot read report file") from exc
    validate(report)
    if not args.confirm and not args.team_auto:
        return {"status": "preview", "uploaded": False, "report": report}
    return submit(report, confirm=args.confirm, team_auto=args.team_auto)

def run(args):
    return args.feedback_handler(args)
