---
name: skill-atlas
description: "Manage agent skills across platforms: inventory, duplicates, upstream evidence, safe updates, public alternatives, task/model/tool recommendations, and multi-skill orchestration. Use also to configure shared rules, per-project context, and cross-agent handoff. Read-only by default; apply changes only within explicit user authorization."
---

# Skill Atlas

Use this cross-platform skill manager to inventory an agent-skill ecosystem, track updates, discover alternatives, recommend skill stacks, and orchestrate skills with models and software connectors. It is read-only by default.

Treat `scripts/audit_skills.py` as the primary, platform-neutral entry point. Use `scripts/opencode_skill_manager.py` only as a compatibility helper when the user explicitly asks for the older OpenCode upstream/evolution workflow.

Do not assume that a published user's machine has any particular platform, directory, skill count, duplicate, or symlink layout. Default roots are discovery conventions only. Treat every inventory result as runtime evidence, and accept repeated `--root` arguments for custom platforms or canonical stores.

Choose the workflow from the request:

- inventory, duplicates, updates, symlinks, or consolidation: run the audit workflow
- a product idea, professional task, model question, or software workflow with uncertainty about which capabilities to use: run recommendation and orchestration
- stronger alternatives or competitors for installed skills: run external discovery
- public-market freshness or a reviewed shared market snapshot: run market
- recurring competitor comparison with historical differences: run monitor
- cross-agent rules, project context, or handoff setup: read the cross-agent context workflow below
- a downloaded or proposed third-party skill: run strict security review

## Cross-Agent Context and Handoff

When asked to connect agent tools, organize per-project memory, or verify shared context, read [docs/cross-agent-collaboration.md](docs/cross-agent-collaboration.md). Discover each tool's actual instruction entry, reuse existing project state, and distinguish configured files from verified loading and handoff. Rule-entry setup is agent-led; the optional task checkpoint CLI is described under Integrated Closeout and task continuity. Apply setup changes only within the user's authorized scope and preserve backups and concurrent work.

For WorkBuddy setup, read the WorkBuddy adapter discovery section in that guide; verify its effective rules root, project-guidance precedence, account scope, and loading conditions.

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
└── monitor
    ├── add        create a daily, weekly, monthly, or quarterly monitor
    ├── list       list monitor configurations
    ├── status     inspect one schedule and its snapshot count
    ├── due        list comparisons whose next run is due
    ├── run        create a research packet or record reviewed results
    ├── history    compare saved snapshots over time
    └── remove     remove configuration while retaining snapshots
```

Commands are read-only by default. `install` previews its exact copy and link operations unless the user supplies both `--apply` and `--confirm`. `manage update`, `manage sync`, and `orchestrate run` always produce plans only. `manage self update` and `manage self rollback` may modify the Skill Atlas installation only when the user supplies both `--apply` and `--confirm` after reviewing the exact source or backup. Never install, overwrite, delete, symlink, update, or execute external actions without that explicit confirmation.

Agent command syntax varies. If a platform does not pass arguments after `$skill-atlas` or does not support dollar-prefixed skill calls, accept equivalent natural language such as "Use Skill Atlas manage" or "用 Skill Atlas 编排这个任务". Preserve the six command meanings across platforms.

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
  --mode balanced
```

Add one or more `--root /path/to/skills` options when the user's platform stores skills elsewhere.

- `quick`: inspect local skills first and create external skill searches only for missing capabilities
- `balanced`: inspect local skills and create an external comparison plan for every required capability; target three public candidates per capability
- `benchmark`: perform the broadest comparison planning for every capability; target eight public candidates with deeper queries

The deterministic CLI does not browse the internet. In `balanced` and `benchmark`, treat `external_comparison_plan` as work for the active Agent: search current public sources, inspect the candidate code, and score local and external candidates with the same 100-point rubric. Keep the recommendation status `provisional` until that work is complete. `provisional` means candidates are unverified and must not be presented as an adoption decision.

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

Use `market refresh` to create a research packet. A completed market snapshot must include at least one `marketplace`, one `official-or-github`, and one `community` source. The command does not browse by itself. After the Agent finishes current research and security review, save reviewed JSON with `market refresh --results FILE`.

Do not claim a cache is refreshed merely because a packet was generated. Only validated results produce a `completed` snapshot.

## External Discovery Workflow

Use this workflow when the user wants to compare local skills with public alternatives or find stronger versions of each skill category.

1. Generate focused discovery briefs:

```bash
python3 <skill-root>/scripts/discovery_brief.py --focus ux --limit 20
```

2. Search the web for each relevant brief. Prioritize primary or inspectable sources:

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
