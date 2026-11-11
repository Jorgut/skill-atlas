---
name: skill-atlas
description: "Manage agent skills across platforms: inventory, duplicates, upstream evidence, safe updates, public alternatives, task/model/tool recommendations, and multi-skill orchestration. Use also to configure shared rules, per-project context, cross-agent handoff, read-only local agent environment scanning, and optional local cross-agent messages. Read-only by default; apply changes only within explicit user authorization."
---

# Skill Atlas

Use this cross-platform skill manager to inventory an agent-skill ecosystem, track updates, discover alternatives, recommend skill stacks, and orchestrate skills with models and software connectors. It is read-only by default.

Use `scripts/skill_atlas.py` as the unified entry point, including executed public search. Treat `scripts/audit_skills.py` as the platform-neutral local inventory helper. Use `scripts/opencode_skill_manager.py` only as a compatibility helper when the user explicitly asks for the older OpenCode upstream/evolution workflow.

Do not assume that a published user's machine has any particular platform, directory, skill count, duplicate, or symlink layout. Default roots are discovery conventions only. Treat every inventory result as runtime evidence, and accept repeated `--root` arguments for custom platforms or canonical stores.

Choose the workflow from the request:

- inventory, duplicates, updates, symlinks, or consolidation: run the audit workflow
- a product idea, professional task, model question, or software workflow with uncertainty about which capabilities to use: run recommendation and orchestration
- stronger alternatives or competitors for installed skills: run external discovery
- public-market freshness or a reviewed shared market snapshot: run market
- recurring competitor comparison with historical differences: run monitor
- cross-agent rules, project context, or handoff setup: read the cross-agent context workflow below
- inspect which local agent tools, rule roots, skill roots, or Skill Atlas copies exist: run `agents scan` (read-only)
- duplicated project copies, divergent `AGENTS.md`/`CLAUDE.md`/state docs, or nested project roots: run `projects audit` (read-only)
- large agent homes, caches, sessions, plugins, project media, build artifacts, Git objects, or disk pressure: run `disk scan` (read-only)
- handing a compact review or action request to a local agent: read Agent Handoff Messages below
- a downloaded or proposed third-party skill: run strict security review

## Executed Public Search

For requests to find public Skills, MCP servers, AI/software tools or current alternatives, read [docs/external-search.md](docs/external-search.md) and run the unified CLI with `--search-mode hybrid` (or `web` to skip local inventory). CLI defaults remain `local` for backward compatibility. Do not answer a public-search request with only local scanning or generated query suggestions.

```bash
python3 <skill-root>/scripts/skill_atlas.py discover similar pdf --search-mode web
python3 <skill-root>/scripts/skill_atlas.py recommend tool "blender" --search-mode hybrid
python3 <skill-root>/scripts/skill_atlas.py market refresh --category pdf --search-mode web
```

Use concise public keywords. Do not send private project text, file contents or inventory. The default providers execute GitHub repository search, official Skills tree/path lookup and official MCP Registry name search. Add `--provider github-code` for code search or `--provider web` for the Brave web index when the required API credentials are configured. Repeated provider flags select the exact source set. Never claim a missing provider ran, a linked website was inspected, or bounded API results cover the entire web. Keep per-source execution status, timestamp, limitations and citation URLs visible; failed/limited searches do not prove there are no candidates.

External hits are typed metadata candidates, not reviewed installation recommendations. Preserve their provenance, classification basis and discovery-priority score, and complete the risk checklist/content review before adoption. No search hit automatically enters orchestration or the reviewed market cache. `--mode quick|balanced|benchmark` controls comparison planning depth, independently of network scope. Use additional authorized browsing when the bounded API coverage is insufficient, recording what actually executed.

## Cross-Agent Context and Handoff

When asked to connect agent tools, organize per-project memory, or verify shared context, read [docs/cross-agent-collaboration.md](docs/cross-agent-collaboration.md). Discover each tool's actual instruction entry, reuse existing project state, and distinguish configured files from verified loading and handoff. Rule-entry setup is agent-led; the optional task checkpoint CLI is described under Integrated Closeout and task continuity. Apply setup changes only within the user's authorized scope and preserve backups and concurrent work.

For WorkBuddy setup, read the WorkBuddy adapter discovery section in that guide; verify its effective rules root, project-guidance precedence, account scope, and loading conditions.

Reusable public starting points are available in [templates/README.md](templates/README.md): general rules, project rules, and project context. Adapt them to verified tool/project requirements without publishing private records.

## Local Agent Environment Scan

Use `agents scan` when asked which coding-agent tools leave evidence on this
machine, where their rule and skill roots are, or whether local Skill Atlas
copies disagree on a version. The scan is read-only: it inspects filesystem
metadata and local `skill.json` manifests, never executes a tool, opens no
network connection, reads no credentials or session data, and writes nothing.
Levels are file-evidence only: `not-detected`, `detected`, or `configured`. A
`configured` result is not proof of runtime loading, and only paths documented
in this repository can reach it; candidate paths and home overrides stay
unverified hints. Use `--project .` to report project-scoped rule candidates
and `--format json` for the full result. Read
[docs/agent-environments.md](docs/agent-environments.md) for the catalog,
evidence levels, output contract, limitations, and how to verify a tool. This
is discovery evidence, not handoff verification.

## Project Root and Duplicate Documentation Audit

Use `projects audit` when asked which local project copies exist, whether
duplicated checkouts diverge in their
`AGENTS.md`/`CLAUDE.md`/`CONTEXT.md`/`PROJECT_STATE.md`, or whether one project
is nested inside another. It discovers candidate roots by `.git` entries and
discovery markers, groups likely duplicates as confirmed (normalized git remote,
compared case-insensitively) or probable (case-folded directory name), compares
the listed project documents by SHA-256 without printing their contents, and
flags divergent documents and nested roots. These are evidence levels, not proof
that copies are identical. The audit is read-only: it never runs git
(`.git/config` and `.git/HEAD` are parsed by hand), never writes, moves, merges,
archives, or deletes, never opens a network connection, and never prints
document contents. Recommendations are plans with
`requires_user_confirmation: true`; review the divergent documents before acting.
Use repeated `--project`, `--root` with `--depth`, and `--format json`. Read
[docs/project-root-audit.md](docs/project-root-audit.md) for identity rules, the
256 KiB hash cap, recommendations, output contract, and a worked example.

## Disk Usage Audit

Use `disk scan` when asked what agent work is using local disk space, or before
cleaning large agent homes, caches, sessions, plugins, project media, build
artifacts, or Git objects. It scans known agent roots under `--home`, plus
repeated `--root` directories and one optional `--project`, and reports apparent
and allocated sizes, file counts, categories, risk levels, largest files by
allocated size at or above `--min-file-mb`, and plan-only suggested actions.
Allocated size (`st_blocks × 512`) is the real disk usage and drives the
threshold, sorting and risk totals; apparent size (`st_size`) can be much larger
for sparse files. It reads metadata only: no file contents, credentials, session
text, or account data; it never follows symlinks while walking, opens no network
connection, and by default never moves or deletes anything. The opt-in
`disk scan --apply --to-trash --confirm` (optional repeated `--risk low|medium`,
default `low`) moves selected low/medium direct-child candidates into `~/.Trash`
(or `--trash-dir`) with unique names. High-risk entries such as databases and
`.git` objects and symlinks are never moved, `rm -rf` and permanent deletion are
never used, and space is freed only after the Trash is emptied.
Allocated size is not a promise of reclaimable space because clones, snapshots
and hard links can share blocks, and database or Git objects must never be
deleted directly. Read [docs/disk-scan.md](docs/disk-scan.md) for known roots,
categories and risk, the JSON contract, the opt-in cleanup rules, limitations,
and a worked example.

## Agent Handoff Messages

The optional `message` command group relays compact handoff notes through local
files under `.agent-state/messages/<task>/`. Use `message send` to queue a
summary with short evidence pointers, then have the addressed recipient read
`message inbox` or `message show` and record `taken`, `completed`, or `refused`
with `message ack`. A message sent with `--requires-approval` cannot be recorded
as `completed` until a person runs `message approve`. Nothing is sent over the
network: no agent is started, woken, or notified, and a queued file is not proof
of delivery. Use a request ID for safe retries, respect the default 24-hour TTL
and 10-pass chain limit, keep `.agent-state/messages/` uncommitted, and never place
secrets in a payload. This is Stage 1.5 transport only; the Stage 2 orchestrator
remains unimplemented. Read [docs/agent-messaging.md](docs/agent-messaging.md)
for flags, states, limits, and a worked Codex → Claude Code example.

## Commands

Treat this command tree as stable across Agent platforms:

```text
skill-atlas
├── install          preview or explicitly apply cross-platform installation
├── manage
│   ├── scan       inventory configured skill roots
│   ├── status     inspect sources and optional upstream freshness
│   ├── update     generate an update plan; never apply automatically
│   ├── dedupe     generate a duplicate and consolidation plan
│   ├── sync       generate a canonical-directory and symlink plan
│   └── self
│       ├── status    inspect the installed Skill Atlas version or a release candidate
│       ├── update    plan or explicitly apply a reviewed Skill Atlas update
│       └── rollback  list backups or explicitly restore one
├── discover
│   ├── similar       find similar public skills
│   ├── competitors   find references for user-authored skills; never replace them
│   ├── alternatives  find replacement or complementary candidates
│   └── gaps          find missing capabilities for a task or product
├── recommend
│   ├── product    recommend a product skill stack
│   ├── task       recommend skills for a concrete task
│   ├── model      identify evaluation skills and current model research
│   └── tool       identify skills, APIs, plugins, MCP, and software connectors
├── orchestrate
│   ├── plan       build an ordered multi-skill workflow
│   ├── validate   check role overlap, duplication, and capability gaps
│   └── run        stage an execution plan and wait for explicit confirmation
├── market
│   ├── status     inspect shared public-market snapshot freshness
│   └── refresh    create a research packet or save reviewed market results
├── monitor
│   ├── add        create a daily, weekly, monthly, or quarterly monitor
│   ├── list       list monitor configurations
│   ├── status     inspect one schedule and its snapshot count
│   ├── due        list comparisons whose next run is due
│   ├── run        create a research packet or record reviewed results
│   ├── history    compare saved snapshots over time
│   └── remove     remove configuration while retaining snapshots
├── agents
│   └── scan       read-only local evidence for agent tools, rules, and skills
├── disk
│   └── scan       read-only audit of agent, cache and project disk usage
├── projects
│   └── audit      read-only audit of project roots and duplicate project docs
└── message
    ├── send       queue one compact handoff message for a local agent or person
    ├── inbox      list messages addressed to one agent; read-only
    ├── show       show one message and its local receipts; read-only
    ├── ack        record taken, completed, or refused
    └── approve    record a person's approval before completion
```

Commands are read-only by default. `install` previews its exact copy and link operations unless the user supplies both `--apply` and `--confirm`. `manage update`, `manage sync`, and `orchestrate run` always produce plans only. `manage self update` and `manage self rollback` may modify the Skill Atlas installation only when the user supplies both `--apply` and `--confirm` after reviewing the exact source or backup. The `message` actions write only under `.agent-state/messages/`; they do not contact another agent or modify project files. `message approve` records a person's local approval and must not be run on another person's behalf. `agents scan` reads filesystem metadata and local Skill Atlas manifests only; it never executes an agent tool and writes nothing. `disk scan` reads file metadata only; it never reads file contents, follows symlinks while walking, or deletes, moves, compresses, or archives anything. `projects audit` reads metadata, small `.git` files, and documentation hashes only; it never runs git and writes nothing. Never install, overwrite, delete, symlink, update, or execute external actions without that explicit confirmation.

Agent command syntax varies. If a platform does not pass arguments after `$skill-atlas` or does not support dollar-prefixed skill calls, accept equivalent natural language such as "Use Skill Atlas manage" or "用 Skill Atlas 编排这个任务". Preserve these command meanings across platforms.

The bundled `commands/skill-atlas.md` is a portable slash-command adapter for
platforms that load Markdown command files. Use the installer below to register
it; copying the skill folder alone does not register a slash command. Codex uses
`$skill-atlas` or natural-language invocation rather than a custom
`/skill-atlas` menu entry.

Preview a cross-platform installation from a cloned or downloaded package:

```bash
python3 scripts/skill_atlas.py install --all-platforms --commands
```

After reviewing every destination and target, apply it explicitly:

```bash
python3 scripts/skill_atlas.py install --all-platforms --commands --apply --confirm
```

The installer keeps one canonical copy under `~/.agents/skills/skill-atlas`,
creates platform skill links, and registers `/skill-atlas` for OpenCode and
Claude Code. It never overwrites an existing path. Re-running the same install
is idempotent. Use repeated `--platform codex|opencode|claude` instead of
`--all-platforms` for a subset.

To discover a local component library, scope the scan explicitly instead of crawling arbitrary project trees:

```bash
python3 <skill-root>/scripts/skill_atlas.py orchestrate plan \
  "Build a React liquid glass interface" \
  --component-root /path/to/component-repository
```

## Recurring Competitor Monitoring

Use `monitor add` when a user wants Skill Atlas to revisit competitors on a schedule. The monitor stores configuration and snapshots under `~/.local/share/skill-atlas` by default; `--state-dir` may override this for automation or testing.

`monitor run ID` creates the current competitor discovery packet and records `research-required`. It remains due and does not advance the schedule. This is not a completed web comparison. The active Agent must perform current web research, verify inspectable sources, review license and maintenance, confirm platform compatibility, and run strict security review before producing a results JSON.

Record reviewed results with:

```bash
python3 <skill-root>/scripts/skill_atlas.py monitor run closeout --results results.json
```

Results use this minimal contract:

```json
{
  "summary": "Material changes since the last comparison",
  "candidates": [
    {"name": "Candidate", "url": "https://github.com/example/candidate"}
  ]
}
```

The completed snapshot records added, removed, and unchanged candidate identities compared with the prior snapshot. User-authored skills remain protected reference targets and are never automatically replaced.

Skill Atlas deliberately has no resident background process. Codex Automation, OpenCode automation, `cron`, or `launchd` should periodically invoke `monitor due`, then ask an Agent to complete due research packets. Do not describe a generated packet as a completed comparison.

## Default Workflow

1. Run the bundled script in read-only mode:

```bash
python3 <skill-root>/scripts/audit_skills.py --format markdown
```

2. Explain only the buckets found by the scan:

- Loadable now by Codex: `~/.codex/skills`, `~/.agents/skills`
- Loadable by OpenCode: `~/.config/opencode/skills`
- Loadable by Claude-style setups: `~/.claude/skills`
- Cached or marketplace copies: plugin caches, package caches, downloaded marketplaces
- Custom or standalone roots supplied by the user

3. Classify maintenance ownership before recommending action:

- `user-authored`: the user created or locally evolved it. Never replace; only find competitors/references.
- `external-maintained`: installed from GitHub or another author-maintained source, with an upstream URL or inspectable source repo. It may be updated from upstream and shared across platforms via symlinks after review.
- `tool-bundled/cache`: installed inside plugin caches, marketplace caches, or tool-managed directories. Do not edit in place; copy or symlink only from user-controlled canonical directories.
- `unknown-local`: no upstream evidence and unclear origin. Report as needs source confirmation before update or consolidation.

4. Call out exact duplicates by parsed `name`, especially when the same skill exists in more than one platform root.

5. Explain symlink status without assuming consolidation is already configured:

- `Symlinked Skills` are entries where the loadable skill path or its parent directory points to another canonical location.
- `Consolidation Suggestions` mean the same parsed skill name exists as separate physical copies in multiple agent-loadable roots.
- Recommend one canonical directory plus symlinks when the user wants Codex, OpenCode, Claude, and other agents to share one maintained copy.
- A canonical directory is optional and user-controlled. Derive proposed paths from the scan and platform configuration; do not hard-code a universal canonical location.

6. Treat update status as evidence-based:

- `up-to-date`: local hash matches recorded upstream raw URL
- `differs`: local hash differs from recorded upstream raw URL
- `no-upstream`: no machine-readable upstream URL was found
- `fetch-failed`: an upstream URL exists but could not be fetched
- `skipped`: network checking was not requested

7. Do not apply updates automatically. If the user asks to update, symlink, consolidate, or delete, present a plan with target skill paths, upstream URLs, backup path, and rollback method before making changes.

## Product Skill Recommendation Workflow

Use this workflow when a user describes a product, professional task, service, workflow, model-selection question, or software integration and does not know which capabilities are useful.

Natural-language trigger examples:

- "Use skill-atlas to find and orchestrate the best skills for this product."
- "为这个任务检索并编排技能，同时检查是否需要外部模型或软件连接器。"
- "我需要做 HMI UI/UX，请选一个主设计技能，再用其他技能复核。"

On platforms that expose skills as slash commands, invoke the platform's command for `skill-atlas` and include the request. Do not promise one universal slash-command syntax because platforms differ.

1. Choose the research depth and run the recommendation command. `balanced` is the default:

```bash
python3 <skill-root>/scripts/skill_atlas.py recommend product \
  "Describe the task, product, model question, or software workflow" \
  --mode balanced --search-mode hybrid
```

Add one or more `--root /path/to/skills` options when the user's platform stores skills elsewhere.

- `quick`: inspect local skills first and create external skill searches only for missing capabilities
- `balanced`: inspect local skills and create an external comparison plan for every required capability; target three public candidates per capability
- `benchmark`: perform the broadest comparison planning for every capability; target eight public candidates with deeper queries

With `--search-mode web|hybrid`, the unified CLI executes the selected search APIs and reports actual evidence under `external_search`. In default `local` scope it only plans. In `balanced` and `benchmark`, the remaining `external_comparison_plan` is work for the active Agent: search current public sources, inspect the candidate code, and score local and external candidates with the same 100-point rubric. Keep the recommendation status `provisional` until that work is complete. `provisional` means candidates are unverified and must not be presented as an adoption decision.

Every unified `recommend` or `orchestrate` invocation checks the reviewed public-market snapshot under `~/.local/share/skill-atlas`. Default freshness windows are 168 hours for `quick`, 24 hours for `balanced`, and zero for `benchmark`. `benchmark` and `--refresh` always set `market_refresh_required`. Skill Atlas cannot assume every Agent platform supports startup hooks; a platform startup task may run `market status`, but it must not perform a full market crawl automatically.

Reviewed candidates may include optional `roles`, `keywords`, and `platforms`. Roles use `research`, `design`, `discovery`, `planning`, `implementation`, `review`, or `verification`. A fresh matching snapshot produces `reviewed_market_matches` and an ordered `reviewed_orchestration`; these remain separate from local `use_now` entries. Always preserve both installation state and review freshness, and never execute an external entry marked `install-required` or `refresh-required`.

2. Return these sections when applicable:

- `Required Capabilities`: inferred work areas such as product planning, UI/UX, backend, storage, authentication, AI, testing, documents, deployment, or payments
- `Use Now`: relevant skills currently available in an agent-loadable root
- `Suggested Orchestration`: an ordered research, design, production, and verification stack with primary, support, and reviewer roles
- `Platform-Managed Matches`: useful plugin/cache matches that may be available only through their owning tool and must not be edited in place
- `External Search Gaps`: missing capabilities plus focused queries for public skill discovery
- `External Benchmark Plan`: local candidates, external search queries, candidate targets, and required checks for each capability
- `Comparison Rubric`: task fit 30, workflow quality 20, eval evidence 15, maintenance 10, source and license 10, compatibility 10, safety 5
- `Models, Tools, and Domain Research`: time-sensitive AI model comparisons, domain standards, application APIs, MCP connectors, plugins, or automation interfaces that are not themselves skills

3. Recommend a minimal stack. Prefer one primary production skill per capability. Add a complementary reviewer or verifier only when it checks a different quality dimension. Treat Slides, PPT agents, PowerPoint, Canva, and equivalent presentation generators as one mutually exclusive generator family: select one primary and list the others only as alternatives unless the user explicitly requests a comparison experiment. Require explicit task evidence before selecting narrow media tools such as Remotion or YouTube clipping; the mere presence of images, media, or a portfolio does not justify them.

4. Distinguish artifact types:

- a `skill` supplies agent instructions, workflows, scripts, or domain knowledge
- a `component-library` supplies executable project code and UI primitives; catalog its metadata and installation status, but never copy its source into Skill Atlas
- a `model` is a time-sensitive external capability that requires current benchmark, quality, license, cost, latency, and deployment research
- a `software integration` may require the actual desktop application, CLI, scripting API, plugin, MCP server, or computer-control capability
- a `domain reference` supplies standards and constraints that general creation skills may miss

5. For external gaps, use the local `search-skill` workflow when available, or search inspectable official and community sources directly. Treat the generated queries as a worklist, not as verified recommendations.

6. Before presenting an external skill as installable, verify its source, author or repository history, license, maintenance activity, platform compatibility, and strict security scan. Never install automatically.

## Public Market Freshness

Use `market status` as the lightweight startup check. It reads local metadata only and returns `missing`, `fresh`, or `stale` with `researched_at`, age, TTL, source coverage, and candidate count.

Use `market refresh --search-mode web` for executed public discovery; default `market refresh` still creates an offline research packet. A completed reviewed market snapshot must include at least one `marketplace`, one `official-or-github`, and one `community` source. Search-only results never renew reviewed freshness. After the Agent finishes current research and security review, save reviewed JSON with `market refresh --results FILE`.

Do not claim a cache is refreshed merely because a packet was generated. Only validated results produce a `completed` snapshot.

## External Discovery Workflow

Use this workflow when the user wants to compare local skills with public alternatives or find stronger versions of each skill category.

1. Execute focused public search and retain actual evidence:

```bash
python3 <skill-root>/scripts/skill_atlas.py discover similar ux --search-mode hybrid --web-limit 20
```

The older `discovery_brief.py` only generates offline briefs; it does not search.

2. Inspect returned candidates and expand with additional executed searches where coverage is insufficient. Prioritize primary or inspectable sources:

- GitHub repositories with visible `SKILL.md`
- official skill marketplaces/directories such as SkillsMP, SkillMD, Playbooks, and ClawHub
- official Codex, Claude Code, OpenCode, or plugin skill collections
- author pages with source links, license, install instructions, and update history

Use an available `search-skill` as a trusted-source policy reference. Do not assume its install path. Its source tiers are useful for high-confidence searches:

- Tier 1: official/high-trust sources such as `anthropics/skills` and `ComposioHQ/awesome-claude-skills`
- Tier 2: community-curated sources such as `travisvn/awesome-claude-skills` and `skills.sh`
- Tier 3: aggregators such as `skillsmp.com`, used with extra verification

For this skill's full-inventory discovery mode, do not limit searches to only those sources. Treat the `search-skill` tiers as priority ordering and safety heuristics, then expand to additional inspectable sources when needed.

3. Score candidates against the local skill:

- source trust: known author, repository history, license, install path
- content quality: trigger clarity, procedural depth, examples, references, scripts/assets
- maintenance: recent updates, version tags, issue activity, compatibility notes
- fit: whether it replaces the local skill, complements it, or should only be used as inspiration
- safety: no hidden destructive instructions, no unreviewed shell install, no credential exfiltration

4. Run strict static security review before recommending install, update, or promotion:

```bash
python3 <skill-root>/scripts/security_review_skills.py --path /path/to/candidate-skill --format markdown
python3 <skill-root>/scripts/security_review_skills.py --path /path/to/candidate-skill --strict --format markdown
```

Use the verdicts this way:

- `safe`: no static findings from the current rules; still review source and license.
- `review-needed`: do not install automatically; inspect findings and explain the tradeoff.
- `unsafe`: do not install or update from this candidate unless the user explicitly accepts a written risk plan.

Default mode suppresses ordinary Markdown-only links and badges so README references do not swamp the review. `--strict` also reports those links. Both modes still report executable network loads, remote shell execution, destructive commands, config tampering, credential references, prompt-injection language, and automatic dependency installs.

5. Protect user-developed skills:

- If a skill appears to be user-developed or locally evolved, never label an external candidate as a replacement.
- For user-developed skills, report external findings as competitors, comparable products, references, or ideas to borrow.
- Keep the local skill as the canonical artifact for continued iteration unless the user explicitly says otherwise.

6. Report in four buckets:

- `upgrade candidate`: likely better than the local skill after review
- `complement`: useful ideas or references, but not a direct replacement
- `competitor/reference`: similar external work for a user-developed skill; do not replace
- `skip`: low trust, stale, vague, unsafe, or not meaningfully better

7. Do not install or replace anything from the web without explicit user confirmation.

## Command Compatibility

Legacy shorthand remains valid: `manage` defaults to `manage scan`; `discover QUERY` defaults to `discover similar QUERY`; `recommend REQUEST` defaults to `recommend task REQUEST`; and `orchestrate REQUEST` defaults to `orchestrate plan REQUEST`.

## Skill Atlas Self-Update

Use `manage self` for Skill Atlas itself, not for third-party skills. Its default update policy is `notify`: it checks and plans but never silently replaces the installed copy.

- `manage self status` reports the installed version, channel, policy, package hash, and whether a release source is configured.
- `manage self status --source PATH` validates a local release directory or archive and reports its version, hash, and strict security verdict.
- `manage self update --source PATH` produces the same read-only plan. Applying it requires both `--apply` and `--confirm`.
- `manage self rollback` lists managed backups. Restoring one requires `--backup PATH --apply --confirm`.

Archive candidates also require `--checksum SHA256`. The updater rejects path traversal, links, missing or mismatched identity metadata, checksum failures, same-version or older update candidates, and any strict security verdict other than `safe`.

An applied update stages a reviewed copy in the installation's parent directory, renames the current installation into a managed backup, and atomically promotes the staged copy. If promotion fails, it restores the previous installation. Rollback uses the same mechanism and creates a recovery backup of the version being replaced.

The public release source is declared in `skill.json`. When `repository` is unset, report `source-not-configured`; do not invent a GitHub update result. Local directories and checksum-verified archives are supported now. Network release fetching may be added only after the repository and release verification contract are published.

For lower-level helpers, alternate output formats, or debugging, read [docs/cli-reference.md](docs/cli-reference.md).

## Security Review Rules

Static security review looks for:

- sensitive paths and secrets: `.env`, SSH keys, cloud credentials, keychains, tokens
- destructive shell: forced recursive deletion, broad permission changes, shell profile persistence
- remote code execution: `curl | sh`, dynamic `eval`/`exec`, encoded payloads
- agent or MCP config tampering
- prompt injection language that asks agents to ignore system/developer instructions or exfiltrate data <!-- security-review: allow documented rule description -->
- unknown external network locations
- automatic dependency installation

The scanner reports `context` and `confidence` for each finding. Treat findings in executable scripts or Markdown code blocks as higher risk than ordinary prose. A line may include `security-review: allow` only after manual review confirms the match is documentation or a deliberate benign reference.

Static review is a gate, not a guarantee. A `safe` result means no current rule matched; it does not prove the skill is safe. Never install, update, promote, or symlink a third-party skill solely because the static scan is clean; also check source history, license, author trust, upstream URL, diff, and rollback plan.

Optional OpenCode legacy manager commands:

```bash
python3 <skill-root>/scripts/opencode_skill_manager.py list
python3 <skill-root>/scripts/opencode_skill_manager.py show <skill-name>
python3 <skill-root>/scripts/opencode_skill_manager.py init <skill-name>
python3 <skill-root>/scripts/opencode_skill_manager.py set-upstream <skill-name> <raw-skill-md-url>
python3 <skill-root>/scripts/opencode_skill_manager.py update <skill-name>
python3 <skill-root>/scripts/opencode_skill_manager.py apply-evolution <skill-name>
python3 <skill-root>/scripts/opencode_skill_manager.py rollback <skill-name> <archive-filename>
```

## Upstream Discovery

The script only treats these as machine-readable upstream evidence:

- `evolution.json` with `upstream.raw_skill_md_url`
- `skill.json`, `.skill-source.json`, or `source.json` with `raw_skill_md_url`, `url`, `source`, `upstream`, or `repo`
- comments or text in `SKILL.md` containing a GitHub raw `SKILL.md` URL

Free-form README links or vague repo mentions are hints, not update authority. Report them as notes, not as safe update sources.

## External-Maintained Skills

Use this category for skills pulled directly from GitHub or another author-maintained source, such as a public PPT/slide skill maintained by its original author.

For these skills:

- Preserve the author's upstream URL in `evolution.json`, `skill.json`, `.skill-source.json`, or `source.json`.
- Prefer one user-controlled canonical directory for the skill.
- Expose the canonical directory to Codex, OpenCode, Claude Code, and other agents with symlinks only after confirming each platform can load that layout.
- Check upstream with `audit_skills.py --check-upstream`; if it differs, show the upstream URL, local path, backup path, and rollback method before updating.
- Do not treat external-maintained skills as competitors to the user's self-authored skills. They are maintained dependencies.
- Do not edit plugin-cache copies directly; install or mirror into a user-controlled canonical directory first.

## OpenCode Evolution Workflow

Use `scripts/opencode_skill_manager.py` only when the user explicitly asks to manage OpenCode skills in `~/.config/opencode/skills`. Do not treat it as the main update mechanism for Codex, Claude, Agents, plugin-cache, or other platform roots.

This compatibility script preserves the old local layout:

- `SKILL.upstream.md`: upstream baseline
- `archive/`: last 5 upstream baselines
- `evolution.json`: user-owned local lessons/preferences/notes
- `SKILL.md`: generated final skill, upstream plus local evolution

Before running `update`, make sure the target skill has a recorded `evolution.json` upstream URL and tell the user which files will change.

## Safety Rules

- Never overwrite `SKILL.md` during audit.
- Never apply installation without both `--apply` and `--confirm`; refuse all conflicts before creating the canonical copy or any link.
- Never delete duplicate skills during audit.
- Never assume one platform's installed skill is usable by another platform unless it is under that platform's configured root or symlinked there.
- Prefer symlinks or one canonical source when the user wants to share one skill across Codex, OpenCode, and Claude.
- Before any update, preserve the previous file or directory and state the rollback path.
- Never describe Skill Atlas self-update as automatic or unattended. Its default policy is notification, and write operations require `--apply --confirm`.


## Integrated Closeout and task continuity

The bundled `closeout/SKILL.md` is the authoritative Closeout procedure.
Use the Closeout six-plane verification and permission rules for project
reconciliation, release evidence, and project cleanup. The bundled skill
must not silently delete branches, deployments, user data, or memory.

For task continuity use the platform-neutral commands in
`scripts/skill_atlas.py`:

- `checkpoint`: save a task-scoped Git evidence snapshot after a meaningful milestone.
- `handoff`: record what was completed, what remains, and the next safe action.
- `resume`: perform read-only verification before accepting a handoff.
- `closeout audit`: run bundled read-only project inventory.
- `closeout evals`: validate bundled Closeout evaluation cases.

Read `docs/multi-agent-development.md` and the project's own `AGENTS.md`,
`CLAUDE.md`, issue, and architectural decisions. Never treat a checkpoint as
proof a test ran. Never overwrite a dirty working tree or auto-push merely
to prepare a handoff. The receiving agent must inspect relevant code and
run appropriate tests. Token exhaustion can interrupt any Agent before
its next checkpoint, so state recovery also requires direct Git inspection.

Keep the Skill Atlas discovery and recommendation features first-class:
`discover`, `recommend`, and `orchestrate` must continue to work without
Closeout or a state file present. Do not automatically install skills or
switch external models without the appropriate access and authorization.


## Optional Skill Development Kit integration

Use `create plan` when a requested new Skill requires creation rather than
installing a public candidate. It selects a method from the independently
maintained `skill-development-kit`: `skill-from-github`,
`skill-from-masters`, or `skill-from-notebook`. Use `--kit-root` to
verify an actual local checkout; `plan-only` does not mean an external
Skill has executed. Never copy the Kit into Skill Atlas, silently install
its content, or bypass Atlas's security reviews.


## Kimi Code CLI support

Current Kimi Code CLI natively discovers `~/.agents/skills/`, so it can use
the shared canonical Skill Atlas installation without duplicating copies in
Kimi-specific skill directories. The optional installer recognizes
`--platform kimi` and records the native-discovery route. Kimi invokes
Skills through `/skill:skill-atlas` and `/skill:closeout`.

See [docs/kimi-code.md](docs/kimi-code.md). Validate Kimi's own `AGENTS.md`
loading, version, skill catalog, and `checkpoint/handoff/resume` on a real
disposable repository before claiming live platform support. Its documented
hooks, `kimi -p`, and ACP do not establish automatic rate-limit failover.


## Model-Aware Handoff recommendation

For requests to select a model or Agent before passing an existing task,
use the read-only `handoff advise` command with the project root, task ID,
and a reviewed local Model/Agent registry. First inspect the saved task
`next_action` and actual Git status. Distinguish declared capabilities from
measured outcomes and live provider availability. Do not fabricate provider
access, recent performance, API costs or a permanent model ranking.

An evidence-backed recommendation is only a suggestion; execution requires
separate approval and currently supported tools. Read
`docs/model-aware-handoff.md` for the contract.


## Feedback Loop

When a user reports a Skill Atlas failure, prepare a sanitized local
Issue draft and preview it before seeking write permission. Manual
GitHub submission requires explicit user authorization. The only
automatic exception is the scoped, opt-in CI failure reporting workflow
for the Skill Atlas repository itself. Do not upload project files,
credentials, logs, or private conversation histories. See
docs/feedback-loop.md.
