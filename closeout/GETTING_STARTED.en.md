# Closeout Beginner Guide

[中文](GETTING_STARTED.zh-CN.md) | **English** | [Русский](GETTING_STARTED.ru.md)

Closeout performs evidence-based project closeout. It reconciles source code, real runtime behavior, documentation, Agent rules, authorized memory, and workspace residue.

It is not a generic file organizer and does not delete files, branches, or worktrees without informed confirmation.

## 1. Install

```bash
git clone https://github.com/Jorgut/closeout-skill.git
cd closeout-skill
python3 scripts/install_closeout.py --all-platforms --commands
```

The last command is a preview. If no conflict is reported, apply it:

```bash
python3 scripts/install_closeout.py \
  --all-platforms \
  --commands \
  --apply \
  --confirm
```

Fully quit and reopen Codex, OpenCode, or Claude Code.

## 2. Where to Invoke It

### Codex

Codex does not expose a custom `/closeout` command. Enter:

```text
$closeout
```

Or use natural language:

```text
Use Closeout to verify that this project's code, README, and Agent rules agree.
```

### OpenCode or Claude Code

```text
/closeout
```

Natural language also works:

```text
Run Closeout on this project. Do not delete anything yet.
```

## 3. Safe First Test

Open a small Git project with code and a README, then request:

```text
$closeout docs-sync. Check only code, README, and rule files. Do not change memory or delete anything.
```

In OpenCode or Claude Code, replace `$closeout` with `/closeout`.

Read all six fact-plane statuses. If cleanup candidates are listed, nothing is deleted until you review the report and confirm specific actions.

## 4. Choose a Mode

### `docs-sync`

Use after routine development to reconcile documentation and rules with code:

```text
$closeout docs-sync. Verify startup commands, ports, and documented features against the implementation.
```

### `knowledge-closeout`

Use after completing a feature or milestone when the next session needs reliable context:

```text
$closeout knowledge-closeout. Reconcile docs, rules, and memory that this platform explicitly allows you to maintain.
```

Closeout must not write memory when no supported or authorized memory surface exists.

### `release-closeout`

Use after a PR, deployment, or release:

```text
$closeout release-closeout. Verify the separate state of code, remote repository, deployment, and live user surface.
```

Release states are distinct: `draft`, `PR`, `merged`, `deployed`, `live-verified`, `knowledge-closed`, and `cleaned`. Merged does not mean deployed, and deployed does not mean live-verified.

### `workspace-audit`

Use only when several projects must be inspected:

```text
$closeout workspace-audit. Inspect documentation and rule conflicts read-only; do not write across projects.
```

## 5. Understand the Report

| Fact plane | What it verifies |
| --- | --- |
| `code` | Source, configuration, schema, and tests |
| `runtime` | What users or deployed services actually receive |
| `docs` | README and documentation accuracy |
| `rules` | AGENTS.md, CLAUDE.md, and other active instructions |
| `memory` | Authorized cross-session knowledge |
| `workspace` | Temporary artifacts, copies, branches, or worktrees |

Statuses:

- `verified-current`: checked and correct
- `changed-and-verified`: corrected and verified again
- `pending`: evidence is unavailable; completion must not be claimed
- `out-of-scope`: excluded from this request
- `not-applicable`: the project does not have this surface

## 6. Why Cleanup Requires a Final Confirmation

Closeout first reports possible cleanup targets, such as obsolete plans, backup copies, branches, or worktrees. After reading the complete report, you must confirm the exact items to remove.

```text
User: $closeout knowledge-closeout
Agent: reports evidence and cleanup candidates
User: I reviewed the report. Delete candidates A and B, but keep C.
Agent: performs the approved cleanup, audits again, and appends the result
```

An initial request such as “finish and clean up” is not the final confirmation. This protects unique work from accidental deletion.

## 7. Useful Examples

```text
$closeout docs-sync. Verify the new login feature, environment-variable documentation, and test command.
$closeout knowledge-closeout. Prepare an accurate handoff and list unfinished work without claiming it is complete.
$closeout release-closeout. Check the GitHub commit, deployment record, and real live page; mark inaccessible evidence pending.
$closeout workspace-audit. Remain read-only and do not modify files, memory, branches, or worktrees.
```

## 8. Troubleshooting

### `/closeout` Is Missing

- Codex uses `$closeout`, not a custom slash command.
- OpenCode and Claude Code require installation with `--commands`.
- Fully restart the Agent application.
- Check command links:

```bash
ls -l ~/.config/opencode/commands/closeout.md
ls -l ~/.claude/commands/closeout.md
```

### Cleanup Candidates Were Not Deleted

This is expected. Read the pre-cleanup report and explicitly approve only the items that may be deleted.

### Why Is Something `pending`?

The Agent lacks direct evidence, such as live access, remote permissions, or executed tests. `pending` is more reliable than a false completion claim.

### Verify Installation

```bash
ls -l ~/.agents/skills/closeout/SKILL.md
ls -l ~/.codex/skills/closeout
ls -l ~/.config/opencode/skills/closeout
ls -l ~/.claude/skills/closeout
```

The last three paths should resolve to the same canonical installation.

