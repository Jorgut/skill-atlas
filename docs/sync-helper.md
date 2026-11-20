# Menu-Bar Sync Helper

`sync helper` manages an optional macOS menu-bar app that shows the current
Git-sync state for your registered repositories. It was added in `0.15.0-beta`;
`0.16.0-beta` added a dirty-file threshold, and `0.16.1-beta` rewrites the helper
to read Git directly with `/usr/bin/git` — it no longer spawns the Python CLI and
its config no longer contains Python or CLI paths.

The helper exists because notifications can be blocked, muted, or shown as
"Script Editor" banners. A menu-bar item is visible without notification
permission: it shows `SA` when everything is clean, `SA N` when N
repositories/worktrees need attention, and `SA !` when a refresh fails or a
registered repository cannot be read. The menu lists the actionable worktrees
and offers Open in Terminal, Open in Finder, **Grant file access…**, Refresh now,
Open registry, and Quit.

It is **explicitly opt-in**. Installing it is a deliberate `--confirm` action,
it runs locally after installation, and it never pushes, fetches, commits,
merges, or changes a repository.

## What it is and is not

It **is**:

- a small AppKit menu-bar app built locally from `helper/` with `swiftc`;
- a login item that launches the app, which reads the registry and runs
  `/usr/bin/git` directly every 15 minutes by default (no Python or Skill Atlas
  CLI needed at runtime);
- an alternative to OS notifications when banners are unavailable or
  unreliable;
- installed with a preview-first command and removed with a matching uninstall
  command.

It **is not**:

- a notification replacement inside the OS Notification Center — it has no
  notification permission and sends no banners;
- a background sync service: it only reads local Git state; it does not push,
  fetch, commit, or merge;
- a signed, notarized, or distributable app — the build is local and ad-hoc
  signed; signing/notarization and distribution are future work;
- an installer for the watch registry: it reads
  `~/.config/skill-atlas/watch.json`, which is normally written by
  `sync setup` (or by you, manually);
- a replacement for `sync summary`/`sync notify`; it is a read-only indicator.

## Requirements

- macOS 13 or newer (the app declares `LSMinimumSystemVersion` 13.0).
- Xcode Command Line Tools, providing `swiftc`, `codesign`, and `/usr/bin/git`.
- At install time, a Skill Atlas checkout containing `scripts/skill_atlas.py`
  and `helper/build.sh`. After installation the helper no longer needs Python,
  the CLI, or the checkout — only the app, its config, the registry, and Git.
- The helper is installed per user under `~/Applications` and
  `~/Library/Application Support`.

Check the toolchain before installing:

```bash
command -v swiftc
git --version
```

## Quickstart

Preview first. Preview writes nothing and works on any platform:

```bash
python3 <skill-root>/scripts/skill_atlas.py sync helper install
```

If you do not yet have a watch registry, create it with `sync setup` (preview,
then `--confirm`) before installing the helper:

```bash
python3 <skill-root>/scripts/skill_atlas.py sync setup --confirm
```

Then install the helper:

```bash
python3 <skill-root>/scripts/skill_atlas.py sync helper install --confirm
```

Useful variants:

```bash
# Use a different poll interval (seconds; minimum 60) and don't launch it now.
python3 <skill-root>/scripts/skill_atlas.py sync helper install --confirm \
  --interval 1800 --no-open

# Count dirty work in the badge only after 5 files (default is 20).
python3 <skill-root>/scripts/skill_atlas.py sync helper install --confirm \
  --dirty-min-files 5

# Check installation, or preview uninstall.
python3 <skill-root>/scripts/skill_atlas.py sync helper status
python3 <skill-root>/scripts/skill_atlas.py sync helper uninstall

# Actually remove the app, config and login item.
python3 <skill-root>/scripts/skill_atlas.py sync helper uninstall --confirm
```

## Install flags

| Flag | Meaning |
|---|---|
| `--confirm` | Build the app, copy it to `~/Applications`, write config and the login item, load it, and optionally open it. Without this flag the command only previews. |
| `--interval SECONDS` | Poll interval for the helper (default 900 = 15 minutes; values below 60 are raised to 60). |
| `--dirty-min-files FILES` | Include dirty worktrees in the menu only when the dirty count reaches this number (default 20; values below 1 are raised to 1). |
| `--no-open` | Do not launch the helper immediately after installing. The login item is still written. |
| `--format markdown\|json` | Output format (default `markdown`). |

`sync helper` is macOS-only for installation. A `--confirm` install on another
platform is refused with exit status 2; preview is available everywhere. A
missing `swiftc`, a failed build, or a refused install also exits 2. If
`launchctl bootstrap` fails after installation, the files are already written and
the result is `status: "error"` (the CLI itself exits 0).

## What installation writes

`sync helper install --confirm` writes:

| Path | Purpose |
|---|---|
| `~/Applications/Skill Atlas Notify.app` | The built menu-bar app (ad-hoc codesigned by the build script) |
| `~/Library/Application Support/Skill Atlas/helper.json` | Helper config: registry path, poll interval, dirty threshold |
| `~/Library/LaunchAgents/com.skill-atlas.notify-helper.plist` | Login item that opens the app with `/usr/bin/open -a` at login |

The config contains:

- `registry`: `~/.config/skill-atlas/watch.json`
- `interval`: poll interval in seconds
- `dirty_min_files`: dirty threshold (default 20)

For backward compatibility the installer also writes `state` and `log` path
fields, but the native helper does not read or write those files. There are no
Python or CLI paths in the config. The helper does not create the registry: if it
is missing or invalid, refreshes fail and the menu shows an error (`SA !`);
create the registry with `sync setup` first.

The registry must be the object form:

```json
{
  "projects": [
    "/Users/you/repos/project-a",
    "/Users/you/repos/project-b"
  ]
}
```

`sync notify` also accepts a plain JSON list, but the helper decodes the object
form only, so a hand-written list produces a "Cannot read registry" error. Use
`sync setup`, or wrap the list in `projects`.

### No backups

Installation removes an existing `Skill Atlas Notify.app` at the target path and
overwrites the config and login item without creating backups. If you have a
customized install, uninstall it first or back up those files yourself.

## First run and file access

The helper reads Git metadata directly from the registered repository folders.
macOS protects `Documents`, `Desktop`, `Downloads`, and some other locations
with TCC (Privacy & Security), so the app may be denied access even though it is
only reading Git metadata.

Two things can make the usual macOS **Allow** prompt unreliable:

- the app is an unsigned/ad-hoc local build;
- it is launched as a background login item, not by opening it from Finder.

As a result the prompt may not appear at all. The helper does not pretend
everything is clean in that case: it shows `SA !`, lists
`Cannot read <project>: ...`, and offers **Open Privacy settings…**.

Use one of these paths to grant access:

1. **From the helper menu.** Choose **Grant file access…** (`g`). This opens a
   folder picker; select the folder(s) that contain your registered repositories
   (for example `Documents`) and choose **Allow**. If macOS shows a prompt,
   allow it. If the picker closes but refreshes still fail, continue below.
2. **Manual Full Disk Access (most reliable).** Open System Settings →
   Privacy & Security → **Full Disk Access**, click **+**, choose
   `~/Applications/Skill Atlas Notify.app`, and enable it. Quit and reopen the
   helper (or use **Refresh now**) after changing access.
3. **Files and Folders.** System Settings → Privacy & Security → **Files and
   Folders**; if **Skill Atlas Notify** is listed, enable the relevant folders
   (Documents, Desktop, Downloads, etc.). Unsigned/ad-hoc apps sometimes do not
   appear here; use Full Disk Access instead.

After changing access, use **Refresh now**; if the badge is still `SA !`, quit
and relaunch the helper. You can also click **Open Privacy settings…** in the
menu to jump to the Files and Folders pane.

### If the menu-bar icon is hidden

macOS may hide status items when the menu bar is full, especially on notched
displays or with many menu-bar apps. The helper has no Dock icon, so it can be
easy to think it is not running:

- quit or hide other menu-bar items, or use a menu-bar manager;
- relaunch it with `open -a "Skill Atlas Notify"`;
- check Activity Monitor for `SkillAtlasNotify`;
- the login item relaunches it at the next login.

### Visibility: menu bar, Dock and floating badge

macOS hides menu-bar extras when the bar is crowded and hides both the menu
bar and Dock in full-screen apps. The helper therefore adds two fallbacks:

- when an issue exists it sets a Dock badge and temporarily becomes a regular
  app, so the count is visible in the Dock;
- it also shows a small floating `Skill Atlas · N` badge near the top-right
  corner. The panel is non-activating, joins all Spaces and uses
  `fullScreenAuxiliary`, so it remains visible over full-screen Chrome/Figma.

The floating badge is a clickable, high-contrast button; click it (or the Dock icon) to see the issue summary. The summary alert has OK and Later (Esc) buttons; a no-upstream line includes a push hint. When clean,
the floating badge is hidden and the Dock icon returns to accessory mode.
If you do not want the floating badge, quit the helper; the menu-bar item and
LaunchAgent remain unchanged.

## Menu behavior

The helper is an accessory app: it has no Dock icon and does not take over the
screen. Its menu contains:

- badge `SA` — all clean; `SA N` — N actionable repositories/worktrees;
  `SA !` — a refresh error or unreadable project;
- a list of actionable worktrees, each with **Open in Terminal** and
  **Open in Finder**;
- **Grant file access…** (`g`);
- skipped project errors and, when access is denied, **Open Privacy
  settings…**;
- **Refresh now** (`r`), **Open registry** (`o`), and **Quit** (`q`).

Each refresh runs `git worktree list`, then branch/upstream/ahead/behind/status
for every worktree of every registered project, using `/usr/bin/git` in that
directory. It is offline and read-only.

## Dirty threshold

The helper counts Git status entries (untracked files included; top-level
`.agent-state/` entries are ignored) and uses the `dirty_min_files` value from its config (default 20). A
worktree whose only issue is uncommitted work appears in the menu — and counts
toward `SA N` — only once its dirty count reaches the threshold. Other warnings
(unpushed commits, no upstream, behind, detached HEAD) are not
threshold-filtered.

This makes the badge a signal for *accumulating* work rather than every
in-progress edit. There is no dedupe/idle/force-after logic in the helper: each
refresh shows current state, and the threshold is the deliberate limiter. OS
notifications are separate: the `sync setup` LaunchAgent is governed by its idle,
force-after, and minimum interval settings, while the helper displays state
without notification permission.

If the helper was installed before `0.16.0-beta`, its config may not contain
`dirty_min_files` (the field is optional for compatibility); reinstall with
`sync helper install --confirm` to add the threshold.

## No notification permission, no auto-push

The menu-bar helper is not a notification. It does not request notification
permission, does not post banners, and does not depend on Notification Center or
Focus settings. It only displays state in the menu bar. Its dirty threshold
controls the menu badge, not OS notification behavior.

It never pushes, fetches, commits, merges, or deletes anything. **Open in
Terminal/Finder**, **Open registry**, **Grant file access…**, and **Refresh now**
are user-initiated actions; the helper runs no other commands.

## Status and uninstall

```bash
python3 <skill-root>/scripts/skill_atlas.py sync helper status
```

`status` reports `installed` or `not-installed` by checking the app directory;
it does not verify the running process, the launchd job, or file-access
permissions.

Uninstall is preview-first as well:

```bash
python3 <skill-root>/scripts/skill_atlas.py sync helper uninstall          # preview
python3 <skill-root>/scripts/skill_atlas.py sync helper uninstall --confirm # remove
```

`--confirm` boots out the login item, stops the helper process, and removes the
app, config, and plist. It leaves the watch registry and any legacy state/log
files in place; remove those separately if you want a full cleanup. Uninstalling
never touches the watched Git repositories.

## JSON results

Install preview:

| Key | Contents |
|---|---|
| `status` | `preview` |
| `app`, `config`, `plist` | Paths that would be written |
| `interval_seconds` | Poll interval that would be configured |
| `dirty_min_files` | Dirty threshold that would be configured |
| `notes` | Preview and file-access reminders |

Install result adds `launchctl_loaded` and `launchctl_output`; `status` is
`installed` when `launchctl bootstrap` succeeds, otherwise `error`. `status`
command returns `{status, app, config, plist}`. Uninstall preview returns
`{status: "preview", app, plist, config}`; confirmed uninstall returns
`{status: "removed", removed: [...]}`.

## Relationship to `sync notify`, `sync setup`, and `sync summary`

- The helper is now independent at runtime: it reads the registry and runs Git
  directly instead of invoking [`sync notify`](sync-notify.md). It reuses the
  same warning concepts (no upstream, unpushed commits, behind, detached, dirty
  above the threshold) and is read-only.
- [`sync setup`](sync-setup.md) installs the notification LaunchAgent and writes
  the shared `watch.json` registry. The helper reads that registry and does not
  install the notification job.
- [`sync summary`](sync-summary.md) is the compact end-of-block summary; it also
  defaults its `commit_suggested` threshold to 20 dirty files.
- [`sync status`](cli-reference.md) is the manual, one-off check.
- The helper adds a persistent menu-bar surface without notification permission;
  it is still a local UI helper, not an agent or push service. It never
  auto-pushes.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `SA !`, `Cannot read <project>` | Grant access with **Grant file access…**; if that fails, add the app to System Settings → Privacy & Security → Full Disk Access, then Refresh now (relaunch if needed). |
| No `SA` icon | The menu bar may be crowded/notched; quit other menu-bar items or relaunch with `open -a "Skill Atlas Notify"`. Check Activity Monitor for `SkillAtlasNotify`. |
| No macOS prompt appeared | Expected for some unsigned/background apps; use the manual Full Disk Access route above. |
| `Cannot read registry` | The registry is missing/invalid or is a plain JSON list; use `sync setup` or wrap paths in `{"projects": [...]}`. |
| Stale/offline counts | The helper is read-only and never fetches; `ahead`/`behind` use local tracking refs. Refresh after your own fetch. |
| Badge never counts dirty work | The dirty count is below `dirty_min_files` (default 20); reinstall with `--dirty-min-files` or commit/review the changes. |
| Helper won't build | Install Xcode Command Line Tools (`xcode-select --install`) so `swiftc` exists. |

## Limitations

- **Unsigned/ad-hoc local build.** The app is built locally and ad-hoc signed
  (`codesign --sign -`); it is not notarized or distributed. Gatekeeper and TCC
  behavior may vary, and signing/notarization is future work.
- **File access is TCC-dependent.** The helper needs access to each registered
  repository's folder. The ordinary Allow prompt may not appear for an
  unsigned/background login item; manual Full Disk Access is the reliable route.
- **macOS 13+ only.** Installation is refused on other platforms; preview is
  available anywhere.
- **No backup or rollback.** Installing removes an existing app at the target
  path and overwrites config/plist; uninstall removes them without restoring
  previous versions.
- **Build requires Xcode command-line tools.** At runtime the helper needs
  `/usr/bin/git` (also supplied by the Command Line Tools), but not Python, the
  Skill Atlas CLI, or the checkout.
- **Registry is not created.** The helper expects the object-form
  `~/.config/skill-atlas/watch.json`; a missing/invalid/list-form registry
  produces menu-bar errors.
- **Polling, not push.** Updates appear at the configured interval (default
  15 minutes) or when you choose Refresh now.
- **Menu-bar visibility is not guaranteed.** macOS can hide status items when
  space is short; the app has no Dock icon.
- **Dirty threshold is a heuristic.** The default 20 counts dirty Git entries
  (including untracked files; top-level `.agent-state/` entries are ignored), not
  changed lines or risk. Lower it for small
  projects; raise it if generated files inflate the count. It filters only dirty
  work in the menu, not other warnings.
- **No notification guarantee.** This is a menu-bar indicator, not a banner; it
  cannot wake you, interrupt Focus, or guarantee attention.
