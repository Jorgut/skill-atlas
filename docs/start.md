# First-Run Tour

`start` is an explicit first-run tour added in `0.14.0-beta`. It prints a short
welcome, the version of the installed Skill Atlas copy, five safe starting
commands, links to the detailed workflow guides, the safety rules, and a
suggested order for the first session.

The command is **explicit only**. It is not a popup, tray app, daemon, installer,
or scan: nothing runs until someone invokes it, and invoking it changes nothing
on disk.

## What it is and is not

It **is**:

- a one-shot, static tour for a person or agent who just installed Skill Atlas;
- a safe starting point that lists read-only commands before optional setup;
- available as Markdown for people and JSON for scripts or agents.

It **is not**:

- an automatic first-run popup — agent skills cannot open UI by themselves, so a
  person or the current agent must ask for it;
- a machine scan: it does not inspect your tools, projects, disk, or Git state;
- a substitute for the workflow guides, which explain each command in detail;
- a permission or confirmation mechanism: commands in the tour still follow their
  own read-only/`--confirm` rules.

## Quickstart

```bash
# Human-readable tour (default).
python3 <skill-root>/scripts/skill_atlas.py start

# Machine-readable tour.
python3 <skill-root>/scripts/skill_atlas.py start --format json
```

Run it right after installation. The tour itself always prints the same content;
the `version` field comes from the installed copy's `skill.json`, so it reflects
the copy you invoked, not necessarily the latest release.

The first command it suggests uses `agents scan` without a path. When you run the
project audit it suggests, replace `<path>` with a real project directory.

## What the tour prints

The Markdown output has a title, version, one-paragraph summary, and four
sections:

| Section | Contents |
|---|---|
| `## Quickstart` | Five commands, each with a one-line purpose |
| `## Workflows` | Links to the workflow guides (GitHub `main` URLs) |
| `## Safety` | Read-only default, no automatic push/commit/fetch/merge/deletion, disk cleanup moves only selected low/medium-risk paths to Trash, runtime loading is never claimed from file evidence |
| `## Suggested order` | Run `agents scan` first, audit projects, review disk before cleanup, then add push reminders |

The five quickstart commands are:

1. `python3 scripts/skill_atlas.py agents scan` — see which agent tools and Skill
   Atlas copies exist.
2. `python3 scripts/skill_atlas.py projects audit --project <path>` — find
   duplicate project copies and drifted project documents.
3. `python3 scripts/skill_atlas.py disk scan --min-file-mb 100` — find what agent
   work uses on disk; cleanup is opt-in.
4. `python3 scripts/skill_atlas.py sync status --project .` — check unpushed
   commits, missing upstream, behind-remote, and dirty state.
5. `python3 scripts/skill_atlas.py sync setup --project . --confirm` — install
   the optional macOS push reminder (preview without `--confirm`).

Note that the fifth command is the only one that writes anything (a local
registry and LaunchAgent). Run `sync setup` without `--confirm` first, and skip
it if you are not on macOS.

## JSON shape

`start --format json` returns:

| Key | Contents |
|---|---|
| `version` | Version from the invoked copy's `skill.json` |
| `title` | `Welcome to Skill Atlas` |
| `summary` | One-paragraph description |
| `quickstart` | Array of `{command, purpose}` objects (five entries) |
| `workflows` | Array of `{name, doc}` objects; `doc` is an absolute GitHub URL |
| `safety` | Array of safety-rule strings |
| `next_steps` | Array of suggested-order strings |

The JSON is static apart from `version`; it contains no machine-specific paths,
counts, or scan results.

## Why it is explicit

Agent skills are instructions and scripts, not applications. A skill cannot open
a window, notification, or terminal prompt by itself, and Skill Atlas does not
install a background service or hook that could do so. The `start` command exists
so that a person can ask for orientation, or a current agent can run it when the
user says "I just installed this" or "where do I start?" — then follow the
suggested order.

This also keeps first contact safe: the tour makes no scans, no network calls,
and no changes; the commands it recommends follow their own review and
confirmation rules.

## Suggested first 10 minutes

1. Run `start` and read the tour.
2. Run `agents scan` to see which tools and copies exist. Treat the result as
   file evidence, not proof of runtime loading.
3. Run `projects audit --project <one real project>` to check for duplicate
   copies and drifted `AGENTS.md` / `CLAUDE.md` / state documents.
4. If disk space matters, run `disk scan`, review the largest entries, and only
   then decide whether any opt-in cleanup is appropriate.
5. Run `sync status --project .` before a handoff. On macOS, preview
   `sync setup` and use `--confirm` only if you want the scheduled reminder.
6. Open the linked workflow guides for the parts you plan to use. See
   [Start here](../README.md#start-here) or the guides directly:
   [agent scan](agent-environments.md), [project audit](project-root-audit.md),
   [disk scan](disk-scan.md), [sync notifications](sync-notify.md), and
   [sync setup](sync-setup.md).

## Relationship to other docs

- [`agents scan`](agent-environments.md) reports tool, rule, skill, and Skill
  Atlas copy evidence.
- [`projects audit`](project-root-audit.md) groups likely project duplicates and
  compares project documents.
- [`disk scan`](disk-scan.md) audits disk use and supports opt-in Trash cleanup.
- [`sync status`](sync-notify.md) shows the Git sync state; [`sync setup`](sync-setup.md)
  installs the optional macOS reminder job.
- [Installation and Development Layout](development-layout.md) explains which
  copy belongs where.

## Limitations

- **Static content.** The tour does not know whether you have used Skill Atlas
  before, which tools are installed, or whether a repository is clean. Use the
  scans for facts.
- **Version comes from the invoked copy.** Running `start` from an old installation
  reports that copy's version even if a newer release exists elsewhere.
- **Workflow links are remote.** The printed links point at
  `https://github.com/Jorgut/skill-atlas/blob/main/docs/...`, so opening them
  needs a browser/network and may describe a newer version than the copy you
  invoked.
- **One suggested command writes.** `sync setup --confirm` installs a macOS
  LaunchAgent and sends a test notification unless `--no-test` is used. Preview
  it first; the command's own rules still apply.
- **No auto-run.** Nothing triggers the tour. If the user asks for orientation,
  run it explicitly; do not assume it appeared on its own.

## Safety and privacy

`start` reads only the invoked copy's `skill.json` to fill `version`, prints
static text, and opens nothing. It does not scan the machine, read project files,
open a network connection, execute other Skill Atlas commands, or change any
configuration. The workflow links are plain URLs and are not fetched by the
command.
