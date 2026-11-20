# Project Sync Summary

`sync summary` prints a compact, read-only project-state summary for the end of a
work block or a handoff. It answers one question: *is this project in a state
that wants a commit, a checkpoint, or a push before I stop or hand it off?*

It was added in `0.16.0-beta` and is deliberately small: branch, dirty count,
ahead/behind, upstream presence, a one-line summary, `commit_suggested`,
`checkpoint_suggested`, and concrete next actions. It never commits, pushes,
fetches, or changes anything.

## What it is and is not

It **is**:

- a compact read-only summary of one project's Git state;
- an end-of-block / handoff nudge that says whether a commit or checkpoint looks
  due;
- threshold-aware: `--dirty-min-files` (default 20) decides when uncommitted
  work is enough to suggest a commit;
- available as Markdown for people and JSON for scripts or agents.

It **is not**:

- an automatic commit or checkpoint: `commit_suggested` and
  `checkpoint_suggested` are advisory booleans;
- a background monitor or timer;
- a replacement for `sync status` when you need the full warning list;
- a way to nag on every small edit — see the threshold guidance below;
- a multi-project aggregator: it summarizes one `--project` at a time.

## Quickstart

```bash
# Compact summary for the current project (commit suggestion at 20+ dirty files).
python3 <skill-root>/scripts/skill_atlas.py sync summary --project .

# Use a lower threshold for a small project.
python3 <skill-root>/scripts/skill_atlas.py sync summary --project . --dirty-min-files 5

# JSON for an agent or script.
python3 <skill-root>/scripts/skill_atlas.py sync summary --project . --format json
```

Run it at the end of a work block, before a handoff, or when deciding whether to
commit; do not wire it to every file save.

Example with two uncommitted files and the default threshold:

```text
# Project sync summary
- project: `/Users/you/repos/widgets`
- summary: widgets · feat/issue-42: 2 dirty, 0 ahead, 0 behind, upstream=yes
- commit suggested: False
- checkpoint suggested: True
- action: Review and commit/checkpoint 2 uncommitted change(s).
- note: Read-only summary; no commit, push, fetch or branch change was made.
```

With `--dirty-min-files 2`, `commit suggested` becomes `True`.

## Flags

| Flag | Meaning |
|---|---|
| `--project PATH` | Project to summarize (default `.`). |
| `--dirty-min-files N` | Suggest a commit when the dirty count is at or above N (default 20; values below 1 are raised to 1). |
| `--format markdown\|json` | Output format (default `markdown`). |

## What the summary means

| Field | Meaning |
|---|---|
| `status` | `ok` |
| `project` | Resolved repository root |
| `summary` | One-line text: `name · branch: N dirty, N ahead, N behind, upstream=yes\|no` |
| `branch` | Current branch, or `DETACHED` |
| `upstream` / `has_upstream` | Upstream reference, if configured |
| `ahead` / `behind` | Local commits not on the remote / remote-tracking commits not local |
| `dirty` | Number of dirty entries from `git status --porcelain` (untracked files included; `.agent-state/` excluded) |
| `detached` | Whether HEAD is detached |
| `last_commit` / `commit` | Last commit timestamp and current HEAD |
| `dirty_threshold` | Effective threshold used for `commit_suggested` |
| `commit_suggested` | `true` when `dirty >= dirty_threshold` |
| `checkpoint_suggested` | `true` when there is uncommitted work, unpushed commits, an upstream problem, a behind state, or a detached HEAD |
| `actions` | Concrete next steps; a clean project gets `Working tree and branch are clean.` |
| `notes` | Read-only reminder |

`commit_suggested` considers only the dirty count and threshold; `ahead`,
`behind`, detached state, and missing upstream do not set it. `checkpoint_suggested`
covers all of those states, because a checkpoint or handoff should record the
state before you move on. A clean project sets both to `false`.

The dirty count is a count of Git status entries, not lines changed: a modified
file counts once, and each untracked file counts as its own entry with
`--untracked-files=all`. `.agent-state/` is ignored.

## Choosing a dirty threshold

The recommended default is **20 files**:

- **Use 20 at end-of-block/handoff.** A handful of in-progress edits (1–10 files)
  is normal and should not produce a commit nag; 20+ dirty files usually means
  work has accumulated and deserves a review/commit/checkpoint.
- **Do not run this on every small edit.** The summary is a periodic
  end-of-block nudge, not a keystroke watcher.
- **Adjust for the project.** Lower the threshold (for example 5) for tiny
  personal projects; raise it for generated or vendored trees you routinely keep
  dirty, or narrow those paths in your workflow.
- **The threshold is advisory.** `commit_suggested` does not review the changes;
  inspect the diff and decide.

The same `--dirty-min-files` spelling is used in three places, with different
defaults on purpose:

| Context | Default | Effect |
|---|---|---|
| `sync summary --dirty-min-files` | 20 | Whether `commit_suggested` becomes true |
| `sync notify --include-dirty --dirty-min-files` | 1 | Whether a dirty-only notification appears |
| `sync helper install --dirty-min-files` | 20 | Whether the menu-bar badge includes dirty work |

The helper uses the same dirty threshold in its native Git check, so it shows a
dirty warning only once the count reaches the configured number; OS
notifications from `sync setup` are separate and remain governed by the
notification job's idle/force-after/min-interval settings.

## Relationship to checkpoint, handoff, and the helper

- `checkpoint` and `handoff` save evidence under `.agent-state/` and include a
  read-only `git.sync` block plus warnings. `sync summary` is the short on-demand
  nudge before or after those actions; it saves nothing.
- [`sync status`](cli-reference.md) is the detailed, warning-oriented check.
  `sync summary` condenses the same Git facts into a commit/checkpoint decision.
- [`sync notify`](sync-notify.md) delivers warnings on a schedule or hook;
  `--include-dirty --dirty-min-files` controls dirty warnings there.
- [The menu-bar helper](sync-helper.md) uses the same idea with a default
  threshold of 20: its badge starts counting dirty work once the threshold is
  reached, without needing notification permission.

## Read-only by design

`sync summary` reads local Git state only. It does not fetch, so `ahead`/`behind`
reflect local tracking refs and may be stale. It does not commit, push, rebase,
merge, switch branches, write state files, open a network connection, or start an
agent. The JSON result contains only the summary; the Markdown output is a short
human-readable view.

## Limitations

- **Advisory, not authoritative.** `commit_suggested` is a count-based nudge; it
  does not inspect diff size, file type, or whether the changes are intentional.
- **Single project.** Run it per project; it does not summarize a registry or
  multiple worktrees at once. `sync status`/`sync notify` cover broader checks.
- **Dirty entries include untracked files.** Generated/build artifacts can inflate
  the count; ignore or exclude them in your workflow, or adjust the threshold.
- **Tracking refs can be stale.** No fetch happens; run your own fetch before
  comparing `ahead`/`behind` across machines.
- **Threshold defaults can be wrong for a project.** 20 is a recommendation, not
  a rule; tune it rather than ignoring the signal.
