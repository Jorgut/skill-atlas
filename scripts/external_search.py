#!/usr/bin/env python3
"""Bounded public-source discovery. Search evidence is never installation approval."""
from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPException
import ipaddress
import json
import os
import re
import socket
import sys
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROVIDERS = ("github", "github-code", "official-skills", "mcp", "web")
DEFAULT_PROVIDERS = ("github", "official-skills", "mcp")
KINDS = ("all", "skill", "mcp-server", "ai-tool", "software-tool", "model", "unknown")
OFFICIAL_SKILLS = ("openai/skills", "anthropics/skills")
MAX_BYTES = 4 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def text(value: Any, limit: int = 800) -> str:
    """Do not render control/terminal sequences from untrusted metadata."""
    return "".join(c for c in str(value or "") if c.isprintable())[:limit]


def public_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 4096 or any(not c.isprintable() or c.isspace() for c in value):
        return None
    try:
        p = urlsplit(value)
        host = (p.hostname or "").lower()
        if p.scheme != "https" or not host or p.username or p.password or p.port not in (None, 443):
            return None
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            if "." not in host:
                return None
        params = parse_qsl(p.query, keep_blank_values=True)
        if any(key.lower() in {"token", "access_token", "api_key", "apikey", "password", "authorization", "signature"} for key, _ in params):
            return None
        params = [(key, val) for key, val in params if not key.lower().startswith("utm_") and key.lower() not in {"gclid", "fbclid", "msclkid"}]
        host = f"[{host}]" if ":" in host else host
        return urlunsplit(("https", host, p.path, urlencode(params), p.fragment))
    except ValueError:
        return None


def canonical(value: str) -> str:
    p = urlsplit(value)
    path = p.path
    if p.hostname == "github.com":
        path = path.rstrip("/")
        parts = path.split("/")
        if len(parts) > 2:
            parts[1] = parts[1].lower()
            parts[2] = parts[2].removesuffix(".git").lower()
        path = "/".join(parts)
    return urlunsplit(("https", p.netloc.lower(), path, p.query, p.fragment))


class SearchError(Exception):
    def __init__(self, status: str, http_status: int | None = None, retry_after: str | None = None):
        self.status, self.http_status, self.retry_after = status, http_status, retry_after
        super().__init__(status)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicClient:
    """Only fixed public GET endpoints. Never follow publisher URLs or redirects."""
    def __init__(self, timeout: float = 8, retries: int = 1, token: str | None = None, web_key: str | None = None):
        self.timeout, self.retries, self.token = timeout, retries, token
        self.web_key = web_key
        self.opener = build_opener(NoRedirect())

    def get(self, url: str) -> Any:
        p = urlsplit(url)
        allowed = (
            p.hostname == "api.github.com" and (
                p.path in {"/search/repositories", "/search/code"}
                or bool(re.fullmatch(r"/repos/(openai/skills|anthropics/skills)/git/trees/main", p.path))
            )
        ) or (p.hostname == "registry.modelcontextprotocol.io" and p.path == "/v0.1/servers") or (p.hostname == "api.search.brave.com" and p.path == "/res/v1/web/search")
        if not allowed or p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
            raise SearchError("blocked-endpoint")
        headers = {"Accept": "application/json", "User-Agent": "SkillAtlas-public-search/1"}
        if p.hostname == "api.github.com":
            headers["Accept"] = "application/vnd.github+json"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
        if p.hostname == "api.search.brave.com" and self.web_key:
            headers["X-Subscription-Token"] = self.web_key
        for attempt in range(self.retries + 1):
            try:
                deadline = time.monotonic() + self.timeout
                with self.opener.open(Request(url, headers=headers, method="GET"), timeout=self.timeout) as response:
                    chunks, length = [], 0
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise SearchError("timeout")
                        # urllib's HTTPResponse exposes its socket through the buffered file.
                        # read1 performs at most one underlying read; shrink its timeout to
                        # the remaining budget so slow response bodies cannot extend it.
                        sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                        if sock is not None:
                            sock.settimeout(remaining)
                        reader = getattr(response, "read1", response.read)
                        chunk = reader(min(65536, MAX_BYTES - length + 1))
                        if time.monotonic() > deadline:
                            raise SearchError("timeout")
                        if not chunk:
                            unread = getattr(response, "length", None)
                            if isinstance(unread, int) and unread > 0:
                                raise SearchError("truncated-response")
                            break
                        length += len(chunk)
                        if length > MAX_BYTES:
                            raise SearchError("response-too-large")
                        chunks.append(chunk)
                    return json.loads(b"".join(chunks).decode("utf-8"))
            except HTTPError as exc:
                if exc.code in {502, 503, 504} and attempt < self.retries:
                    exc.close()
                    time.sleep(0.2)
                    continue
                remaining = exc.headers.get("X-RateLimit-Remaining")
                status = "http-error"
                if exc.code == 429 or (exc.code == 403 and (remaining == "0" or exc.headers.get("Retry-After"))):
                    status = "rate-limited"
                elif exc.code == 401:
                    status = "authentication-required"
                elif exc.code == 403:
                    status = "permission-denied"
                elif 300 <= exc.code < 400:
                    status = "redirect-blocked"
                # Never echo response bodies, tokens, or arbitrary exception strings.
                failure = SearchError(status, exc.code, text(exc.headers.get("Retry-After"), 80) or None)
                exc.close()
                raise failure from None
            except (TimeoutError, socket.timeout):
                raise SearchError("timeout") from None
            except (URLError, OSError, HTTPException):
                raise SearchError("network-error") from None
            except (json.JSONDecodeError, UnicodeError):
                raise SearchError("invalid-response") from None


def terms(query: str) -> list[str]:
    ignored = {"the", "and", "for", "with", "find", "search", "best", "current", "please", "tools", "tool", "skills", "skill"}
    return list(dict.fromkeys(t.lower() for t in re.findall(r"[\w-]+", query) if len(t) > 1 and t.lower() not in ignored))[:12]


def github_query(query: str) -> str:
    # Use literal terms only: untrusted search qualifiers cannot widen auth scope.
    return " ".join(re.findall(r"[\w-]+", query)[:16])[:180]


def infer_kind(name: str, description: str, topics: list[str]) -> str:
    value = " ".join([name, description, *topics]).lower()
    if any(x in value for x in ["skill.md", "agent-skill", "agent skill", "claude skill", "codex skill"]):
        return "skill"
    if re.search(r"\bmcp\b|model context protocol", value):
        return "mcp-server"
    if any(x in value for x in ["language model", "model weights", "model checkpoint"]):
        return "model"
    if any(x in value for x in ["artificial-intelligence", " ai ", "llm", "generative-ai"]):
        return "ai-tool"
    return "software-tool"


def candidate(name: str, url: str, kind: str, description: str, provider: str, request_url: str,
              retrieved_at: str, **metadata) -> dict[str, Any] | None:
    safe = public_url(url)
    if not safe:
        return None
    item = {
        "name": text(name, 200), "url": safe, "artifact_type": kind,
        "description": text(description), "source": provider, "retrieved_at": retrieved_at,
        "classification_basis": "metadata-inferred", "availability": "not-verified",
        "review_status": "review-required", "installable": False,
        "risk_review": {
            "status": "metadata-only", "code_audited": False,
            "required_checks": ["publisher identity", "license", "maintenance", "task compatibility",
                                "source/content security review", "permissions, credentials and data access",
                                "explicit approval before installation or execution"],
        },
        "provenance": [{"provider": provider, "request_url": request_url, "retrieved_at": retrieved_at}],
    }
    item.update(metadata)
    checks = item["risk_review"]["required_checks"]
    if kind == "skill":
        checks.append("instructions, scripts, dependencies and prompt injection")
    elif kind == "mcp-server":
        checks.append("package/remote identity and exposed tool capabilities")
    elif kind in {"ai-tool", "software-tool", "unknown"}:
        checks.append("vendor identity, data handling, account costs and integration permissions")
    elif kind == "model":
        checks.append("model card, weights provenance, usage license and deployment requirements")
    item["risk_review"]["flags"] = ["content-not-reviewed", "permissions-not-reviewed"]
    if not item.get("license") or item["license"] == "NOASSERTION":
        item["risk_review"]["flags"].append("license-unverified")
    if item.get("archived"):
        item["risk_review"]["flags"].append("repository-archived")
    return item


def run_search(query: str, providers=DEFAULT_PROVIDERS, limit: int = 10, pages: int = 1,
               timeout: float = 8, retries: int = 1, kind: str = "all",
               token_env: str = "GITHUB_TOKEN", web_key_env: str = "BRAVE_SEARCH_API_KEY", client=None) -> dict[str, Any]:
    if not query.strip() or len(query) > 500:
        raise ValueError("Search query must contain 1–500 characters.")
    if not 1 <= limit <= 50 or not 1 <= pages <= 3 or not 0 < timeout <= 30 or retries not in (0, 1):
        raise ValueError("Search limits: results 1–50, pages 1–3, timeout >0–30 seconds, retries 0–1.")
    if kind not in KINDS or not providers or any(p not in PROVIDERS for p in providers):
        raise ValueError("Unsupported artifact kind or search provider.")
    if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in (token_env, web_key_env)):
        raise ValueError("Token environment variable must be a variable name, not a token.")
    started = now()
    client = client or PublicClient(timeout, retries, os.environ.get(token_env), os.environ.get(web_key_env))
    candidates: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    query_terms = terms(query)

    def request(provider: str, url: str, parse):
        at = now()
        record = {"provider": provider, "request_url": url, "started_at": at,
                  "executed": True, "status": "pending", "result_count": 0}
        sources.append(record)
        try:
            data = client.get(url)
            items, truncated, cursor = parse(data, url, at)
            candidates.extend(x for x in items if x)
            record.update(status="partial" if truncated else "completed", result_count=sum(x is not None for x in items),
                          truncated=bool(truncated), next_cursor=text(cursor, 500) if cursor else None)
            return data
        except SearchError as exc:
            record.update(status=exc.status, http_status=exc.http_status, retry_after=exc.retry_after)
        except (KeyError, TypeError, ValueError, AttributeError):
            record.update(status="invalid-response")
        finally:
            record["completed_at"] = now()
        return None

    for provider in dict.fromkeys(providers):
        if provider in {"github", "github-code"}:
            endpoint = "code" if provider == "github-code" else "repositories"
            q = github_query(query)
            if not q:
                sources.append({"provider": provider, "executed": False, "status": "invalid-query", "result_count": 0})
                continue
            q += " is:public"
            q += " filename:SKILL.md" if endpoint == "code" else " in:name,description,readme"
            for page in range(1, pages + 1):
                url = f"https://api.github.com/search/{endpoint}?" + urlencode({"q": q, "per_page": limit, "page": page})

                def parse_github(data, request_url, at):
                    items = data["items"]
                    if not isinstance(items, list) or not isinstance(data["total_count"], int):
                        raise ValueError()
                    output = []
                    for row in items:
                        if not isinstance(row, dict):
                            raise ValueError()
                        repo = row.get("repository", row)
                        if repo.get("private") is True:
                            continue
                        name = repo.get("full_name", row.get("name", ""))
                        desc = repo.get("description") or ""
                        result_kind = "skill" if endpoint == "code" else infer_kind(name, desc, repo.get("topics") or [])
                        license_info = repo.get("license") or {}
                        c = candidate(name + (":" + row.get("path", "") if endpoint == "code" else ""),
                                      row["html_url"], result_kind, desc, provider, request_url, at,
                                      repository_url=public_url(repo.get("html_url")),
                                      license=text(license_info.get("spdx_id"), 80) or None,
                                      upstream_updated_at=text(repo.get("pushed_at"), 80) or None,
                                      homepage=public_url(repo.get("homepage")),
                                      archived=bool(repo.get("archived", False)))
                        if c and endpoint == "code":
                            c["classification_basis"] = "SKILL.md filename; content not audited"
                        output.append(c)
                    more = data["total_count"] > page * limit
                    return output, bool(data.get("incomplete_results")) or (more and page == pages), str(page + 1) if more else None

                data = request(provider, url, parse_github)
                if data is None or len(data.get("items", [])) < limit or page * limit >= data.get("total_count", 0):
                    break
        elif provider == "official-skills":
            for repo in OFFICIAL_SKILLS:
                url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"

                def parse_skills(data, request_url, at):
                    rows = data["tree"]
                    if not isinstance(rows, list):
                        raise ValueError()
                    matches = [row for row in rows if row.get("type") == "blob"
                               and row.get("path", "").endswith("/SKILL.md")
                               and (not query_terms or any(term in row["path"].lower() for term in query_terms))]
                    output = [candidate(row["path"].removesuffix("/SKILL.md"),
                                        f"https://github.com/{repo}/blob/main/{quote(row['path'])}", "skill",
                                        "Official publisher repository path match; skill content not fetched.",
                                        provider, request_url, at, repository_url=f"https://github.com/{repo}",
                                        revision=text(row.get("sha"), 80), classification_basis="official repository SKILL.md path")
                              for row in matches[:limit]]
                    return output, bool(data.get("truncated")) or len(matches) > limit, None

                request(provider, url, parse_skills)
        elif provider == "mcp":
            if len(query.strip()) < 3:
                sources.append({"provider": provider, "executed": False, "status": "invalid-query", "result_count": 0})
                continue
            cursor = None
            for page in range(pages):
                params = {"search": query, "limit": limit, "version": "latest"}
                if cursor:
                    params["cursor"] = cursor
                url = "https://registry.modelcontextprotocol.io/v0.1/servers?" + urlencode(params)

                def parse_mcp(data, request_url, at):
                    rows = data["servers"]
                    if not isinstance(rows, list):
                        raise ValueError()
                    output = []
                    for row in rows:
                        server = row["server"]
                        name = server["name"]
                        repo = public_url((server.get("repository") or {}).get("url"))
                        url = repo or "https://registry.modelcontextprotocol.io/v0.1/servers/" + quote(name, safe="") + "/versions/latest"
                        c = candidate(name, url, "mcp-server", server.get("description", ""), provider,
                                      request_url, at, classification_basis="MCP Registry publisher metadata",
                                      version=text(server.get("version"), 100), repository_url=repo,
                                      registry_name=text(name, 200))
                        if c:
                            c["identity"] = "mcp:" + name.lower()
                            c["risk_review"]["declared_packages"] = len(server.get("packages") or [])
                            c["risk_review"]["declared_remotes"] = len(server.get("remotes") or [])
                        output.append(c)
                    next_cursor = (data.get("metadata") or {}).get("nextCursor")
                    return output, bool(next_cursor) and page == pages - 1, next_cursor

                data = request(provider, url, parse_mcp)
                if not data:
                    break
                cursor = (data.get("metadata") or {}).get("nextCursor")
                if not cursor:
                    break

        elif provider == "web":
            if not os.environ.get(web_key_env):
                sources.append({"provider": provider, "executed": False, "status": "configuration-required",
                                "reason": "Set the named Brave Search API key environment variable.", "result_count": 0})
                continue
            for page in range(pages):
                url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": min(limit, 20), "offset": page})

                def parse_web(data, request_url, at):
                    rows = (data.get("web") or {}).get("results", [])
                    if not isinstance(rows, list) or not isinstance(data.get("query"), dict):
                        raise ValueError()
                    output = []
                    for row in rows:
                        inferred = infer_kind(row["title"], row.get("description", ""), [])
                        output.append(candidate(row["title"], row["url"],
                                                inferred if inferred != "software-tool" else "unknown",
                                                row.get("description", ""), provider, request_url, at,
                                                classification_basis="unverified web metadata inference; inspect artifact before adoption"))
                    more = bool(data["query"].get("more_results_available"))
                    return output, more and page == pages - 1, str(page + 1) if more else None

                data = request(provider, url, parse_web)
                if not data or not (data.get("query") or {}).get("more_results_available"):
                    break

    unique: dict[str, dict[str, Any]] = {}
    evidence_priority = {"official-skills": 4, "mcp": 4, "github-code": 3, "github": 2, "web": 1}
    for c in candidates:
        key = c.get("identity") or canonical(c["url"])
        if key not in unique:
            unique[key] = c
            continue
        previous = unique[key]
        # Choose the stronger artifact evidence independently of provider order.
        strength = lambda item: (evidence_priority[item["source"]], item["name"], item["url"])
        primary, secondary = sorted((previous, c), key=strength, reverse=True)
        provenance = previous["provenance"] + c["provenance"]
        for field, value in secondary.items():
            if field not in primary or primary[field] in (None, ""):
                primary[field] = value
        primary["provenance"] = provenance
        unique[key] = primary
    duplicate_count = len(candidates) - len(unique)
    for key, c in list(unique.items()):
        if kind != "all" and c["artifact_type"] != kind:
            del unique[key]
            continue
        c["id"] = hashlib.sha256(key.encode()).hexdigest()[:20]
        haystack = (c["name"] + " " + c["description"]).lower()
        matched = [t for t in query_terms if t in haystack]
        relevance = round(60 * len(matched) / max(1, len(query_terms)))
        evidence = 20 if provider_is_registry(c) else 10
        metadata_score = (10 if c.get("license") and c["license"] != "NOASSERTION" else 0) + (10 if c.get("upstream_updated_at") or c.get("revision") or c.get("version") else 0)
        c["score"] = {"value": relevance + evidence + metadata_score, "out_of": 100,
                      "kind": "discovery-priority-only", "relevance": relevance,
                      "source_evidence": evidence, "metadata_completeness": metadata_score,
                      "matched_terms": matched, "not_a_security_or_quality_verdict": True}
    attempted = [s for s in sources if s["executed"]]
    successful = [s for s in attempted if s["status"] in {"completed", "partial"}]
    status = "failed" if not successful else "completed" if len(successful) == len(sources) and all(s["status"] == "completed" for s in sources) else "partial"
    if status == "completed" and not unique:
        status = "completed-empty"
    return {
        "schema_version": 1, "status": status, "query": query, "started_at": started, "completed_at": now(),
        "network_attempted": bool(attempted), "sources": sources,
        "candidates": sorted(unique.values(), key=lambda x: (-x["score"]["value"], x["id"]))[:limit],
        "unique_candidates_before_limit": len(unique), "duplicates_removed": duplicate_count,
        "review_status": "review-required", "market_cache_updated": False,
        "coverage": "Bounded public APIs, not an exhaustive web crawl. Official Skills use path matching; GitHub results use metadata; Optional web provider searches the Brave index; website classifications are metadata inferences until reviewed. Publisher pages are links, not fetched pages. MCP Registry performs name substring search.",
        "query_policy": "Only the explicit query is sent. No local files, inventory, paths or transcripts are transmitted. Queries are not translated automatically.",
    }


def provider_is_registry(c):
    return c["source"] in {"official-skills", "mcp"}


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--search-mode", choices=("local", "web", "hybrid"), default="local",
                        help="Source scope; local preserves offline compatibility. web/hybrid perform public API requests.")
    parser.add_argument("--provider", action="append", choices=PROVIDERS, default=[], help="External provider; repeat to select sources.")
    parser.add_argument("--artifact-type", choices=KINDS, default="all")
    parser.add_argument("--web-limit", type=int, default=10, help="Maximum external candidates (1–50).")
    parser.add_argument("--search-pages", type=int, default=1, help="Maximum pages per paginated provider (1–3).")
    parser.add_argument("--search-timeout", type=float, default=8, help="Socket timeout and response-body budget, at most 30 seconds.")
    parser.add_argument("--search-retries", type=int, choices=(0, 1), default=1)
    parser.add_argument("--web-key-env", default="BRAVE_SEARCH_API_KEY", help="Optional Brave Search API key environment variable name (provider web).")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN", help="Optional token environment variable name; never read credential files.")


def from_args(args, query):
    try:
        return run_search(query, providers=args.provider or DEFAULT_PROVIDERS, limit=args.web_limit,
                          pages=args.search_pages, timeout=args.search_timeout, retries=args.search_retries,
                          kind=args.artifact_type, token_env=args.github_token_env, web_key_env=args.web_key_env)
    except ValueError as exc:
        print(f"External search refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


def emit_markdown(result: dict[str, Any]) -> None:
    print("\n## Executed External Search\n")
    print(f"- status: {result['status']}; at: {result['completed_at']}")
    print(f"- query: {text(result['query'])}")
    print(f"- coverage: {result['coverage']}")
    for source in result["sources"]:
        print(f"- {source['provider']}: {source['status']}; candidates: {source['result_count']}; request: {source.get('request_url', 'not sent')}")
        if source.get("retry_after"):
            print(f"  - Retry-After: {source['retry_after']} (not automatically waited)")
    for c in result["candidates"]:
        print(f"- {c['name']} [{c['artifact_type']}; priority {c['score']['value']}/100; review-required]")
        print(f"  - source: {c['url']} (retrieved {c['retrieved_at']})")
        if c.get("homepage"):
            print(f"  - publisher homepage (not fetched/verified): {c['homepage']}")
        print(f"  - {c['description']}")
    print("- No candidate installed, executed, content-audited, or promoted to reviewed market cache.")
