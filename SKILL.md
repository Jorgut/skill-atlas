---
name: skill-atlas
description: Audit, discover, recommend, orchestrate, and safely manage agent skills across Codex, OpenCode, Claude-style agents, plugin caches, and configurable skill roots. Use when the user wants to inventory installed skills, detect duplicates or symlinks, check upstream freshness, compare public alternatives, review third-party skill safety, plan cross-platform consolidation, describe a product or professional task and ask which skills should be combined, compare current AI models for a workflow, or find skills and connectors for software such as design, HMI, animation, CAD, and 3D modeling tools. The skill is platform-neutral and local-first. It reports and recommends before acting; it must not overwrite, delete, symlink, install, or upgrade skills without explicit confirmation.
---

# Skill Atlas

Use this cross-platform skill manager to inventory an agent-skill ecosystem, track updates, discover alternatives, recommend skill stacks, and orchestrate skills with models and software connectors. It is read-only by default.

Treat `scripts/audit_skills.py` as the primary, platform-neutral entry point. Use `scripts/opencode_skill_manager.py` only as a compatibility helper when the user explicitly asks for the older OpenCode upstream/evolution workflow.

Do not assume that a published user's machine has any particular platform, directory, skill count, duplicate, or symlink layout. Default roots are discovery conventions only. Treat every inventory result as runtime evidence, and accept repeated `--root` arguments for custom platforms or canonical stores.

Choose the workflow from the request:

- inventory, duplicates, updates, symlinks, or consolidation: run the audit workflow
- a product idea, professional task, model question, or software workflow with uncertainty about which capabilities to use: run recommendation and orchestration
- stronger alternatives or competitors for installed skills: run external discovery
- a downloaded or proposed third-party skill: run strict security review

## Commands

Treat this command tree as stable across Agent platforms:

```text
skill-atlas
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
└── orchestrate
    ├── plan       build an ordered multi-skill workflow
    ├── validate   check role overlap, duplication, and capability gaps
    └── run        stage an execution plan and wait for explicit confirmation
```

Commands are read-only by default. `manage update`, `manage sync`, and `orchestrate run` always produce plans only. `manage self update` and `manage self rollback` may modify the Skill Atlas installation only when the user supplies both `--apply` and `--confirm` after reviewing the exact source or backup. Never install, overwrite, delete, symlink, update, or execute external actions without that explicit confirmation.

Agent command syntax varies. If a platform does not pass arguments after `$skill-atlas` or does not support dollar-prefixed skill calls, accept equivalent natural language such as "Use Skill Atlas manage" or "用 Skill Atlas 编排这个任务". Preserve the four command meanings across platforms.

Use the deterministic CLI when direct script execution is appropriate:

```bash
python3 <skill-root>/scripts/skill_atlas.py manage
python3 <skill-root>/scripts/skill_atlas.py manage status
python3 <skill-root>/scripts/skill_atlas.py manage self status
python3 <skill-root>/scripts/skill_atlas.py discover competitors ux-audit
python3 <skill-root>/scripts/skill_atlas.py recommend product "Design an automotive HMI"
python3 <skill-root>/scripts/skill_atlas.py recommend model "Product animation"
python3 <skill-root>/scripts/skill_atlas.py orchestrate validate "Create product animation"
```

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

1. Run the local-first recommendation command:

```bash
python3 <skill-root>/scripts/recommend_skills.py --request "Describe the task, product, model question, or software workflow" --format markdown
```

Add one or more `--root /path/to/skills` options when the user's platform stores skills elsewhere.

2. Return these sections when applicable:

- `Required Capabilities`: inferred work areas such as product planning, UI/UX, backend, storage, authentication, AI, testing, documents, deployment, or payments
- `Use Now`: relevant skills currently available in an agent-loadable root
- `Suggested Orchestration`: an ordered research, design, production, and verification stack with primary, support, and reviewer roles
- `Platform-Managed Matches`: useful plugin/cache matches that may be available only through their owning tool and must not be edited in place
- `External Search Gaps`: missing capabilities plus focused queries for public skill discovery
- `Models, Tools, and Domain Research`: time-sensitive AI model comparisons, domain standards, application APIs, MCP connectors, plugins, or automation interfaces that are not themselves skills

3. Recommend a minimal stack. Prefer one primary production skill per capability. Add a complementary reviewer or verifier only when it checks a different quality dimension. Do not run two overlapping generator skills as equal primaries without explaining how their outputs will be compared or merged.

4. Distinguish artifact types:

- a `skill` supplies agent instructions, workflows, scripts, or domain knowledge
- a `model` is a time-sensitive external capability that requires current benchmark, quality, license, cost, latency, and deployment research
- a `software integration` may require the actual desktop application, CLI, scripting API, plugin, MCP server, or computer-control capability
- a `domain reference` supplies standards and constraints that general creation skills may miss

5. For external gaps, use the local `search-skill` workflow when available, or search inspectable official and community sources directly. Treat the generated queries as a worklist, not as verified recommendations.

6. Before presenting an external skill as installable, verify its source, author or repository history, license, maintenance activity, platform compatibility, and strict security scan. Never install automatically.

Example:

```bash
python3 <skill-root>/scripts/recommend_skills.py \
  --request "AI presentation app with document upload, web slides, PDF export, accounts, and deployment"
```

```bash
python3 <skill-root>/scripts/recommend_skills.py \
  --request "Compare current AI models for product animation and orchestrate research, production, and review skills"
```

```bash
python3 <skill-root>/scripts/recommend_skills.py \
  --request "Design an automotive HMI UI/UX system and combine primary design with independent UX validation"
```

```bash
python3 <skill-root>/scripts/recommend_skills.py \
  --request "Find skills and software integrations for an architect using Rhino, Grasshopper, Blender, or SketchUp"
```

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

## Useful Commands

Unified entry point:

```bash
python3 <skill-root>/scripts/skill_atlas.py manage --format markdown
python3 <skill-root>/scripts/skill_atlas.py manage status --check-upstream
python3 <skill-root>/scripts/skill_atlas.py manage dedupe
python3 <skill-root>/scripts/skill_atlas.py manage self status
python3 <skill-root>/scripts/skill_atlas.py manage self update --source /path/to/reviewed-release
python3 <skill-root>/scripts/skill_atlas.py manage self rollback
python3 <skill-root>/scripts/skill_atlas.py discover alternatives ux
python3 <skill-root>/scripts/skill_atlas.py recommend task "A concise task description"
python3 <skill-root>/scripts/skill_atlas.py recommend tool "Rhino and Blender automation"
python3 <skill-root>/scripts/skill_atlas.py orchestrate plan "A concise task description"
python3 <skill-root>/scripts/skill_atlas.py orchestrate validate "A concise task description"
```

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

The component commands below remain available for automation and debugging.

Markdown summary:

```bash
python3 <skill-root>/scripts/audit_skills.py --format markdown
```

Machine-readable JSON:

```bash
python3 <skill-root>/scripts/audit_skills.py --format json
```

Recommend skills for a product:

```bash
python3 <skill-root>/scripts/recommend_skills.py --request "A concise task or product description" --format markdown
python3 <skill-root>/scripts/recommend_skills.py --request "A concise task or product description" --format json
python3 <skill-root>/scripts/recommend_skills.py --request "A concise task or product description" --root /custom/skills
```

`--product` remains a compatibility alias for older callers.

Full TSV inventory:

```bash
python3 <skill-root>/scripts/audit_skills.py --format tsv
```

Check recorded upstream URLs. This requires network permission in sandboxed environments:

```bash
python3 <skill-root>/scripts/audit_skills.py --check-upstream --format markdown
```

Scan a custom root:

```bash
python3 <skill-root>/scripts/audit_skills.py --root /path/to/search --format markdown
```

Generate external discovery briefs:

```bash
python3 <skill-root>/scripts/discovery_brief.py --format markdown
python3 <skill-root>/scripts/discovery_brief.py --focus ux --limit 20
python3 <skill-root>/scripts/discovery_brief.py --format json
```

Generate full external discovery batches:

```bash
python3 <skill-root>/scripts/make_discovery_batches.py --format markdown --batch-size 25
python3 <skill-root>/scripts/make_discovery_batches.py --format json --batch-size 25
```

Run static security review:

```bash
python3 <skill-root>/scripts/security_review_skills.py --path /path/to/skill --format markdown
python3 <skill-root>/scripts/security_review_skills.py --path /path/to/skill --format json
python3 <skill-root>/scripts/security_review_skills.py --path /path/to/skill --strict --format markdown
```

Review default local user skill roots:

```bash
python3 <skill-root>/scripts/security_review_skills.py --format markdown
```

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
- Never delete duplicate skills during audit.
- Never assume one platform's installed skill is usable by another platform unless it is under that platform's configured root or symlinked there.
- Prefer symlinks or one canonical source when the user wants to share one skill across Codex, OpenCode, and Claude.
- Before any update, preserve the previous file or directory and state the rollback path.
- Never describe Skill Atlas self-update as automatic or unattended. Its default policy is notification, and write operations require `--apply --confirm`.
