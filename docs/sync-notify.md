# Sync Notifications

`sync notify` is an optional, lightweight notification command added in
`0.12.0-beta`. It checks one or more Git repositories (and their worktrees) and
notifies you only when there is something that needs attention — an unpushed
commit, a branch with no upstream, a remote-tracking branch that is ahead, or a
detached HEAD. It is silent when everything is clean.

![Target macOS notification: Skill Atlas banner with repository, branch, and unpushed count](assets/sync-notification-mockup.png)

*UI target for the FlowCue Pro surface. The current lightweight `osascript` notification may show Script Editor as the app name and has no custom buttons.*

It exists so that the same warnings already recorded by `checkpoint` and
`handoff` can also reach you from a hook, a scheduler, or a shell alias without
turning Skill Atlas into a background service. `sync notify` never pushes,
commits, merges, or starts an agent; it only reports. A person still decides what
to do.

## What it is and is not

It **is**:

- a one-shot, local check of explicitly listed projects and a registry file;
- worktree-aware: each repository expands to its Git worktrees;
- deduplicated through a local state file and a minimum interval;
- quiet when clean, compact when not;
- usable from macOS notifications, stderr, or JSON output.

It **is not**:

- a background daemon, menu-bar app, or timer — nothing runs unless you invoke it
  (or wire it into your own hook/scheduler);
- a sync tool: it does not push, commit, merge, rebase, or change branches;
- a fetch service — fetching is opt-in with `--fetch` and only updates
  remote-tracking refs;
- a delivery guarantee: operating-system notification settings can mute or hide
  the notification.

## Quickstart

```bash
# Check the current repository; macOS notification is the default channel.
python3 <skill-root>/scripts/skill_atlas.py sync notify --project .

# Check several explicit repositories and print one compact line to stderr.
python3 <skill-root>/scripts/skill_atlas.py sync notify \
  --project ~/repos/one --project ~/repos/two --channel stderr

# Use a registry file and print the full JSON result.
python3 <skill-root>/scripts/skill_atlas.py sync notify \
  --registry ~/.config/skill-atlas/projects.json --channel json

# Optionally fetch first so "behind" is fresh; never pushes.
python3 <skill-root>/scripts/skill_atlas.py sync notify --project . --fetch --channel stderr

# Also include uncommitted changes as actionable.
python3 <skill-root>/scripts/skill_atlas.py sync notify --project . --include-dirty --channel stderr
```

| Flag | Meaning |
|---|---|
| `--project PATH` | Repository to check. May be repeated. |
| `--registry PATH` | JSON file containing a list of repository paths, or an object with a `projects` list. |
| `--channel macos\|stderr\|json` | Where actionable warnings go (default: `macos`). |
| `--min-interval MINUTES` | Suppress the same state per worktree for this many minutes (default 60). |
| `--state PATH` | Deduplication state file (default `~/.cache/skill-atlas/sync-notify.json`). |
| `--fetch` | Run `git fetch --quiet --prune` before checking. Off by default; never pushes. |
| `--fetch-timeout SECONDS` | Time limit per repository fetch (default 10). |
| `--include-dirty` | Treat uncommitted changes as actionable too. Off by default. |

At least one `--project` or a `--registry` file is required; otherwise the command
is refused with exit status 2. Non-Git paths and unreadable worktrees are
reported in `skipped` rather than aborting the whole run.

## Registry file

The registry is intentionally simple — a JSON list:

```json
[
  "/Users/you/repos/project-a",
  "/Users/you/repos/project-b"
]
```

or an object with a `projects` list:

```json
{
  "projects": [
    "/Users/you/repos/project-a",
    "/Users/you/repos/project-b"
  ]
}
```

Relative paths resolve from the current working directory; absolute paths are
clearer for launchd/cron entries. An unreadable or invalid registry is refused
with exit status 2.

## Worktrees

For each repository, `sync notify` runs `git worktree list --porcelain` and checks
the main worktree plus every linked worktree it reports. A linked worktree with
its own branch can need a push even when the main checkout is clean, so each path
is checked and tracked separately. Duplicate paths are checked once; `checked` in
the result counts the worktree paths examined.

## What counts as actionable

A worktree produces a notification when any of these is true:

| Condition | Meaning |
|---|---|
| **no upstream** | The current branch has no upstream; commits are local-only. |
| **unpushed commits** | `ahead > 0`: local commits are not on the remote. |
| **behind remote** | The remote-tracking branch is ahead; fetch and then rebase or merge deliberately. |
| **detached HEAD** | Commits are not on a branch and are easy to lose. |
| **uncommitted changes** | Only when `--include-dirty` is passed; otherwise dirty state is ignored. |

Warnings are summarized, not blocking: a notification says *what* looks
actionable, and you decide whether to push, commit, branch, or ignore it. Nothing
is changed and no remote is contacted unless you add `--fetch`.

## Channels

- **`macos`** (default) — sends a notification with
  `osascript -e 'display notification ...'`. The macOS notification system may
  display **Script Editor** as the app name because `osascript` is the sending
  process, and there are no custom buttons or click actions. Branded or clickable
  notifications would require a signed helper application or a Pro/helper-app
  path, which is not part of this release. Delivery also depends on the user's
  Notification Center and Focus settings.
- **`stderr`** — prints one compact line such as
  `Skill Atlas · 1 project needs a push: project · master: 1 unpushed`.
  This is the easiest channel for hooks and logs; it stays silent when clean.
- **`json`** — prints the full result object (including `notified`, `suppressed`,
  `skipped`, and `fetch_errors`) to stdout. Useful for scripts; it prints even
  when the status is `clean`.

The command exits 0 for a normal check, whether clean or notified. It exits 2 only
when the request is refused (no targets, invalid registry, or an unsupported
channel).

## Deduplication and interval

The state file (default `~/.cache/skill-atlas/sync-notify.json`, override with
`--state`) records the last notified state per worktree path. When the same
branch/commit/ahead/behind/upstream/detached state is seen again inside
`--min-interval` minutes (default 60), the entry is added to `suppressed` instead
of `notified`; `macos` and `stderr` stay silent, and `json` reports
`status: clean` with a non-empty `suppressed` list.

- Delete the state file to re-arm notifications.
- A changed commit, branch, ahead/behind count, upstream presence, or detached
  state produces a new notification.
- Uncommitted-only changes are not part of the dedupe key. With
  `--include-dirty`, a worktree whose only change is dirty state may stay
  suppressed until the interval elapses; use `--min-interval 0` if you genuinely
  want every dirty check reported.

State is local; nothing is uploaded and no remote service is used to deduplicate.

## Optional fetch

By default, `sync notify` reads local Git state only. That means `behind` is based
on the last known remote-tracking refs and can be stale. `--fetch` runs
`git fetch --quiet --prune` for each repository root before checking, with a
per-fetch timeout (`--fetch-timeout`, default 10 seconds).

Fetch only updates remote-tracking refs. It does **not** merge, rebase, push,
commit, or change the working tree. Fetch failures (offline, missing credentials,
timeouts) are collected in `fetch_errors` and the check continues with local
state. If you do not want any network access, leave `--fetch` off.

## Example output

`--channel stderr` prints one line:

```text
Skill Atlas · 1 project needs a push: project · master: 1 unpushed
```

The macOS channel uses the same summary as title/subtitle/body: title
`Skill Atlas`, subtitle `1 project needs a push`, body
`project · master: 1 unpushed`. For compactness, the body lists at most three
worktrees as `<worktree name> · <branch>: <detail>`, followed by `+N more` when
needed. Notifications are intentionally short: they are a prompt to go look, not
a report.

## JSON result

`sync notify --channel json` returns:

| Key | Contents |
|---|---|
| `status` | `notified` when at least one worktree was newly actionable, otherwise `clean` (including when everything was suppressed) |
| `channel` | `macos`, `stderr`, or `json` |
| `checked` | Number of unique worktree paths examined |
| `notified` | Actionable worktrees that were reported this run |
| `suppressed` | Actionable worktrees suppressed by the interval/state dedupe |
| `skipped` | Projects/worktrees that could not be checked, with a `reason` |
| `fetch_errors` | Repositories whose optional fetch failed, with an `error` |
| `state_file` | Deduplication state file path |
| `fetch` | Whether `--fetch` was requested |
| `notes` | A reminder that checks are read-only and nothing is pushed |

Each entry in `notified` and `suppressed` has `project` (repository root), `path`
(worktree path), `branch`, `has_upstream`, `ahead`, `behind`, `dirty`,
`detached`, `commit`, and `warnings`. `skipped` entries have `project` and
`reason`; `fetch_errors` entries have `project` and `error`.

## Optional wiring

Nothing invokes `sync notify` for you. The examples below are optional,
platform-specific starting points; verify the current configuration format for
your client or operating system. All of them are notification-only: never add an
auto-push step, and keep `--fetch` off unless you deliberately want the network
check.

### Shell alias

```bash
alias sync-notify='python3 /path/to/skill-atlas/scripts/skill_atlas.py sync notify --project /path/to/repo --channel stderr'
```

Run it after a work block or before switching agents.

### Claude Code Stop hook

If your Claude Code version supports command hooks, a `Stop` hook can call the
same command:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/skill-atlas/scripts/skill_atlas.py sync notify --project /path/to/repo --channel stderr"
          }
        ]
      }
    ]
  }
}
```

Hook configuration locations and schemas differ by client and version; confirm
the current format in your client's documentation before relying on this. Use
`stderr` and keep the output compact. A per-turn hook can add context tokens
because its output may be fed back to the model; `sync notify` is silent when
clean, which keeps that cost near zero. The notification itself does not consume
model tokens.

### Codex notify wrapper

Codex's `notify` setting can pass its JSON event to a command. A small wrapper
can ignore that JSON and call `sync notify`:

```sh
#!/bin/sh
# Save as ~/.local/bin/skill-atlas-sync-notify and register it as Codex's notify command.
python3 /path/to/skill-atlas/scripts/skill_atlas.py sync notify \
  --project /path/to/repo --channel stderr
```

The wrapper does not need to parse the event payload. Register the wrapper with
the current Codex `notify` setting; validate the configuration format for your
Codex version.

### launchd (macOS), every 60 minutes

A user LaunchAgent can run an explicit project list or registry periodically.
Save as `~/Library/LaunchAgents/local.skill-atlas.sync-notify.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>local.skill-atlas.sync-notify</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>python3</string>
    <string>/path/to/skill-atlas/scripts/skill_atlas.py</string>
    <string>sync</string>
    <string>notify</string>
    <string>--registry</string>
    <string>/Users/you/.config/skill-atlas/projects.json</string>
    <string>--channel</string>
    <string>macos</string>
  </array>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
```

Then load it with
`launchctl load -w ~/Library/LaunchAgents/local.skill-atlas.sync-notify.plist`
(after checking the Python path and registry path for your machine). launchd runs
with a limited environment and can differ from your shell; verify that the job
actually runs. This is a scheduler, not a Skill Atlas daemon — it invokes one
check per interval and then exits.

### Token and cost notes

- A notification sent through macOS or stderr does not consume model tokens.
- A hook whose output is passed back to a model can add context tokens on every
  turn. Prefer an end-of-block/Stop hook over a per-tool-call hook, and use
  `--channel stderr` with the compact line.
- `sync notify` is silent when clean, which is what makes frequent invocation
  inexpensive.
- JSON output is for scripts and is not meant to be fed into a model conversation
  repeatedly.

## Relationship to `sync status` and checkpoints

- `sync status --project .` checks one repository on demand and prints a readable
  Git status; it is the best command to run manually or before a handoff.
- `checkpoint`/`handoff` record `git.sync` warnings in the task evidence; `resume`
  reports current warnings when inspecting a checkpoint.
- `sync notify` is the batch, worktree-aware, deduplicated variant intended for
  hooks and schedulers. It is still one-shot: if nothing invokes it, nothing
  happens.

All three are read-only unless `--fetch` is passed, and none of them pushes,
commits, merges, or starts an agent. See
[Installation and Development Layout](development-layout.md#push-before-you-hand-off-and-during-long-work)
for the wider handoff convention.

## Limitations

- **No delivery guarantee.** macOS notification settings, Focus modes, or the
  way `osascript` is registered can hide or mute the notification; the command
  still exits successfully.
- **macOS shows `Script Editor` as the app.** `osascript` is the sending process,
  so the notification may not be branded and cannot have custom buttons. A
  branded, clickable helper is future work, not part of `0.12.0-beta`.
- **Platform-specific wiring is not bundled.** Hooks, launchd, cron, and shell
  aliases vary by client, OS version, and permissions; validate the exact
  configuration before relying on it.
- **`behind` may be stale without `--fetch`.** Fetch only updates remote-tracking
  refs; failures are reported but do not block the check.
- **Deduplication is local and approximate.** The state file is per user; dirty
  changes are not part of the dedupe key; changing only dirty state with
  `--include-dirty` may be suppressed until the interval ends.
- **Non-Git paths are skipped.** At least one valid project is required; invalid
  registries and missing targets are refused.
- **No cleanup.** The command does not delete or truncate worktrees, branches, or
  state unexpectedly; the state file only records notification keys. It never
  pushes, commits, merges, or fetches unless `--fetch` is explicitly supplied.

## Privacy

Everything is local. The command reads local Git metadata only (no file contents,
credentials, or session text), and opens no network connection unless `--fetch`
is supplied. The state file stores only worktree paths and deduplication keys
(branch, commit, ahead/behind, upstream presence, detached state) plus a
timestamp. Notification titles and bodies contain worktree names, branch names,
and warning counts; treat screenshots or logs of them as you would any local
project path.
