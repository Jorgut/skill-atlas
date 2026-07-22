#!/usr/bin/env python3
"""Static security review for local or candidate skills."""

from __future__ import annotations

import argparse
import json
import os
import re
from urllib.parse import urlparse
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


HOME = Path.home()
TEXT_EXTENSIONS = {
    ".md",
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
}
EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str
    pattern: str
    reason: str
    executable_only: bool = False


@dataclass
class Finding:
    rule_id: str
    severity: str
    file: str
    line: int
    excerpt: str
    reason: str
    context: str
    confidence: str


TRUSTED_URL_HOSTS = {
    "api.skillmd.com",
    "clawhub.ai",
    "cli.github.com",
    "github.com",
    "img.shields.io",
    "npmjs.com",
    "playwright.dev",
    "playbooks.com",
    "pypi.org",
    "raw.githubusercontent.com",
    "skills.sh",
    "skillsmp.com",
}
RESOURCE_URL_HOSTS = {
    "cdn.jsdelivr.net",
    "unpkg.com",
}
EXECUTABLE_EXTENSIONS = {".py", ".sh", ".bash", ".zsh", ".js", ".ts", ".tsx", ".jsx"}
CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml"}
URL_RE = re.compile(r"https?://[^\s)>\"']+")


RULES = [
    Rule("secret-path", "unsafe", r"(~|/Users/[^/\s]+)/(?:\.ssh|\.gnupg|\.aws|\.config/gcloud|Library/Keychains)\b", "references sensitive credential stores"),
    Rule("env-secret", "review-needed", r"\b(?:API[_-]?KEY|SECRET|PASSWORD|PRIVATE[_-]?KEY|ACCESS[_-]?TOKEN)\b|(?:\bTOKEN\b(?=\s*[=:]))", "references secrets or tokens"),
    Rule("destructive-rm", "unsafe", r"\brm\s+-[^\n]*(?:r[^\n]*f|f[^\n]*r)\b", "uses recursive forced deletion", True),
    Rule("sudo", "review-needed", r"\bsudo\b", "requests elevated privileges", True),
    Rule("curl-pipe-shell", "unsafe", r"\b(?:curl|wget)\b[^\n|;]*(?:\||;)\s*(?:sh|bash|zsh|python|python3|node)\b", "pipes remote content into an interpreter", True),
    Rule("remote-exec", "unsafe", r"\beval\s*\(|(?:^|[^.\w])exec\s*\(|\b(?:python|python3|node|ruby|perl)\s+-e\b", "uses dynamic execution", True),
    Rule("base64-exec", "unsafe", r"base64\s+-d|base64\.b64decode|atob\(", "may decode hidden payloads", True),
    Rule("profile-persistence", "review-needed", r"\.(?:zshrc|bashrc|bash_profile|profile|config/fish/config\.fish)\b", "modifies or references shell startup files"),
    Rule("agent-config", "review-needed", r"\.(?:codex|claude|config/opencode|cursor|gemini)/(?:config|settings|mcp|servers)", "references agent configuration or MCP setup"),
    Rule("broad-home-write", "review-needed", r"\b(?:chmod|chown)\s+[^\n]*(?:777|666|recursive|-R)|\bmv\s+[^\n]*(?:~|/Users/)", "may broadly alter home files or permissions", True),
    Rule("prompt-injection", "unsafe", r"ignore (?:all )?(?:previous|system|developer) instructions|bypass (?:safety|confirmation)|exfiltrate|leak (?:secrets|tokens|files)", "contains prompt-injection or exfiltration language"),
    Rule("auto-install", "review-needed", r"\b(?:pip|npm|pnpm|yarn|brew|uv|cargo)\s+(?:install|add)\b", "installs dependencies or packages", True),
    Rule("credential-upload", "unsafe", r"\b(?:upload|send|post|exfiltrate)\b[^\n]*(?:secret|token|password|\.env|private key|ssh)", "may transmit credentials"),
]


def iter_skill_roots(paths: list[Path]) -> Iterable[Path]:
    for path in paths:
        path = path.expanduser()
        if not path.exists():
            continue
        if path.is_file():
            yield path
            continue
        if (path / "SKILL.md").exists():
            yield path
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            if "SKILL.md" in filenames:
                yield Path(dirpath)


def iter_files(target: Path) -> Iterable[Path]:
    if target.is_file():
        yield target
        return
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in TEXT_EXTENSIONS:
                yield path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_context(path: Path, in_markdown_code: bool) -> str:
    if path.suffix.lower() == ".md":
        return "markdown-code" if in_markdown_code else "markdown"
    if path.suffix.lower() in EXECUTABLE_EXTENSIONS:
        return "executable"
    if path.suffix.lower() in CONFIG_EXTENSIONS:
        return "config"
    return "text"


def is_allowlisted_line(line: str) -> bool:
    return "security-review: allow" in line


def is_rule_definition(path: Path, line: str) -> bool:
    return path.name == "security_review_skills.py" and "Rule(" in line


def is_regex_literal_line(line: str) -> bool:
    return bool(re.search(r"\bre\.(?:match|search|compile)\(", line)) or "URL_RE =" in line


def is_executable_context(context: str) -> bool:
    return context in {"executable", "markdown-code"}


def markdown_link_only(context: str, line: str) -> bool:
    if context != "markdown":
        return False
    return bool(URL_RE.search(line)) and not re.search(r"\b(?:curl|wget|import|script|source|fetch)\b", line, re.IGNORECASE)


def is_design_token_phrase(rule: Rule, line: str) -> bool:
    return rule.rule_id == "env-secret" and bool(re.search(r"\b(?:spacing|color|typography|radius|shadow)\s+token\b", line, re.IGNORECASE))  # security-review: allow documented rule exception


def downgrade_for_context(rule: Rule, context: str, line: str) -> tuple[str, str] | None:
    if rule.executable_only and not is_executable_context(context):
        return None
    if markdown_link_only(context, line) and rule.rule_id not in {"prompt-injection", "credential-upload"}:
        return None
    if is_design_token_phrase(rule, line):
        return None
    if context == "markdown" and rule.severity == "unsafe":
        if re.search(r"\b(?:looks for|detects|rule|review|example|examples|static|language that asks|asks agents)\b", line, re.IGNORECASE):
            return ("review-needed", "low")
    if context in {"markdown", "config", "text"} and rule.executable_only:
        return ("review-needed", "medium")
    return (rule.severity, "high" if is_executable_context(context) else "medium")


def url_finding(path: Path, line_no: int, line: str, context: str, strict: bool) -> Finding | None:
    if is_regex_literal_line(line):
        return None
    urls = URL_RE.findall(line)
    if not urls:
        return None
    unknown_hosts: list[str] = []
    resource_hosts: list[str] = []
    for url in urls:
        host = (urlparse(url).hostname or "").lower()
        if host in TRUSTED_URL_HOSTS:
            continue
        if host in RESOURCE_URL_HOSTS:
            resource_hosts.append(host)
            continue
        unknown_hosts.append(host or url)
    if unknown_hosts:
        if markdown_link_only(context, line) and not strict:
            return None
        return Finding(
            rule_id="unknown-network",
            severity="review-needed",
            file=str(path),
            line=line_no,
            excerpt=line[:240],
            reason=f"references external network host(s): {', '.join(sorted(set(unknown_hosts)))}",
            context=context,
            confidence="high" if is_executable_context(context) else "medium",
        )
    if resource_hosts and re.search(r"\b(?:import|script|source|fetch)\b|<script\b|<link\b", line, re.IGNORECASE):
        return Finding(
            rule_id="remote-resource",
            severity="review-needed",
            file=str(path),
            line=line_no,
            excerpt=line[:240],
            reason=f"loads remote resource host(s): {', '.join(sorted(set(resource_hosts)))}",
            context=context,
            confidence="medium",
        )
    return None


def review_target(target: Path, strict: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    for file_path in iter_files(target):
        try:
            lines = read_text(file_path).splitlines()
        except OSError:
            continue
        in_markdown_code = False
        for line_no, line in enumerate(lines, 1):
            compact = line.strip()
            if file_path.suffix.lower() == ".md" and compact.startswith("```"):
                in_markdown_code = not in_markdown_code
                continue
            if not compact:
                continue
            if is_allowlisted_line(compact) or is_rule_definition(file_path, compact):
                continue
            context = line_context(file_path, in_markdown_code)
            network_finding = url_finding(file_path, line_no, compact, context, strict)
            if network_finding:
                findings.append(network_finding)
            for rule in RULES:
                if re.search(rule.pattern, compact, re.IGNORECASE):
                    adjusted = downgrade_for_context(rule, context, compact)
                    if adjusted is None:
                        continue
                    severity, confidence = adjusted
                    findings.append(
                        Finding(
                            rule_id=rule.rule_id,
                            severity=severity,
                            file=str(file_path),
                            line=line_no,
                            excerpt=compact[:240],
                            reason=rule.reason,
                            context=context,
                            confidence=confidence,
                        )
                    )
    return findings


def verdict(findings: list[Finding]) -> str:
    severities = {finding.severity for finding in findings}
    if "unsafe" in severities:
        return "unsafe"
    if "review-needed" in severities:
        return "review-needed"
    return "safe"


def emit_json(results: list[dict]) -> None:
    print(json.dumps(results, ensure_ascii=False, indent=2))


def emit_markdown(results: list[dict]) -> None:
    counts = Counter(result["verdict"] for result in results)
    print("# Skill Security Review")
    print()
    print(f"- targets: {len(results)}")
    for key in ["unsafe", "review-needed", "safe"]:
        print(f"- {key}: {counts.get(key, 0)}")
    print()
    for result in results:
        if result["verdict"] == "safe":
            continue
        print(f"## {Path(result['target']).name} [{result['verdict']}]")
        print()
        print(f"- target: `{result['target']}`")
        for finding in result["findings"][:25]:
            print(f"- {finding['severity']} `{finding['rule_id']}` {finding['file']}:{finding['line']}")
            print(f"  - context: {finding['context']}; confidence: {finding['confidence']}")
            print(f"  - {finding['reason']}")
            print(f"  - `{finding['excerpt']}`")
        extra = len(result["findings"]) - 25
        if extra > 0:
            print(f"- ... {extra} more findings")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", default=[], help="Skill directory, SKILL.md file, or root to scan. May be repeated.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--strict", action="store_true", help="Report ordinary Markdown links to untrusted hosts instead of ignoring link-only prose.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = [Path(value) for value in args.path] or [HOME / ".codex" / "skills", HOME / ".agents" / "skills"]
    results = []
    for target in iter_skill_roots(paths):
        findings = review_target(target, strict=args.strict)
        results.append(
            {
                "target": str(target),
                "verdict": verdict(findings),
                "finding_count": len(findings),
                "findings": [asdict(finding) for finding in findings],
            }
        )
    if args.format == "json":
        emit_json(results)
    else:
        emit_markdown(results)


if __name__ == "__main__":
    main()
