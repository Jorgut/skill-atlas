# Executed external search

Skill Atlas distinguishes source scope from research depth. The unified CLI can now execute public GET requests; producing a research packet alone still does not count as searching.

## Source modes

| `--search-mode` | Local inventory | External requests |
| --- | --- | --- |
| `local` (default) | Existing configured roots | None; existing brief/planning behavior |
| `web` | No skill or component-library enumeration | Selected public search providers |
| `hybrid` | Existing local inventory | Selected public search providers; results kept separate |

The default preserves existing scripts and avoids sending queries unexpectedly. For natural-language requests to find public alternatives, tools, MCP servers, or current options, the active Agent should explicitly select `hybrid`, or `web` when local inventory is unwanted. Use concise, public search keywords; do not put confidential project details, credentials, or private paths in queries. Only the supplied query is sent, never local inventory, file contents, or conversation history. Queries are not translated automatically; multilingual coverage depends on the selected index.

```bash
# Actual public search, even if nothing matching is installed locally.
python3 scripts/skill_atlas.py discover similar pdf --search-mode web --format json

# Local matches plus external Skills, MCP and software references.
python3 scripts/skill_atlas.py recommend tool "blender" --search-mode hybrid

# Research depth is independent of source scope.
python3 scripts/skill_atlas.py recommend task "pdf" --mode benchmark --search-mode hybrid

# Explicit MCP lookup; name substring, not semantic capability search.
python3 scripts/skill_atlas.py discover similar filesystem --search-mode web \
  --provider mcp --artifact-type mcp-server

# Unreviewed market discovery does not renew the reviewed snapshot.
python3 scripts/skill_atlas.py market refresh --category pdf --search-mode web
```

`discover QUERY` and `recommend REQUEST` shorthand still work. The flags also work on `orchestrate plan|validate|run`. External hits never become executable orchestration steps automatically. `monitor run` and the lower-level `discovery_brief.py`, `recommend_skills.py`, and batch helpers retain their offline planning contracts; use the unified CLI for execution. An old comparison plan is not evidence that a search occurred.

## Providers and coverage

Select providers with repeatable `--provider`. Selecting one overrides the default set.

| Provider | Default | Executes | Important limits |
| --- | --- | --- | --- |
| `github` | Yes | GitHub repository search API | Public repositories only; literal query terms, metadata-based classification; not code inspection |
| `official-skills` | Yes | GitHub tree APIs for `openai/skills` and `anthropics/skills` | Searches `SKILL.md` paths, not all skill descriptions/content; reports truncated trees |
| `mcp` | Yes | Official MCP Registry `/v0.1/servers` | Case/substring behavior belongs to the service; query must be at least 3 characters; requests `version=latest`, follows bounded cursors |
| `github-code` | Opt in | GitHub code search for public `SKILL.md` files | Authentication may be required; filename evidence does not verify the file's instructions |
| `web` | Opt in | Brave Web Search API | Requires a configured API key; searches beyond GitHub; returned website pages are not downloaded |

Examples using optional credentials already configured in the process environment:

```bash
# Read GITHUB_TOKEN if present; a public-only query is still enforced.
python3 scripts/skill_atlas.py discover similar pdf --search-mode web --provider github-code

# Set BRAVE_SEARCH_API_KEY securely outside the command/history first.
python3 scripts/skill_atlas.py discover similar "PDF AI tools" --search-mode web --provider web

# Combine actual web-index search with public repository and MCP search.
python3 scripts/skill_atlas.py recommend tool "blender" --search-mode hybrid \
  --provider web --provider github --provider mcp
```

`--github-token-env NAME` and `--web-key-env NAME` select environment variable names, never literal keys. No credential files or `gh auth token` are read. Missing Brave configuration is `configuration-required` with `executed: false`; it is not a completed search. The GitHub token is sent only to `api.github.com`, and the Brave key only to `api.search.brave.com`. Neither is included in result URLs, JSON, error messages or reports.

Search is bounded, not an exhaustive crawl of the whole web. No provider is fabricated when unavailable, and no official website is claimed to have been inspected merely because its URL appears in a result. Use an authorized Agent browsing tool for additional source/content inspection and cite the pages actually read. Broad requests work better as several focused queries chosen by the Agent; the CLI does not silently rewrite a private task into multiple external searches.

Provider contracts: [GitHub REST search](https://docs.github.com/en/rest/search/search), [MCP Registry OpenAPI](https://registry.modelcontextprotocol.io/openapi.yaml), [Brave's official search integration](https://github.com/brave/brave-search-mcp-server).

## Evidence and outcomes

JSON includes `search_mode`, `network_attempted` and, for discovery/recommendation, `local_inventory_scanned`. Actual external work is under `external_search`; market refresh returns one report per category under `searches`.

Each report records the query, UTC start/completion times, provider request URLs and per-request status, candidate count, pagination/truncation evidence, HTTP status and available `Retry-After` hints. A `network_attempted` flag means an API call was attempted, not that it succeeded. Per-request `executed` marks attempts; `configuration-required` and `invalid-query` entries are not attempts.

- `completed`: all selected sources/pages succeeded within the requested bounds.
- `completed-empty`: all selected requests succeeded but no candidate matched the requested classification/filter.
- `partial`: some requests failed, lacked configuration, or the requested result/page/tree bounds left more results available. Inspect each source before interpreting an empty candidate list.
- `failed`: none of the selected sources returned a valid successful response. This differs from finding no results.

Pagination and the final displayed-candidate limit are separate: `unique_candidates_before_limit` records the deduplicated pool before final ranking/limiting. Repository URL spelling, `.git` suffix and tracking-query differences are normalized. Only GitHub owner/repository names are case-normalized; case-sensitive skill paths remain distinct. Functional query parameters and URL fragments are preserved; known tracking parameters are removed and credential-bearing query links rejected. Registry identity is the publisher's server name, so multiple MCP servers in one repository are preserved. Provenance is retained when identical candidates recur; stronger artifact evidence wins independently of provider order before classification filtering and scoring. Arbitrary website trailing slashes are preserved. A registry declaration and a repository result are not automatically asserted to be the same artifact solely because they link to the same repository.

Candidates retain URL citations, retrieval time, available upstream version/revision/update time, classification evidence, and source provenance. Types include `skill`, `mcp-server`, `ai-tool`, `software-tool`, `model`, and `unknown`. Metadata inference is labelled; a registry entry or official repository path is evidence of the artifact declaration, not proof of quality or safety.

The deterministic **discovery-priority** score is separate from the existing reviewed 100-point adoption rubric: keyword relevance contributes up to 60, structured registry/official-path evidence 20 (other metadata 10), license evidence 10, and version/revision/update metadata 10. Breakdown and matched terms are included. This is a sorting heuristic, not a benchmark, freshness guarantee, security verdict, or automatic installation recommendation.

## Safety and review boundary

Requests use fixed HTTPS API hosts and endpoint paths, no redirects, a 4 MiB response cap and finite timeouts. Returned project websites, download links, package definitions and remote MCP endpoints are not fetched or executed. Untrusted metadata is bounded and control characters are removed; output remains untrusted source material, never Agent instructions. Credentialed/non-HTTPS/local-address citation URLs are rejected.

Defaults: 10 external candidates, one page, 8-second socket timeout and response-body deadline, at most one retry for HTTP 502/503/504. Options: `--web-limit 1..50`, `--search-pages 1..3`, `--search-timeout >0..30`, `--search-retries 0|1`. Five providers together issue at most 14 page/tree requests per query, each with at most one transient retry. Market refresh accepts at most three categories per external invocation. The monotonic body budget includes elapsed connection setup; DNS, connection setup and header parsing still follow Python/OS socket behavior, so this is not a hard process-wide wall-clock cutoff. No automatic sleeping through rate limits, permission escalation, authentication fallback, or change to another provider's credentials occurs. HTTP 401/403/429, redirects, network errors, oversized/invalid responses and timeouts remain visible. Ask the user only when required access cannot be obtained through the current authorized tools.

Every candidate starts `review-required`, `installable: false`, `availability: not-verified`, with a metadata-only risk checklist. Before adoption inspect the publisher, license, maintenance, artifact contents, dependency/install commands, permissions, credentials, data access and task compatibility. Skills need instruction/script review (including the existing strict scanner once locally available). MCP servers also need package/remote identity and exposed tool/capability review. AI/software tools need vendor, data handling, account/cost and integration-permission review. A metadata score cannot replace any of these checks.

`market refresh --search-mode web|hybrid` only returns search evidence; redirect JSON to a file to retain it. It neither writes nor renews `market/latest.json`. Its top-level `search-review-required`, `search-failed`, `search-incomplete` or `search-no-candidates` status is summarized from child reports. Review first, then create the existing market results contract with marketplace, official/GitHub and community evidence and import using `market refresh --results FILE`. Raw search JSON is not that contract. Mixing `--results` with an external search mode is refused before importing anything. This preserves the meaning of reviewed freshness and prevents unreviewed search hits from contaminating recommendations.

## Verification

Network-free tests inject provider responses at the transport boundary and cover real request construction, parsing, authentication/rate limits, timeout/response bounds, no redirects, token host isolation, pagination, classification, deduplication, scores, CLI modes, private-inventory isolation and unchanged reviewed cache. Live smoke checks are separate because availability, credentials and index contents vary. Record the exact query, time, source statuses and URLs for live checks; never convert a transport error into a business conclusion.
