# Installation and Development Layout

This page explains where each local copy of Skill Atlas belongs and which copy may be
edited. It is written for two audiences: people who install the skill and people (or
agents) who change it.

The short version: **the Git repository is the only source of truth.** A local
installation is a derived copy, and a local edit belongs in a checkout of the repository,
not in the copy an agent loads.

## Roles

| Role | Purpose | May be edited? | How it changes |
|---|---|---|---|
| Upstream repository | Source of truth; all changes land here through pull requests | Yes, on a branch | Commit, push, review, merge |
| Development checkout | Working copy used to create a branch; preferably one `git worktree` per task | Yes, on its task branch | Commit and push to the same upstream remote |
| Installation copy | Directory an agent tool loads the skill from | **No** | Update by fetching a reviewed commit or release tag |
| Archive | Frozen snapshot kept for history or recovery | **No** | Never; add a new archive instead of rewriting one |

A machine can have several directories, but only one of them is the repository, and only
one of them is the installation. Everything else is a development copy or an archive.
The same rules apply regardless of which agent tool starts the work: Codex, Claude Code,
DeepSeek Harness, OpenCode, WorkBuddy, Kimi Code, Cursor, TRAE, Qoder or another client.

## Example layout

Paths are examples, not requirements. Use whatever locations your tools allow.

```text
~/repos/skill-atlas/                     # upstream checkout, usually on main
~/.local/share/agent-skills/skill-atlas/ # installation copy loaded by agent tools
~/worktrees/skill-atlas-issue-42/        # development worktree for one task
~/archives/skill-atlas-2026-01-01/       # frozen snapshot, read-only
```

Agent skill entries normally point at one of these locations. For example a shared
`~/.agents/skills/skill-atlas` entry may be a symlink to the upstream checkout, while
individual tool entries may point at the installation copy. A symlink does not create a
new copy and does not change these roles; only its target matters.

## For people installing the skill

1. Install from a reviewed commit, a release tag, or your fork — not from an unpublished
   working tree.
2. Do not edit files in the installation copy. Local edits there are invisible to the
   upstream project, are lost on the next update, and make the installed version
   disagree with what other agents load.
3. Update by fetching and fast-forwarding the installation copy, or by re-running the
   installer against a reviewed source:

   ```bash
   git -C /path/to/installation fetch origin
   git -C /path/to/installation merge --ff-only origin/main
   ```

   If the installer manages the directory, prefer `install` and `manage self update`
   with their review and confirmation steps.
4. Report problems upstream (an issue or a pull request) rather than patching the
   installation copy.

## For contributors and agents

1. Keep the upstream checkout clean and on `main`; do not develop there.
2. Create one branch and one worktree per task. A worktree shares the repository's object
   store and remote configuration, so it is cheaper than a second clone and its history
   cannot drift:

   ```bash
   git -C /path/to/repo fetch origin
   git -C /path/to/repo worktree add /path/to/worktrees/skill-atlas-issue-42 \
     -b feat/issue-42-checkpoint origin/main
   ```

3. Work, test and commit inside the worktree. Push the branch to the same upstream remote
   and open a pull request:

   ```bash
   git -C /path/to/worktrees/skill-atlas-issue-42 push -u origin feat/issue-42-checkpoint
   ```

4. When the pull request is merged, remove the worktree and optionally the branch:

   ```bash
   git -C /path/to/repo worktree remove /path/to/worktrees/skill-atlas-issue-42
   git -C /path/to/repo branch -d feat/issue-42-checkpoint
   ```

5. Do not copy files between clones by hand, and do not continue work in a clone that is
   not connected to the same upstream remote. If two copies disagree, compare commits and
   document differences in the pull request; do not reconcile them by overwriting one
   copy with the other.

Agents that can only write inside a sandboxed workspace can place the worktree in that
workspace while the repository itself stays elsewhere. Creating the worktree writes only
the repository's `.git/worktrees/` metadata; the branch and commits are still pushed to
the upstream remote.

## Keeping an installation honest

A local installation can lag behind `main` while still reporting an old version, or a
development copy can be mistaken for the installation. The read-only
[agent environment scan](agent-environments.md) reports local Skill Atlas copies, their
versions and symlink aliases, and sets `version_mismatch` when copies disagree:

```bash
python3 /path/to/skill-atlas/scripts/skill_atlas.py agents scan --format json
```

Treat `version_mismatch: true` as a prompt to compare commits, not as permission to
overwrite a directory. The scan only reports file evidence; it does not prove which copy
an agent actually loaded.

## Archiving an old copy

When a copy is replaced, freeze it rather than deleting it immediately if it may contain
unique work:

1. Record its Git state: `git bundle create <name>.bundle --all`, plus
   `git status --porcelain` and a patch of uncommitted changes.
2. Archive the working tree, including untracked files.
3. Write a short provenance note: original path, date, version, commit, what was
   uncommitted, and how to restore it.
4. Record checksums and keep the archive out of every agent's skill roots.
5. Delete the original only after the archive has been verified and you have decided it
   is no longer needed.

An archive is evidence, not a development location and not an installation.


## Protect the integration branch

A development convention only works if the shared branch cannot be changed around it.
On GitHub, protect the branch that agents push to (usually `main`):

- **Require a pull request before merging.** Direct pushes bypass review, status checks and the history that later agents read.
- **Require the project's CI status check** (for this repository, the `python` job). A green check is evidence, not decoration.
- **Block force pushes and branch deletion.**
- **Include administrators.** Without this, an admin token (including an automation token) can bypass the rules. The protection then protects people from their own automation, not just from each other.
- Require conversation resolution when review comments are used.

Administrators can still disable protection in repository settings; that is an explicit, auditable action rather than a routine bypass. A solo maintainer pays a small cost: hotfixes also go through a pull request. That cost is usually smaller than recovering from an unreviewed or unverified push.

Hosts other than GitHub expose similar controls (protected branches, required checks, merge queues). The principle is the same: the integration branch accepts changes only through a reviewed, verified path.

## Push before you hand off (and during long work)

A local commit is not a handoff. Work that exists only in one checkout — an unpushed branch, a commit
with no upstream, or uncommitted changes — is invisible to another machine, another agent, or a
resumed session that reads the remote. Push reviewed work before handing it off.

Skill Atlas checkpoints and handoffs now record a read-only `git.sync` block in the saved state, and
their command results add a top-level `warnings` array so this risk is visible in the handoff
evidence:

- **no upstream** — the current branch has no upstream; commits are local-only;
- **ahead** — local commits are not on the remote;
- **behind** — the remote-tracking branch is ahead; fetch and then rebase or merge deliberately;
- **dirty** — uncommitted changes exist (the count excludes `.agent-state/`);
- **detached HEAD** — commits are not on a branch and are easy to lose.

`resume` reports the same current warnings when it inspects a saved checkpoint. To check on demand,
run the read-only sync command:

```bash
python3 /path/to/skill-atlas/scripts/skill_atlas.py sync status --project .
```

```text
# Git sync status
- branch: `feat/issue-42`
- upstream: `origin/feat/issue-42`
- ahead: 1; behind: 0; dirty: 0
- warning: 1 local commit(s) are not on the remote; push when the work is reviewed
- note: Read-only local Git status; no fetch, push or repository mutation executed
```

The command never fetches, pushes, commits, rebases, or changes a branch, and it opens no network
connection. `ahead` and `behind` are computed from local tracking refs, which may be stale until you
fetch yourself. Treat the warnings as prompts for a human decision, not as a blocked state.

Recommended checkpoints: when you save a checkpoint or handoff, at the end of a work block, before
switching agents, after a merge, and before leaving work another session may resume. This is **not a
background daemon and has no timer**: a reminder appears only when `checkpoint`, `handoff`, `resume`,
or `sync status` runs.

If you want a proactive reminder, wire the same read-only command into your own shell, scheduler, or
client hook. A portable shell function is enough:

```bash
# Add to ~/.bashrc or ~/.zshrc; pass a project path or use the current directory.
sync_reminder() {
  python3 /path/to/skill-atlas/scripts/skill_atlas.py sync status --project "${1:-.}"
}
```

`cron`, `launchd`, and agent-client hooks can call the same command, but each platform's scheduler
and hook configuration differs; validate that yours runs and shows output. Do not auto-push from any
of these reminders.

A person decides what to do next: push only reviewed commits, never push credentials, private keys,
or large binaries, and when `behind` is reported fetch first and then rebase or merge deliberately.
Create a branch before continuing from a detached HEAD, and commit or explicitly discard local
changes before handoff.

### Lightweight notifications (`sync notify`)

`sync notify` runs the same checks across one or more repositories and every
worktree they contain, and notifies only when a worktree is actionable (no
upstream, unpushed commits, behind, detached HEAD; dirty only with
`--include-dirty`). It is still opt-in and one-shot — no daemon and no timer:

```bash
python3 /path/to/skill-atlas/scripts/skill_atlas.py sync notify --project .
python3 /path/to/skill-atlas/scripts/skill_atlas.py sync notify \
  --registry ~/.config/skill-atlas/projects.json --channel stderr
```

The default channel is a macOS notification (via `osascript`; macOS may show
"Script Editor" as the app and there are no custom buttons); `stderr` and `json`
are available for hooks and scripts. It is silent when clean and deduplicates
identical state per worktree through a local state file and `--min-interval`
(default 60 minutes). `--fetch` is off by default and only updates
remote-tracking refs; it never pushes, merges, or commits.

To make the reminder proactive, wire `sync notify` into your own shell alias,
Claude Code/Codex hook, or launchd/cron job. For a low-noise setup, run it from
launchd every 15 minutes with `--min-interval 60 --idle-minutes 15`: it stays
silent while files or commits are recent and reminds only after 15 minutes of
inactivity. `--test-notification` verifies delivery, and `--log` records
delivered reminders. Keep hooks compact: notifications themselves do not consume
model tokens, but a per-turn hook that feeds output back to the model can add
context tokens. Never add an auto-push step. Concrete hook/launchd examples and
caveats are in [Sync Notifications](sync-notify.md).

## Limitations

- Example paths in this page are illustrative; platform conventions and agent tools
  differ.
- A worktree shares repository metadata but not uncommitted changes, stashes or local
  configuration such as hooks; review them separately.
- This page describes a collaboration convention. Skill Atlas does not move, adopt or
  repair copies automatically.
