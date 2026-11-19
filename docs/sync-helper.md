# Menu-Bar Sync Helper

`sync helper` manages an optional macOS menu-bar app that shows the current
Git-sync state for your registered repositories. It was added in `0.15.0-beta`.

The helper exists because notifications can be blocked, muted, or shown as
"Script Editor" banners. A menu-bar item is visible without notification
permission: it shows `SA` when everything is clean, `SA N` when N
repositories/worktrees need attention, and `SA !` when a refresh fails. The
menu lists the actionable worktrees and offers Open in Terminal, Open in Finder,
Refresh now, Open registry, and Quit.

It is **explicitly opt-in**. Installing it is a deliberate `--confirm` action,
it runs locally after installation, and it never pushes, fetches, commits,
merges, or changes a repository.

## What it is and is not

It **is**:

- a small AppKit menu-bar app built locally from `helper/` with `swiftc`;
- a login item that launches the app, which polls `sync notify --channel json`
  every 15 minutes by default and renders the result;
- an alternative to OS notifications when banners are unavailable or
  unreliable;
- installed with a preview-first command and removed with a matching uninstall
  command.

It **is not**:

- a notification replacement inside the OS Notification Center — it has no
  notification permission and sends no banners;
- a background sync service: it only reads local Git state through
  `sync notify`; it does not push, fetch, commit, or merge;
- a signed, notarized, or distributable app — the build is local and ad-hoc
  signed; signing/notarization and distribution are future work;
- an installer for the watch registry: it reads
  `~/.config/skill-atlas/watch.json`, which is normally written by
  `sync setup` (or by you, manually).

## Requirements

- macOS 13 or newer (the app declares `LSMinimumSystemVersion` 13.0).
- Xcode Command Line Tools, providing `swiftc` and `codesign`.
- A Skill Atlas checkout that stays available after installation: the app's
  config points at the current `skill_atlas.py` and Python interpreter.
- The helper is installed per user under `~/Applications` and
  `~/Library/Application Support`.

Check the toolchain before installing:

```bash
command -v swiftc
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
| `~/Library/Application Support/Skill Atlas/helper.json` | Helper config: Python path, CLI path, registry/state/log paths, poll interval |
| `~/Library/LaunchAgents/com.skill-atlas.notify-helper.plist` | Login item that opens the app with `/usr/bin/open -a` at login |

The config points at:

- registry: `~/.config/skill-atlas/watch.json`
- state: `~/.cache/skill-atlas/helper-state.json`
- log: `~/.cache/skill-atlas/helper.log`

The helper does not create the registry. If the registry is missing or invalid,
refreshes fail and the menu shows an error (`SA !`); create the registry with
`sync setup` first.

### No backups

Installation removes an existing `Skill Atlas Notify.app` at the target path and
overwrites the config and login item without creating backups. If you have a
customized install, uninstall it first or back up those files yourself.

## First run and file access

On first launch, macOS may show a one-time file-access prompt because the
helper's child process reads Git metadata in the registered project folders.
Allow access for the helper/Python process; otherwise refreshes show an error and
the badge remains `SA !`.

The helper is a menu-bar (accessory) app: it has no Dock icon and does not take
over the screen. Its menu is built from `sync notify --channel json`:

- badge `SA` — all clean; `SA N` — N actionable repositories/worktrees;
  `SA !` — refresh failed;
- a list of actionable worktrees, each with **Open in Terminal** and
  **Open in Finder**;
- **Refresh now** (`r`), **Open registry** (`o`), and **Quit** (`q`).

The helper invokes `sync notify` with `--min-interval 0 --idle-minutes 0` so the
badge reflects current state instead of notification suppression. It does not
pass `--fetch`, so every refresh is offline; the helper never opens a network
connection by itself.

## No notification permission, no auto-push

The menu-bar helper is not a notification. It does not request notification
permission, does not post banners, and does not depend on Notification Center or
Focus settings. It only displays state in the menu bar.

It never pushes, fetches, commits, merges, or deletes anything. **Open in
Terminal/Finder** and **Open registry** are user-initiated UI actions; the helper
does not run other commands on its own.

## Status and uninstall

```bash
python3 <skill-root>/scripts/skill_atlas.py sync helper status
```

`status` reports `installed` or `not-installed` by checking the app directory;
it does not verify the running process or the launchd job.

Uninstall is preview-first as well:

```bash
python3 <skill-root>/scripts/skill_atlas.py sync helper uninstall          # preview
python3 <skill-root>/scripts/skill_atlas.py sync helper uninstall --confirm # remove
```

`--confirm` boots out the login item, stops the helper process, and removes the
app, config, and plist. It leaves the watch registry, helper state, and log in
place; remove those separately if you want a full cleanup. Uninstalling never
touches the watched Git repositories.

## JSON results

Install preview:

| Key | Contents |
|---|---|
| `status` | `preview` |
| `app`, `config`, `plist` | Paths that would be written |
| `interval_seconds` | Poll interval that would be configured |
| `notes` | Preview and file-access reminders |

Install result adds `launchctl_loaded` and `launchctl_output`; `status` is
`installed` when `launchctl bootstrap` succeeds, otherwise `error`. `status`
command returns `{status, app, config, plist}`. Uninstall preview returns
`{status: "preview", app, plist, config}`; confirmed uninstall returns
`{status: "removed", removed: [...]}`.

## Relationship to `sync notify`, `sync setup`, and `sync status`

- [`sync notify`](sync-notify.md) does the Git checks and formatting; the helper
  runs it with JSON output and displays the result.
- [`sync setup`](sync-setup.md) installs the notification LaunchAgent and writes
  the shared `watch.json` registry. The helper reads that registry and does not
  install the notification job.
- [`sync status`](cli-reference.md) is the manual, one-off check.
- The helper adds a persistent menu-bar surface without notification permission;
  it is still a local UI helper, not an agent or push service. It never
  auto-pushes.

## Permission error state

If a registered repository lives under `Documents`, `Desktop` or another
protected folder and macOS denies access, the helper does not pretend
everything is clean. It shows `SA !`, lists `Cannot read <project>: ...`,
and offers **Open Privacy settings…** (`Privacy & Security → Files and
Folders`). The first launch normally shows an **Allow** prompt for the
same reason. Grant access to *Skill Atlas Notify*, then use **Refresh now**.

## Limitations

- **Unsigned/ad-hoc local build.** The app is built locally and ad-hoc signed
  (`codesign --sign -`); it is not notarized or distributed. Gatekeeper behavior
  may vary, and signing/notarization is future work.
- **macOS 13+ only.** Installation is refused on other platforms; preview is
  available anywhere.
- **No backup or rollback.** Installing removes an existing app at the target
  path and overwrites config/plist; uninstall removes them without restoring
  previous versions.
- **Requires Xcode command-line tools and `swiftc`.** Build failures are reported
  with the build output.
- **Registry is not created.** The helper expects
  `~/.config/skill-atlas/watch.json`; a missing/invalid registry produces
  menu-bar errors.
- **Python/CLI path captured at install time.** Moving the Skill Atlas checkout,
  Python installation, or the config file can break refreshes; reinstall after
  moving them.
- **Polling, not push.** Updates appear at the configured interval (default
  15 minutes) or when you choose Refresh now.
- **Log growth.** Each actionable refresh can append to
  `~/.cache/skill-atlas/helper.log`; clean refreshes write nothing. Remove or
  rotate the log if it grows.
- **No notification guarantee.** This is a menu-bar indicator, not a banner; it
  cannot wake you, interrupt Focus, or guarantee attention.
