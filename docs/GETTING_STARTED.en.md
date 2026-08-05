# Skill Atlas Beginner Guide

[中文](GETTING_STARTED.zh-CN.md) | **English** | [Русский](GETTING_STARTED.ru.md)

This guide is for people who are new to Agent Skills, symbolic links, or command-line tools. Follow the sections in order.

## 1. What Skill Atlas Does

| Goal | Command |
| --- | --- |
| List installed skills | `manage scan` |
| Check updates, duplicates, and links | `manage status`, `manage dedupe`, `manage sync` |
| Find competitors for your own skill | `discover competitors` |
| Choose skills for a product or task | `recommend product` or `recommend task` |
| Combine skills into a workflow | `orchestrate plan` or `orchestrate validate` |
| Check public-market freshness | `market status` or `market refresh` |
| Repeat competitor research periodically | `monitor` |

Skill Atlas is read-only by default. It does not silently install, delete, update, or replace skills.

## 2. Install

Open a terminal and run:

```bash
git clone https://github.com/Jorgut/skill-atlas.git
cd skill-atlas
python3 scripts/skill_atlas.py install --all-platforms --commands
```

The last command is only a preview. If the destinations look correct and no conflict is reported, apply the installation:

```bash
python3 scripts/skill_atlas.py install \
  --all-platforms \
  --commands \
  --apply \
  --confirm
```

Fully quit and reopen Codex, OpenCode, or Claude Code after installation.

### What the Installer Creates

- One canonical copy at `~/.agents/skills/skill-atlas`
- Symbolic links from each selected Agent platform to that copy
- `/skill-atlas` command adapters for OpenCode and Claude Code
- No custom slash command for Codex; Codex uses `$skill-atlas`

## 3. First Use

### Codex

Enter this in the chat box:

```text
$skill-atlas manage scan
```

Natural language also works:

```text
Use Skill Atlas to scan all local skills and identify duplicates and symbolic links.
```

### OpenCode or Claude Code

```text
/skill-atlas manage scan
```

If the slash command is not visible, use natural language and check the troubleshooting section.

### Terminal

```bash
python3 ~/.agents/skills/skill-atlas/scripts/skill_atlas.py manage scan
```

## 4. Common Workflows

### Check Updates and Duplicates

```text
$skill-atlas manage status
$skill-atlas manage dedupe
$skill-atlas manage sync
```

Replace `$skill-atlas` with `/skill-atlas` in OpenCode or Claude Code. These commands generate reports and plans; a consolidation suggestion does not mean links were already changed.

### Find Competitors for Your Skill

```text
$skill-atlas discover competitors closeout
```

User-authored skills are protected. Competitors are references for comparison and iteration, not automatic replacements.

### Choose Skills for a Product

```text
$skill-atlas recommend product I want to build an automotive HMI design tool --mode balanced
```

Skill Atlas separates installed skills, suggested execution order, missing capabilities, and external models, plugins, MCP servers, or software integrations.

Both recommendation and orchestration support three research modes:

| Mode | Behavior | Use it for |
| --- | --- | --- |
| `quick` | Uses local skills first and searches externally only for missing capabilities | Fast starts |
| `balanced` | Default; compares every capability with three public candidates even when local matches exist | Normal product decisions |
| `benchmark` | Targets eight candidates per capability and adds deeper eval, maintenance, license, compatibility, and security queries | High-stakes selection |

Local and public candidates use the same 100-point rubric: task fit 30, workflow quality 20, eval evidence 15, maintenance 10, source and license 10, compatibility 10, and safety 5.

The CLI creates an external research worklist; it does not browse the web itself. A `provisional` result still requires the active Agent to execute the searches, inspect source code, complete security review, and score the candidates.

### Does Every Startup Search the Whole Market?

No. Agent platforms do not share one startup-hook system, and a full search on every launch would be slow. Every `recommend` or `orchestrate` invocation checks the local reviewed snapshot instead: `quick` defaults to seven days, `balanced` to 24 hours, and `benchmark` always requires current research.

The lightweight status check is offline:

```text
$skill-atlas market status
```

When it reports `missing` or `stale`, create a research packet:

```text
$skill-atlas market refresh --category ui-ux
```

This remains `research-required`. The Agent must actually research and review at least one marketplace, one official or GitHub source, and one community source, then save results with `market refresh --results results.json`. Add `--refresh` to a recommendation when the cache must be ignored.

### Reuse a Reviewed Skill Combination

Market candidates may declare `roles`, `keywords`, and `platforms`. Supported roles are `research`, `design`, `discovery`, `planning`, `implementation`, `review`, and `verification`. Keywords keep specialized candidates tied to relevant requests.

For example, after reviewing React Bits' animation skills and an implementation skill, record candidates like this:

```json
{
  "name": "review-animations",
  "url": "https://github.com/DavidHDev/react-bits",
  "capabilities": ["animation-motion", "design-validation"],
  "roles": ["review"],
  "keywords": ["react", "interaction", "motion"],
  "platforms": ["codex", "opencode", "claude"],
  "score": 90
}
```

Save the complete reviewed results file, then run:

```text
$skill-atlas orchestrate plan Build an interactive React interface with React Bits, accessible motion, and performance --mode balanced
```

Read the output carefully: `use_now` is installed locally; `reviewed_market_matches` comes from the saved snapshot; `reviewed_orchestration` selects one skill per role and lists overlaps as alternatives. `install-required` needs explicit installation approval. `refresh-required` needs current web research before selection.

Validate the proposed combination:

```text
$skill-atlas orchestrate validate I want to build an automotive HMI design tool --mode balanced
```

### Find Professional Software Integrations

```text
$skill-atlas recommend tool Help an architect automate Rhino, Grasshopper, Blender, and SketchUp
```

A result may include skills, desktop applications, scripting APIs, plugins, or MCP servers. Review each artifact according to its own installation and security model.

## 5. Recurring Competitor Comparisons

Create a monitor:

```text
$skill-atlas monitor add closeout --interval monthly
```

Intervals: `daily`, `weekly`, `monthly`, or `quarterly`.

List due monitors:

```text
$skill-atlas monitor due
```

Ask the Agent to complete the real web research:

```text
$skill-atlas monitor run closeout. Execute the research packet, verify sources, authors, licenses, maintenance, compatibility, and security, then save this comparison and compare it with the previous one.
```

The process has two stages:

1. Skill Atlas creates a research packet.
2. The Agent performs current web research and records reviewed results.

`research-required` means only stage one is complete. The monitor remains due and must not be presented as a completed comparison.

View history:

```text
$skill-atlas monitor history closeout
```

Monitor state is stored under `~/.local/share/skill-atlas` by default.

### Does It Run in the Background?

No. Skill Atlas does not install a hidden resident process. Use Codex Automation, OpenCode Automation, `cron`, or macOS `launchd` to wake an Agent periodically with a request such as:

```text
Use Skill Atlas to check monitor due. Complete web research, security review, and historical comparison for every due monitor. Never replace user-authored skills.
```

## 6. Status Glossary

- `read-only`: no files were changed
- `research-required`: a research packet exists, but external comparison is incomplete
- `missing` / `fresh` / `stale`: the market snapshot is absent, inside its TTL, or expired
- `completed`: reviewed results were saved as a snapshot
- `user-authored`: your skill; never automatically replaced
- `external-maintained`: maintained by an external author and eligible for reviewed updates
- `tool-bundled/cache`: managed by a platform; do not edit it in place
- `unknown-local`: origin is unclear and must be confirmed before updates

## 7. Troubleshooting

### `/skill-atlas` Is Missing

- Codex does not provide this custom slash command. Use `$skill-atlas` or natural language.
- OpenCode and Claude Code require installation with `--commands`.
- Fully restart the Agent application.
- Check command links:

```bash
ls -l ~/.config/opencode/commands/skill-atlas.md
ls -l ~/.claude/commands/skill-atlas.md
```

### The Command Is Not Found

Test the canonical installation directly:

```bash
python3 ~/.agents/skills/skill-atlas/scripts/skill_atlas.py --help
```

### Duplicates Were Reported but Not Merged

This is intentional. Run `manage sync`, review the exact plan, and explicitly approve any copy removal or symbolic-link creation.

### Check the Installed Version

```bash
python3 ~/.agents/skills/skill-atlas/scripts/skill_atlas.py manage self status
```

The beta version does not perform unattended network updates. Review a release before applying `manage self update`.
