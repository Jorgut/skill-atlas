# Skill Atlas

[![skills.sh](https://img.shields.io/badge/skills.sh-Jorgut/skill--atlas-8A2BE2?style=flat-square)](https://skills.sh/Jorgut/skill-atlas)
[![Install with npx](https://img.shields.io/badge/npx%20skills%20add-Jorgut%2Fskill--atlas-000?style=flat-square)](https://github.com/Jorgut/skill-atlas)
![License](https://img.shields.io/github/license/Jorgut/skill-atlas?style=flat-square)
![Agent Skill](https://img.shields.io/badge/Agent%20Skill-Skill%20Manager-111111?style=flat-square)

Skill Atlas is a local-aware, cross-platform manager for agent skills. It inventories installed skills, detects duplicates and symlinks, plans updates and consolidation, discovers alternatives and competitors, recommends skill stacks for products and professional workflows, and validates multi-skill orchestration.

It supports Codex, OpenCode, Claude Code, shared `~/.agents/skills` installations, plugin caches, and custom skill roots. Read-only planning is the default.

Beginner guides: [中文](docs/GETTING_STARTED.zh-CN.md) | [English](docs/GETTING_STARTED.en.md) | [Русский](docs/GETTING_STARTED.ru.md)

> [!IMPORTANT]
> Copying the Skill Atlas folder into a skill directory only installs the skill. It does **not** register `/skill-atlas`. Use the installer with `--commands` to register command adapters on platforms that support Markdown slash commands.

## Install

### Quick install (recommended)

```bash
npx skills add Jorgut/skill-atlas
```

### Manual install

Requirements: Git and Python 3.10 or newer.

```bash
git clone https://github.com/Jorgut/skill-atlas.git
cd skill-atlas
```

First preview every copy and symlink operation. This command does not change anything:

```bash
python3 scripts/skill_atlas.py install --all-platforms --commands
```

After reviewing the destinations, apply the same plan explicitly:

```bash
python3 scripts/skill_atlas.py install --all-platforms --commands --apply --confirm
```

Restart the installed Agent applications after installation so they reload their skill and command indexes.

To install for only selected platforms, repeat `--platform`:

```bash
python3 scripts/skill_atlas.py install \
  --platform codex \
  --platform opencode \
  --commands
```

## Platform Behavior

| Platform | Skill path | Command adapter | Invoke after installation |
| --- | --- | --- | --- |
| Codex | `~/.codex/skills/skill-atlas` | Not applicable | `$skill-atlas` or natural language |
| OpenCode | `~/.config/opencode/skills/skill-atlas` | `~/.config/opencode/commands/skill-atlas.md` | `/skill-atlas` |
| Claude Code | `~/.claude/skills/skill-atlas` | `~/.claude/commands/skill-atlas.md` | `/skill-atlas` |

The installer keeps one canonical copy at `~/.agents/skills/skill-atlas` and links each selected platform to it. This avoids maintaining separate physical copies while preserving each platform's expected discovery path.

Codex does not use the bundled Markdown slash-command adapter. In Codex, invoke the installed skill as `$skill-atlas` or ask in natural language, for example: `Use Skill Atlas to recommend skills for an automotive HMI project.`

## What It Does

Skill Atlas exposes six main workflows:

| Workflow | Purpose | Example |
| --- | --- | --- |
| `manage` | Scan skills, inspect update evidence, find duplicates, and plan shared-directory consolidation | `manage status --check-upstream` |
| `discover` | Find similar skills, alternatives, capability gaps, or competitors for user-authored skills | `discover competitors ux-audit` |
| `recommend` | Recommend skills, models, tools, plugins, MCP servers, and software integrations for a task | `recommend tool "Rhino and Blender automation"` |
| `orchestrate` | Build and validate an ordered multi-skill workflow | `orchestrate validate "Design an automotive HMI"` |
| `market` | Check public-market freshness or record a reviewed shared snapshot | `market status` |
| `monitor` | Schedule recurring competitor research and compare completed snapshots | `monitor add closeout --interval monthly` |

Examples using the deterministic CLI:

```bash
python3 scripts/skill_atlas.py manage
python3 scripts/skill_atlas.py manage status --check-upstream
python3 scripts/skill_atlas.py discover competitors ux-audit
python3 scripts/skill_atlas.py recommend product "Build a product animation platform" --mode balanced
python3 scripts/skill_atlas.py recommend tool "Rhino, Grasshopper, Blender, and SketchUp" --mode benchmark
python3 scripts/skill_atlas.py orchestrate validate "Design an automotive HMI" --mode balanced
python3 scripts/skill_atlas.py market status
python3 scripts/skill_atlas.py market refresh --category ui-ux
python3 scripts/skill_atlas.py monitor add closeout --interval monthly
python3 scripts/skill_atlas.py monitor due
```

With `/skill-atlas` or `$skill-atlas`, the rest of the line is the request. Natural-language requests are also supported:

```text
/skill-atlas recommend the best local and public skills for product animation
$skill-atlas find Rhino and Blender skills, connectors, and missing capabilities
Use Skill Atlas to compare my UX skill with public competitors without replacing mine.
```

## Recommendation Modes

`recommend` and `orchestrate` accept the same `--mode` option:

| Mode | Behavior | Best for |
| --- | --- | --- |
| `quick` | Uses installed skills first and creates public-skill searches only for missing capabilities | Fast local planning |
| `balanced` | Default. Compares every required capability against three public candidates, even when a local match exists | Normal product decisions |
| `benchmark` | Expands every capability to eight candidates and deeper eval, maintenance, license, compatibility, and security queries | High-stakes selection |

Local and public candidates use one 100-point rubric: task fit 30, workflow quality 20, eval evidence 15, maintenance 10, source and license 10, compatibility 10, and safety 5.

The deterministic CLI creates an external research worklist; it does not browse the web by itself. A `provisional` result means the Agent must execute those searches, inspect sources, and score the candidates before claiming the comparison is complete.

Every `recommend` and `orchestrate` invocation checks the reviewed market snapshot. Default TTLs are seven days for `quick`, 24 hours for `balanced`, and zero for `benchmark`. `benchmark` and `--refresh` always require current research.

## Public Market Cache

Use this as a lightweight startup check; it never accesses the network:

```bash
python3 scripts/skill_atlas.py market status
```

When the snapshot is missing or stale, generate a category-specific research packet:

```bash
python3 scripts/skill_atlas.py market refresh --category ui-ux
```

The active Agent must then research and review the candidates. Completed results require at least one marketplace source, one official or GitHub source, and one maintained community source:

```json
{
  "summary": "Current reviewed market snapshot",
  "sources": [
    {"name": "skills.sh", "type": "marketplace", "url": "https://skills.sh"},
    {"name": "GitHub", "type": "official-or-github", "url": "https://github.com"},
    {"name": "Community list", "type": "community", "url": "https://github.com/example/awesome-skills"}
  ],
  "candidates": [
    {
      "name": "Candidate",
      "artifact_type": "skill",
      "url": "https://github.com/example/candidate",
      "capabilities": ["design-ux"],
      "roles": ["design", "review"],
      "keywords": ["react", "hmi"],
      "platforms": ["codex", "opencode", "claude"],
      "score": 91
    }
  ]
}
```

Save reviewed results with `market refresh --results results.json`. Generating a packet alone remains `research-required` and never updates the freshness timestamp. Skill Atlas does not install a universal startup hook because Agent platforms differ; platform automation may run `market status`, while full research stays TTL-driven or explicit.

### Reuse Reviewed Skills in an Orchestration

Candidate metadata can assign an `artifact_type`: `skill` (the backward-compatible default), `component-library`, `model`, `software-integration`, or `domain-reference`. Component libraries remain executable project dependencies and are never copied into Skill Atlas. Candidate roles use `research`, `design`, `discovery`, `planning`, `implementation`, `review`, and `verification`. `keywords` prevent a general capability match from recommending a domain-specific artifact for the wrong product. An optional `score` from 0 to 100 ranks candidates reviewed with the shared rubric; the highest-scored non-duplicate candidate wins each role.

For a React interaction workflow, save reviewed entries such as React Bits' `apple-design`, `find-animation-opportunities`, `improve-animations`, and `review-animations`, plus a reviewed implementation skill such as `motion-dev-animations`. Then run:

```bash
python3 scripts/skill_atlas.py orchestrate plan \
  "Build an interactive React interface with React Bits, motion, accessibility, and performance" \
  --mode balanced
```

Scan a local component repository only when the user supplies its scope:

```bash
python3 scripts/skill_atlas.py orchestrate plan \
  "Build a React liquid glass interface" \
  --component-root /path/to/liquid-glass-design
```

The root may be a repository containing `component-library.json` or the manifest itself. Skill Atlas does not crawl the entire machine for package manifests.

The result keeps three facts separate:

- `use_now`: locally installed and loadable skills
- `reviewed_market_matches`: relevant typed artifacts from the saved market snapshot
- `reviewed_orchestration`: one selected artifact per ordered role, with overlapping candidates listed as alternatives

`installed` means a Skill name was found locally. `install-required` applies to a missing Skill, while `dependency-required` applies to a component library that must be added to the target project. `refresh-required` means the saved research is outside the selected freshness policy and must be checked again.

## Recurring Competitor Comparisons

Create a monitor once:

```bash
python3 scripts/skill_atlas.py monitor add closeout --interval monthly
```

Check what is due and generate the next research packet:

```bash
python3 scripts/skill_atlas.py monitor due
python3 scripts/skill_atlas.py monitor run closeout
```

`monitor run` without `--results` records a `research-required` snapshot and remains due. It does not claim that web research happened or advance the schedule. An Agent or approved automation should execute the packet's searches, source checks, license review, maintenance review, compatibility checks, and strict security review, then save:

```json
{
  "summary": "What changed and why it matters",
  "candidates": [
    {"name": "Candidate", "url": "https://github.com/example/candidate"}
  ]
}
```

Record the completed comparison and calculate additions/removals against the previous completed snapshot:

```bash
python3 scripts/skill_atlas.py monitor run closeout --results results.json
python3 scripts/skill_atlas.py monitor history closeout
```

Schedules and snapshots default to `~/.local/share/skill-atlas`. Skill Atlas does not keep a hidden background process. Use Codex Automation, OpenCode automation, `cron`, or `launchd` to invoke `monitor due` and the Agent-assisted comparison workflow periodically.

## Safety Model

- Installation is a dry run unless both `--apply` and `--confirm` are present.
- All destination conflicts are detected before any mutation begins.
- Existing paths are never overwritten.
- Failed installation rolls back links and a newly created canonical copy.
- Repeating a successful installation is idempotent and reports `already-installed`.
- Audits, deduplication, third-party updates, discovery, and orchestration remain plans by default.
- Third-party candidates require source, maintenance, license, compatibility, diff, and strict static security review before installation is recommended.
- User-authored skills are never replaced by discovered competitors.

A clean static scan is a gate, not proof that third-party code is safe. Review source history and runtime permissions before installing any external skill.

## Updating Skill Atlas

Skill Atlas does not silently update itself. Version `0.6.2-beta` supports reviewed local release directories and checksum-verified archives.

Inspect the current installation:

```bash
python3 scripts/skill_atlas.py manage self status
```

Preview a reviewed release candidate:

```bash
python3 scripts/skill_atlas.py manage self update --source /path/to/reviewed-release
```

Apply only after reviewing the candidate and security verdict:

```bash
python3 scripts/skill_atlas.py manage self update \
  --source /path/to/reviewed-release \
  --apply \
  --confirm
```

List backups or restore one:

```bash
python3 scripts/skill_atlas.py manage self rollback
python3 scripts/skill_atlas.py manage self rollback \
  --backup /path/to/managed-backup \
  --apply \
  --confirm
```

Archive candidates also require `--checksum SHA256`. Network release fetching and unattended GitHub updates are not part of this beta release.

## Development

Run the focused installer tests:

```bash
python3 -m unittest discover -s tests -v
```

See [`SKILL.md`](SKILL.md) for the complete agent workflow, ownership rules, discovery policy, security gates, and CLI reference.

## Status

Skill Atlas is currently `0.6.2-beta`. Interfaces and platform adapters may change before the stable release.
