# Sync Notification Setup

`sync setup` is a one-command installer for the optional macOS sync notification
job, added in `0.13.0-beta`; `0.13.1-beta` adds a digest backstop for long-lived
active work. It exists so a Skill Atlas-only user can get push reminders without
installing FlowCue or another helper app: the command writes a small registry of
repositories and installs a launchd user agent that periodically runs
`sync notify`.

It is deliberately explicit. Without `--confirm` it only previews what it would
write. With `--confirm` it merges the registry, writes the LaunchAgent (backing
up existing files), loads it with `launchctl`, and optionally sends a test
notification. It never pushes, fetches, commits, or changes a repository.

## What it is and is not

It **is**:

- a preview-first installer for a macOS LaunchAgent;
- a merger for a local watch registry of Git repository paths;
- explicit about the files it creates and the backups it keeps.

It **is not**:

- a background service inside Skill Atlas — launchd owns the schedule and
  invokes `sync notify`; Skill Atlas has no resident daemon;
- a Git sync tool — it never pushes, fetches, commits, merges, or changes a
  branch;
- an uninstaller — removal is a short manual procedure documented below;
- supported for installing on non-macOS systems. Preview works anywhere;
  `--confirm` is macOS-only.

## Quickstart

Preview first. Without `--confirm`, nothing is written:

```bash
python3 <skill-root>/scripts/skill_atlas.py sync setup
```

With no `--project`, the command watches the Git repository of the current
working directory. To watch specific repositories, repeat `--project`:

```bash
python3 <skill-root>/scripts/skill_atlas.py sync setup \
  --project ~/repos/one --project ~/repos/two
```

Review the preview, then install:

```bash
python3 <skill-root>/scripts/skill_atlas.py sync setup \
  --project ~/repos/one --project ~/repos/two --confirm
```

Useful variants:

```bash
# Skip the test notification after installing.
python3 <skill-root>/scripts/skill_atlas.py sync setup --confirm --no-test

# Check every 30 minutes, suppress while active for 30 minutes, repeat at most hourly,
# and digest a long-lived active state after 4 hours.
python3 <skill-root>/scripts/skill_atlas.py sync setup --confirm \
  --interval 30 --idle-minutes 30 --min-interval 60 --force-after-minutes 240 --format json
```

| Flag | Meaning |
|---|---|
| `--project PATH` | Git repository to watch. May be repeated. Defaults to the Git repository containing the current directory. |
| `--interval MINUTES` | LaunchAgent check interval in minutes (default 15). The plist uses a minimum `StartInterval` of 60 seconds. |
| `--idle-minutes MINUTES` | Suppress notifications while files or commits changed within this window (default 30). |
| `--min-interval MINUTES` | Minimum repeat interval for the same worktree state (default 60). |
| `--force-after-minutes MINUTES` | Send a digest after the same state persists this long while active (default 240; `0` disables). |
| `--confirm` | Write files, install the LaunchAgent, and run a test notification. |
| `--no-test` | Skip the post-install test notification. |
| `--format markdown\|json` | Preview/result format (default `markdown`). |

Preview and install validate every project path is a usable Git repository, and
at least one project must be given (or discoverable from the current
directory). Invalid repositories, an invalid existing registry, or a
`--confirm` run on a non-macOS system are refused with exit status 2.

## Preview

Preview prints the registry path, plist path, watched projects, and cadence. A
JSON preview also includes the exact `plist_document` that would be written:

```text
# Sync notification setup: preview
- registry: `~/.config/skill-atlas/watch.json`
- launch agent: `~/Library/LaunchAgents/com.skill-atlas.sync-notify.plist`
- projects: /Users/you/repos/one
- checks every 15 min; idle 30 min; repeat >= 60 min; digest after 240 min
- note: Preview only. Re-run with --confirm to write the registry, install the LaunchAgent and run a test notification.
```

Preview is read-only. It does not create directories or files, but it does read
an existing registry (and refuses if that file is invalid JSON) so the preview
matches what `--confirm` would merge.

## What `--confirm` writes

`--confirm` performs these steps in order:

1. Creates `~/.config/skill-atlas/watch.json` if needed and merges the requested
   project paths into its `projects` list. Existing keys are preserved; duplicate
   paths are removed while preserving order.
2. Backs up an existing registry and/or plist as
   `<filename>.bak-<YYYYMMDDTHHMMSS>` in the same directory (a numeric suffix is
   used if that timestamped backup already exists).
3. Writes
   `~/Library/LaunchAgents/com.skill-atlas.sync-notify.plist` with label
   `com.skill-atlas.sync-notify`. Its arguments run
   `skill_atlas.py sync notify --registry <watch.json> --channel macos
   --min-interval N --idle-minutes N --force-after-minutes N`;
   `StartInterval` is
   `max(60, interval_minutes × 60)`, `RunAtLoad` is false, and
   `LimitLoadToSessionType` is `Aqua`.
4. Runs `launchctl bootout gui/<uid> <plist>` (best effort) and then
   `launchctl bootstrap gui/<uid> <plist>`.
5. Unless `--no-test` is given, sends one test notification through the same
   macOS channel used by the job.

The plist directs standard output to
`~/.cache/skill-atlas/sync-notify.log` and standard error to
`~/.cache/skill-atlas/sync-notify.err`. The notification state file remains the
`sync notify` default, `~/.cache/skill-atlas/sync-notify.json`.

If `launchctl bootstrap` fails, the command reports status `error` but the
registry and plist have still been written and any backups are listed; inspect
`launchctl_output` and run `sync setup --confirm` again after fixing the cause.
A failed test notification is recorded in `test_error` and does not roll back the
installation.

## Result fields

Preview JSON:

| Key | Contents |
|---|---|
| `status` | `preview` |
| `registry`, `plist` | Paths that would be written |
| `projects` | Merged project path list |
| `interval_minutes`, `idle_minutes`, `min_interval`, `force_after_minutes` | Cadence values |
| `plist_document` | The exact LaunchAgent dictionary |
| `notes` | Preview-only reminder |

Installed/error JSON adds:

| Key | Contents |
|---|---|
| `status` | `installed` or `error` |
| `backups` | Paths of timestamped backups created this run |
| `launchctl_loaded` | Whether `launchctl bootstrap` succeeded |
| `launchctl_output` | Bootstrap/bootout output, when captured |
| `test_notification` | The `sync notify` test result, or `null` |
| `test_error` | Error from the test notification, or `null` |
| `notes` | Reminder that the job only reads local Git metadata and never pushes |

Preview, `installed`, and launchctl-error results exit with status 0; refused
requests (invalid repository or registry, or `--confirm` on a non-macOS system)
exit with status 2.

## macOS notification permission

The notification comes from `osascript`, so macOS may show **Script Editor** as
the sending app. If no banner appears:

1. Run the setup test notification again or run
   `sync notify --test-notification` directly.
2. Allow notifications for Script Editor (or the helper app macOS associates
   with it) in System Settings → Notifications.
3. Check the alert style: banners auto-dismiss quickly; alerts stay until
   dismissed.
4. Check Focus / Do Not Disturb and the notification summary settings.
5. Read the log/error files written by the job:
   `~/.cache/skill-atlas/sync-notify.log` and
   `~/.cache/skill-atlas/sync-notify.err`.

A branded, clickable notification requires a signed helper app and is future
work; this release installs the lightweight `osascript` path. See
[Sync Notifications](sync-notify.md#troubleshooting-no-notification) for more
troubleshooting and for the underlying notification behavior.

## Uninstall

Stop and remove the LaunchAgent, then remove the registry if you no longer want
the watch list:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.skill-atlas.sync-notify.plist
rm ~/Library/LaunchAgents/com.skill-atlas.sync-notify.plist
rm ~/.config/skill-atlas/watch.json          # optional: removes saved project list
rm -f ~/.cache/skill-atlas/sync-notify.log ~/.cache/skill-atlas/sync-notify.err
rm -f ~/.cache/skill-atlas/sync-notify.json  # optional: resets dedupe state
```

Backups named `*.bak-*` next to the registry/plist can be removed once you no
longer need them. Uninstalling never touches the watched Git repositories.

## Safety and privacy

- **Local files only.** Setup writes the registry and plist (and their backups)
  under your home directory. It reads local Git metadata to validate projects.
- **No network by design.** It does not fetch, push, or open a network
  connection. The installed job later runs `sync notify`, which is also offline
  unless you explicitly pass `--fetch` in a custom job.
- **No repository mutation.** No commits, branches, worktrees, or working-tree
  files are changed.
- **Local paths are sensitive.** The registry, plist, logs, and backups contain
  absolute repository paths. Treat them as local project data and avoid posting
  them publicly.
- **Explicit confirmation.** Nothing is written without `--confirm`.

## Relationship to `sync notify` and `sync status`

- [`sync notify`](sync-notify.md) performs the checks and sends the
  notification. `sync setup` only installs the schedule and configuration that
  invokes it.
- [`sync status`](cli-reference.md) is the manual, on-demand Git status check.
- `checkpoint`/`handoff` record sync warnings in the task evidence.
- The schedule belongs to macOS launchd; Skill Atlas itself remains a one-shot
  CLI with no resident background process. It never pushes automatically.

## Limitations

- **Installation is macOS-only.** `--confirm` is refused on other platforms;
  preview remains available and writes nothing.
- **launchd context matters.** The LaunchAgent runs in the user's Aqua session
  and a limited environment. Verify the job with `launchctl print`
  (`launchctl print gui/$(id -u)/com.skill-atlas.sync-notify`) and by checking
  the log/error files; a Python path that works in your shell may still fail
  under launchd.
- **launchctl can fail.** If bootstrap fails, files remain written and the
  result reports `status: "error"`; fix the cause and re-run.
- **Notification delivery is best-effort.** Permission, Focus, and alert style
  can hide the banner. A successful setup proves the files were written and
  launchctl ran, not that you saw a notification.
- **No automatic uninstall or rollback.** Use the uninstall steps above; existing
  files are backed up, not deleted.
- **Defaults differ from `sync notify`.** Setup uses a 30-minute idle window and
  a 240-minute digest backstop by default, while `sync notify` uses 0 (off) for
  both when run directly; setup writes the values into the plist.
