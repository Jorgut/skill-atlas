from __future__ import annotations

import json
import sys
import unittest
from io import BytesIO, StringIO
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import Mock, patch
from contextlib import redirect_stdout, redirect_stderr
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import external_search as search


def repository(name="example/pdf-tool", **kwargs):
    return {"full_name": name, "html_url": f"https://github.com/{name}",
            "description": "PDF AI conversion tool", "private": False,
            "pushed_at": "2026-10-01T00:00:00Z", "license": {"spdx_id": "MIT"}, **kwargs}


def github(*rows, total=None, incomplete=False):
    return {"items": list(rows), "total_count": len(rows) if total is None else total, "incomplete_results": incomplete}


def registry(name="org.example/pdf", version="1.0", **kwargs):
    return {"server": {"name": name, "version": version, "description": "PDF MCP server", **kwargs}}


class FakeClient:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return value


class SearchTests(unittest.TestCase):
    def test_repository_search_is_real_literal_public_query_and_auditable(self):
        client = FakeClient(github(repository()))
        report = search.run_search("pdf repo:secret/private", providers=["github"], client=client)
        params = parse_qs(urlsplit(client.calls[0]).query)
        self.assertIn("is:public", params["q"][0])
        self.assertNotIn("repo:", params["q"][0])
        self.assertTrue(report["network_attempted"])
        item = report["candidates"][0]
        self.assertEqual(item["artifact_type"], "ai-tool")
        self.assertEqual(item["review_status"], "review-required")
        self.assertFalse(item["installable"])
        self.assertFalse(item["risk_review"]["code_audited"])
        self.assertEqual(item["provenance"][0]["request_url"], client.calls[0])
        self.assertTrue(report["started_at"].endswith("Z"))
        self.assertEqual(item["score"]["value"], sum(item["score"][k] for k in ("relevance", "source_evidence", "metadata_completeness")))

    def test_empty_success_is_not_network_failure(self):
        empty = search.run_search("pdf", ["github"], client=FakeClient(github()))
        failed = search.run_search("pdf", ["github"], client=FakeClient(search.SearchError("timeout")))
        self.assertEqual(empty["status"], "completed-empty")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["sources"][0]["status"], "timeout")
        self.assertEqual(empty["candidates"], failed["candidates"])

    def test_source_failure_preserves_successes(self):
        client = FakeClient(github(repository()), search.SearchError("rate-limited", 429, "60"))
        report = search.run_search("pdf", ["github", "mcp"], client=client)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(len(report["candidates"]), 1)
        self.assertEqual(report["sources"][1]["retry_after"], "60")
        self.assertEqual(report["sources"][1]["http_status"], 429)

    def test_github_private_rows_are_excluded(self):
        report = search.run_search("pdf", ["github"], client=FakeClient(github(repository(private=True))))
        self.assertFalse(report["candidates"])

    def test_github_code_search_and_auth_failure_are_honest(self):
        client = FakeClient(search.SearchError("authentication-required", 401))
        report = search.run_search("pdf", ["github-code"], client=client)
        self.assertIn("filename:SKILL.md", parse_qs(urlsplit(client.calls[0]).query)["q"][0])
        self.assertEqual(report["sources"][0]["status"], "authentication-required")
        client = FakeClient(github({"name": "SKILL.md", "path": "pdf/SKILL.md",
                                   "html_url": "https://github.com/example/skills/blob/main/pdf/SKILL.md",
                                   "repository": repository("example/skills")}))
        item = search.run_search("pdf", ["github-code"], client=client)["candidates"][0]
        self.assertEqual(item["artifact_type"], "skill")
        self.assertIn("not audited", item["classification_basis"])

    def test_pagination_bounded_and_incomplete_results_reported(self):
        client = FakeClient(github(repository(), total=3))
        report = search.run_search("pdf", ["github"], limit=1, client=client)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(report["status"], "partial")
        self.assertTrue(report["sources"][0]["truncated"])
        client = FakeClient(github(repository("a/pdf"), total=2), github(repository("b/pdf"), total=2))
        report = search.run_search("pdf", ["github"], limit=1, pages=2, client=client)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["unique_candidates_before_limit"], 2)
        self.assertEqual(len(report["candidates"]), 1)
        report = search.run_search("pdf", ["github"], client=FakeClient(github(incomplete=True)))
        self.assertEqual(report["status"], "partial")

    def test_dedup_preserves_provenance(self):
        client = FakeClient(github(repository(), repository(html_url="https://github.com/EXAMPLE/PDF-TOOL.git/")))
        report = search.run_search("pdf", ["github"], client=client)
        self.assertEqual(len(report["candidates"]), 1)
        self.assertEqual(report["duplicates_removed"], 1)
        self.assertEqual(len(report["candidates"][0]["provenance"]), 2)

    def test_skills_from_same_repo_remain_distinct(self):
        client = FakeClient({"tree": [{"type": "blob", "path": "skills/pdf/SKILL.md", "sha": "abc"},
                                       {"type": "blob", "path": "skills/pdf-edit/SKILL.md", "sha": "def"}]}, {"tree": []})
        report = search.run_search("pdf", ["official-skills"], client=client)
        self.assertEqual(len(report["candidates"]), 2)
        self.assertEqual(report["candidates"][0]["artifact_type"], "skill")
        self.assertIn("content not fetched", report["candidates"][0]["description"])
        self.assertTrue(all("api.github.com/repos/" in url for url in client.calls))

    def test_registry_filters_latest_follows_cursor_and_never_copies_secret_headers(self):
        first = {"servers": [registry(remotes=[{"headers": [{"value": "sensitive-value"}]}])], "metadata": {"nextCursor": "next"}}
        second = {"servers": [registry("org.example/pdf2")], "metadata": {}}
        client = FakeClient(first, second)
        report = search.run_search("pdf", ["mcp"], pages=2, client=client)
        self.assertEqual(parse_qs(urlsplit(client.calls[0]).query)["version"], ["latest"])
        self.assertEqual(parse_qs(urlsplit(client.calls[1]).query)["cursor"], ["next"])
        self.assertEqual(len(report["candidates"]), 2)
        self.assertEqual(report["status"], "completed")
        self.assertNotIn("sensitive-value", json.dumps(report))
        self.assertIn("/versions/latest", report["candidates"][0]["url"])
        self.assertEqual(report["candidates"][0]["artifact_type"], "mcp-server")

    def test_registry_dedup_keeps_multiple_servers_in_same_repository(self):
        repo = {"url": "https://github.com/example/pdf"}
        report = search.run_search("pdf", ["mcp"], client=FakeClient({"servers": [registry(repository=repo), registry("org.other/pdf", repository=repo)], "metadata": {}}))
        self.assertEqual(len(report["candidates"]), 2)

    def test_short_registry_query_not_sent(self):
        client = FakeClient()
        report = search.run_search("ai", ["mcp"], client=client)
        self.assertEqual(report["sources"][0]["status"], "invalid-query")
        self.assertFalse(report["network_attempted"])
        self.assertFalse(client.calls)

    def test_invalid_schema_does_not_become_empty_success(self):
        for provider, payload in [("github", {}), ("github", []), ("mcp", {"servers": "oops"}), ("official-skills", {"tree": None})]:
            with self.subTest(provider=provider, payload=payload):
                report = search.run_search("pdf", [provider], client=FakeClient(payload, payload))
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["sources"][0]["status"], "invalid-response")

    def test_result_filter_and_stable_scoring(self):
        payload = github(repository(), repository("example/pdf-mcp", description="PDF MCP server"))
        a = search.run_search("pdf", ["github"], kind="mcp-server", client=FakeClient(payload))
        b = search.run_search("pdf", ["github"], kind="mcp-server", client=FakeClient(payload))
        self.assertEqual(len(a["candidates"]), 1)
        self.assertEqual(a["candidates"][0]["id"], b["candidates"][0]["id"])
        self.assertEqual(a["candidates"][0]["score"], b["candidates"][0]["score"])

    def test_limits_rejected_before_network(self):
        for kwargs in [{"limit": 0}, {"limit": 51}, {"pages": 4}, {"timeout": 31}, {"retries": 2}, {"token_env": "a secret"}, {"web_key_env": "a secret"}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                search.run_search("pdf", ["github"], client=FakeClient(), **kwargs)

    def test_untrusted_urls_and_control_characters(self):
        for url in ["file:///tmp/x", "http://example.org/x", "https://127.0.0.1", "https://[::1]", "https://user:secret@example.org", "https://localhost", "https://a.local", "https://x.example:999/x"]:
            with self.subTest(url=url):
                self.assertIsNone(search.public_url(url))
        report = search.run_search("pdf", ["github"], client=FakeClient(github(repository(description="pdf\x1b[2J\nmalicious"))))
        self.assertNotIn("\x1b", report["candidates"][0]["description"])
        self.assertNotIn("\n", report["candidates"][0]["description"])

    def test_web_missing_configuration_is_not_searched(self):
        with patch.dict("os.environ", {}, clear=True):
            client = FakeClient()
            report = search.run_search("pdf", ["web"], client=client)
        self.assertFalse(report["network_attempted"])
        self.assertEqual(report["sources"][0]["status"], "configuration-required")
        self.assertFalse(client.calls)

    def test_configured_web_provider_returns_citations_without_fetching_pages(self):
        client = FakeClient({"query": {"more_results_available": False}, "web": {"results": [
            {"title": "PDF AI assistant", "url": "https://example.org/pdf", "description": "AI tool for PDF conversion"}]}})
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "not-a-real-key"}):
            report = search.run_search("pdf", ["web"], client=client)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(urlsplit(client.calls[0]).hostname, "api.search.brave.com")
        self.assertEqual(report["candidates"][0]["url"], "https://example.org/pdf")
        self.assertNotIn("not-a-real-key", json.dumps(report))
        self.assertFalse(report["market_cache_updated"])

    def test_web_functional_queries_and_fragments_survive_normalization(self):
        rows = [{"title": "PDF", "url": url} for url in [
            "https://example.org/view?id=one&utm_source=test",
            "https://example.org/view?id=two", "https://example.org/view?id=one&utm_medium=test",
            "https://example.org/app#/pdf-one", "https://example.org/app#/pdf-two"]]
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "test-only"}):
            report = search.run_search("pdf", ["web"], client=FakeClient({"query": {}, "web": {"results": rows}}))
        self.assertEqual(len(report["candidates"]), 4)
        self.assertEqual(report["duplicates_removed"], 1)
        self.assertIn("https://example.org/view?id=one", [c["url"] for c in report["candidates"]])

    def test_dedup_uses_stronger_evidence_regardless_of_provider_order(self):
        url = "https://github.com/openai/skills/blob/main/skills/pdf/SKILL.md"
        web = {"query": {}, "web": {"results": [{"title": "PDF", "url": url}]}}
        tree = {"tree": [{"type": "blob", "path": "skills/pdf/SKILL.md", "sha": "abc"}]}
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "test-only"}):
            a = search.run_search("pdf", ["web", "official-skills"], client=FakeClient(web, tree, {"tree": []}))
            b = search.run_search("pdf", ["official-skills", "web"], client=FakeClient(tree, {"tree": []}, web))
        for report in (a, b):
            self.assertEqual(len(report["candidates"]), 1)
            self.assertEqual(report["candidates"][0]["artifact_type"], "skill")
            self.assertEqual(report["candidates"][0]["revision"], "abc")
            self.assertEqual(len(report["candidates"][0]["provenance"]), 2)
        self.assertEqual(a["candidates"][0]["score"], b["candidates"][0]["score"])

    def test_explicit_skill_marker_takes_precedence_over_domain_mcp_keyword(self):
        report = search.run_search("mcp", ["github"], kind="skill", client=FakeClient(github(
            repository("example/mcp-agent-skill", description="Agent skill for developing MCP servers"))))
        self.assertEqual(report["candidates"][0]["artifact_type"], "skill")

    def test_arbitrary_website_trailing_slashes_are_not_collapsed(self):
        self.assertEqual(search.public_url("https://example.org/tool/"), "https://example.org/tool/")
        self.assertNotEqual(search.canonical("https://example.org/tool/"), search.canonical("https://example.org/tool"))
        self.assertEqual(search.canonical("https://github.com/Example/PDF/"), "https://github.com/example/pdf")

    def test_github_case_sensitive_file_paths_remain_distinct(self):
        rows = [{"path": path, "html_url": "https://github.com/Example/Skills/blob/main/" + path,
                 "repository": repository("Example/Skills")} for path in ["PDF/SKILL.md", "pdf/SKILL.md"]]
        report = search.run_search("pdf", ["github-code"], client=FakeClient(github(*rows)))
        self.assertEqual(len(report["candidates"]), 2)
        self.assertEqual(search.canonical("https://github.com/EXAMPLE/SKILLS"), "https://github.com/example/skills")

    def test_url_controls_and_credential_queries_are_rejected_before_printing(self):
        for url in ["https://example.org/\x1b[2J", "https://example.org/\x00", "https://example.org/?access_token=hidden"]:
            self.assertIsNone(search.public_url(url))
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "test-only"}):
            report = search.run_search("pdf", ["web"], client=FakeClient({"query": {}, "web": {"results": [
                {"title": "PDF", "url": "https://example.org/\x1b[2J"}]}}))
        out = StringIO()
        with redirect_stdout(out):
            search.emit_markdown(report)
        self.assertNotIn("\x1b", out.getvalue())
        self.assertFalse(report["candidates"])

    def test_markdown_reports_failure_and_provenance(self):
        report = search.run_search("pdf", ["github"], client=FakeClient(github(repository())))
        out = StringIO()
        with redirect_stdout(out):
            search.emit_markdown(report)
        self.assertIn("https://github.com/example/pdf-tool", out.getvalue())
        self.assertIn("review-required", out.getvalue())
        self.assertIn("completed_at", json.dumps(report))


class TransportTests(unittest.TestCase):
    def client_with(self, *outcomes, **kwargs):
        client = search.PublicClient(**kwargs)
        client.opener = Mock()
        client.opener.open.side_effect = list(outcomes)
        return client

    def response(self, value):
        response = Mock()
        response.__enter__ = Mock(return_value=BytesIO(value))
        response.__exit__ = Mock(return_value=False)
        return response

    def error(self, code, **headers):
        return HTTPError("https://api.github.com/search/repositories", code, "reason", headers, BytesIO(b"secret body"))

    def test_fixed_endpoints_only_and_no_redirect_follow(self):
        client = self.client_with()
        for url in ["https://api.github.com/user", "https://evil.example/search/repositories", "http://api.github.com/search/repositories", "https://user:password@api.github.com/search/code", "https://api.github.com:444/search/code"]:
            with self.assertRaises(search.SearchError) as caught:
                client.get(url)
            self.assertEqual(caught.exception.status, "blocked-endpoint")
        client.opener.open.assert_not_called()
        self.assertIsNone(search.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example"))

    def test_tokens_are_host_scoped_and_not_in_urls(self):
        client = self.client_with(self.response(b"{}"), self.response(b"{}"), self.response(b"{}"), token="github-secret", web_key="brave-secret")
        for url in ["https://api.github.com/search/code?q=pdf", "https://registry.modelcontextprotocol.io/v0.1/servers?search=pdf", "https://api.search.brave.com/res/v1/web/search?q=pdf"]:
            client.get(url)
        requests = [call.args[0] for call in client.opener.open.call_args_list]
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer github-secret")
        self.assertIsNone(requests[1].get_header("Authorization"))
        self.assertIsNone(requests[2].get_header("Authorization"))
        self.assertIsNone(requests[0].get_header("X-subscription-token"))
        self.assertEqual(requests[2].get_header("X-subscription-token"), "brave-secret")
        self.assertTrue(all("secret" not in req.full_url for req in requests))

    def test_no_retries_for_permissions_limits_or_redirects(self):
        for code, headers, status in [(401, {}, "authentication-required"), (403, {}, "permission-denied"), (403, {"X-RateLimit-Remaining": "0"}, "rate-limited"), (429, {"Retry-After": "120"}, "rate-limited"), (302, {"Location": "https://evil.example"}, "redirect-blocked")]:
            client = self.client_with(self.error(code, **headers))
            with self.subTest(code=code), self.assertRaises(search.SearchError) as caught:
                client.get("https://api.github.com/search/code")
            self.assertEqual(caught.exception.status, status)
            self.assertEqual(client.opener.open.call_count, 1)
            self.assertNotIn("secret", str(caught.exception))

    def test_transient_retries_are_bounded(self):
        client = self.client_with(self.error(503), self.response(b"{}"))
        with patch.object(search.time, "sleep"):
            self.assertEqual(client.get("https://api.github.com/search/code"), {})
        self.assertEqual(client.opener.open.call_count, 2)
        client = self.client_with(self.error(503), retries=0)
        with self.assertRaises(search.SearchError):
            client.get("https://api.github.com/search/code")
        self.assertEqual(client.opener.open.call_count, 1)

    def test_incomplete_http_response_becomes_source_failure_and_retains_other_results(self):
        client = self.client_with(self.response(json.dumps(github(repository())).encode()), IncompleteRead(b"partial", 50))
        report = search.run_search("pdf", ["github", "mcp"], client=client)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(len(report["candidates"]), 1)
        self.assertEqual(report["sources"][1]["status"], "network-error")

    def test_body_deadline_cannot_be_extended_by_slow_chunks(self):
        client = self.client_with(self.response(b"{}"), timeout=1)
        with patch.object(search.time, "monotonic", side_effect=[0, 0.1, 1.1]), self.assertRaises(search.SearchError) as caught:
            client.get("https://api.github.com/search/code")
        self.assertEqual(caught.exception.status, "timeout")

    def test_premature_eof_with_content_length_is_rejected(self):
        class Truncated(BytesIO):
            length = 20
        response = self.response(b"{}")
        response.__enter__.return_value = Truncated(b"{}")
        client = self.client_with(response)
        with self.assertRaises(search.SearchError) as caught:
            client.get("https://api.github.com/search/code")
        self.assertEqual(caught.exception.status, "truncated-response")

    def test_timeout_network_invalid_json_and_size_limits(self):
        cases = [(TimeoutError(), "timeout"), (URLError("secret"), "network-error"),
                 (self.response(b"not json"), "invalid-response"),
                 (self.response(b"x" * (search.MAX_BYTES + 1)), "response-too-large")]
        for outcome, status in cases:
            client = self.client_with(outcome)
            with self.subTest(status=status), self.assertRaises(search.SearchError) as caught:
                client.get("https://api.github.com/search/code")
            self.assertEqual(caught.exception.status, status)


if __name__ == "__main__":
    unittest.main()
