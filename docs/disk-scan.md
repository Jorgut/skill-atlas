# Disk Usage Audit

`disk scan` is a read-only audit of the space that agent work produces locally:
agent homes, session transcripts, caches, plugins, attachments, project media,
build artifacts and Git objects. It was added in `0.9.0-beta`.

The audit reads file metadata only. It never reads file contents, credentials,
session text or account data, never follows symlinks while walking a tree, never
deletes or moves anything, and every suggestion is a plan for the user. Its job is to show where
space goes and how risky each candidate is before anyone cleans anything up.

## What the audit does and does not prove

The audit reports:

- which known agent roots exist under `--home`, plus any repeated `--root`
  directories and one optional `--project` directory;
- apparent sizes per root, per direct child entry, and per category;
- the largest files at or above a size threshold (`--min-file-mb`, default
  200 MB);
- a category and risk level for every reported entry;
- a **suggested review** list with one suggested action per category; and
- explicit limitations in every result.

The audit does **not** prove:

- how much disk space deleting an entry would actually free — reported sizes are
  apparent file sizes, and compression, clones, snapshots and hard links can make
  the real reclaimable space different;
- that a candidate is safe to remove — categories and risks are name-based
  heuristics, not an inspection of the data;
- that a large file is unused, stale, or duplicated;
- that the scan covers the whole machine — known roots are discovery hints, and
  linked roots or external volumes are not followed;
- that any suggested action has been or will be performed.

Missing or unreadable paths are skipped and reported; they do not abort the
audit.

## Quickstart

Run from any directory. Markdown is the default output.

```bash
# Audit the default known agent roots under the current user's home.
python3 <skill-root>/scripts/skill_atlas.py disk scan

# Add explicit directories, for example large document or chat folders.
python3 <skill-root>/scripts/skill_atlas.py disk scan \
  --root ~/Documents/ChatGPT --root ~/Documents/Codex

# Include a project checkout, lower the largest-file threshold, list more files.
python3 <skill-root>/scripts/skill_atlas.py disk scan \
  --project . --min-file-mb 100 --top 30

# Machine-readable result for review notes or automation.
python3 <skill-root>/scripts/skill_atlas.py disk scan --format json
```

The command is safe to run repeatedly: it creates and changes no state.

| Flag | Meaning |
|---|---|
| `--home PATH` | Home directory whose known agent roots are audited. Defaults to the current user's home. |
| `--root PATH` | Additional directory to audit. May be repeated. |
| `--project PATH` | Optional project directory to include in the audit. |
| `--top N` | Number of largest files to report (default 15; bounded to 0–100). |
| `--min-file-mb N` | Report files at or above this size in MB (default 200). `0` includes every file size. |
| `--max-entries N` | Per-root safety limit on filesystem entries (default 400000, minimum 1000). When hit, that root is marked truncated and its sizes are incomplete. |
| `--format markdown\|json` | Markdown report (default) or the full result object. |

`--root` and `--project` are added to the default scope. If one requested root
is inside another, only the outermost is scanned so space is not counted twice;
the skipped nested roots are listed in `nested_roots_skipped`. Requested roots
that do not exist are omitted rather than reported as empty.

## Known roots

The default scope is a fixed set of agent homes resolved under `--home`; only
roots that exist are reported. "Documented" paths mirror this repository's
documentation; "candidate" paths are discovery hints that should be verified
against the tool's installed version.

| ID | Label | Path under `--home` | Evidence |
|---|---|---|---|
| `codex` | Codex home | `.codex` | documented |
| `claude-code` | Claude Code home | `.claude` | documented |
| `deepseek-harness` | DeepSeek Harness home | `.dsh` | documented |
| `cc-switch` | CC Switch skills | `.cc-switch` | candidate |
| `opencode` | OpenCode config | `.config/opencode` | candidate |
| `workbuddy` | WorkBuddy home | `.workbuddy` | candidate |
| `kimi-code` | Kimi Code home | `.kimi-code` | candidate |
| `cursor` | Cursor home | `.cursor` | candidate |
| `xcode-developer` | Xcode developer data | `Library/Developer/Xcode` | candidate |

`--root` entries appear with source `argument`; `--project` appears with source
`project`. Known roots use source `known-root`.

## Categories, risk and suggested actions

Classification uses entry names and the nearest meaningful parent directory
name. File contents are never inspected, so a category is a heuristic, not a
fact about the file.

| Category | Risk | What it usually contains | Suggested action |
|---|---|---|---|
| `agent-cache` | low | Regenerable caches and generated images, including names such as `cache`, `caches`, `.cache`, `.tmp`, `tmp`, `temp`, `computer-use`, `visualizations`, `generated_images`, `codingassistant` | Regenerable cache: close the owning tool before removing it. |
| `build-artifact` | low | Rebuildable output such as `node_modules`, `.build`, `build`, `dist`, `target`, `DerivedData`, `__pycache__`, `.next`, `.venv`, `venv`, `Pods`, `.gradle`, `.turbo`, `.parcel-cache` | Regenerable build output: rebuild when needed. |
| `agent-session` | medium | Session transcripts and history, including names such as `sessions`, `archived_sessions`, `projects`, `transcripts`, `rollouts`, `history`, `threads`, or a name starting with `session` | Review age and keep what matters: archive old sessions elsewhere or prune them with the tool's own controls. |
| `agent-attachment` | medium | Uploaded or attached session files: `attachments`, `uploads` | Review old session attachments; keep only what is needed. |
| `plugin-package` | medium | Plugins and package caches: `plugins`, `packages`, `extensions` | Plugins and package caches are usually reinstallable; check for local development plugins first. |
| `archive` | medium | Backups and old copies: `archive`, `archives`, `backups`, `backup`, `old` | Move to external storage or delete only after verifying the archive is not the only copy. |
| `project-media` | medium | Media directories (`media`, `audio`, `video`, `videos`, `renders`, `exports`, `footage`, `images`, `photos`) and media files such as `.wav`, `.mp3`, `.mp4`, `.mov`, `.psd`, `.aep`, `.dng`, `.raw` | Move finished media to external storage; keep the final exports and remove intermediate renders. |
| `git-object` | high | Anything under a `.git` directory | Never delete directly: migrate large media with Git LFS or start a new history without it. |
| `database` | high | Database files (`.sqlite`, `.sqlite3`, `.db`, `.db-wal`, `.db-shm`) and names starting with `thread_history` | Never delete: back it up first and consider the tool's own maintenance command (for example VACUUM). |
| `other` | medium | Anything not matched above | Review manually; nothing is recommended automatically. |

Risk levels mean:

- **low** — usually regenerable, but confirm the owning tool is closed and the
  data can be rebuilt.
- **medium** — may contain sessions, user media, plugins, archives or other work
  worth keeping; review before acting.
- **high** — databases and Git objects; direct deletion can lose history or
  state. Back up first and use the owning tool's maintenance path.

Only direct children of scanned roots become **suggested review** candidates
(`other` is excluded). The summary's low/medium/high-risk byte totals are sums
of those direct-child candidates, not of the whole disk and not of the largest
files list. Every suggestion is plan-only text; the audit has no delete, move,
compress or archive command.

## Reading the report

Markdown output has these sections:

- **Summary** — existing roots scanned, total apparent size, file count, and
  low/medium/high-risk candidate totals.
- **Roots** — one `### <label> — <size>` block per existing root, with its path,
  file count, notes for truncated or unreadable entries, and up to the 8 largest
  direct children with category and risk.
- **Largest files** — files at or above `--min-file-mb`, up to `--top` entries,
  with inherited category and risk.
- **Suggested review** — up to 20 reclaimable direct-child candidates, each with
  a suggested action.
- **Limitations** — the fixed caveat list.

JSON output has `schema_version` (currently `1`):

| Key | Contents |
|---|---|
| `scan` | `home`, `project` (or `null`), `generated_at`, `top_files`, `min_file_mb` |
| `roots` | Array of scanned roots: `id`, `label`, `evidence`, `source`, `path`, `exists`, `size_bytes`, `files`, `entries`, `categories`, `skipped`, `symlinks_skipped`, `truncated` |
| `top_files` | Array of `{path, size_bytes, modified_at, category, risk}` |
| `reclaimable` | Array of `{path, size_bytes, category, risk, suggested_action, root_id}`; contains every direct-child candidate, while Markdown shows up to 20 |
| `nested_roots_skipped` | Existing requested or known roots skipped because a parent root already covers them |
| `summary` | `roots_scanned`, `total_bytes`, `files`, `low_risk_bytes`, `medium_risk_bytes`, `high_risk_bytes` |
| `limitations` | Fixed list of limitation strings |

Root `entries` are direct children with `name`, `path`, `is_dir`, `size_bytes`,
`files`, `category` and `risk`. `categories` aggregates the children's sizes by
category. `skipped` counts unreadable entries; `symlinks_skipped` counts
symlinks that were not followed.

### Worked example output

Sanitized excerpt from a real run on a development machine: paths are replaced
with `/home/you`, and some root blocks are elided. This run found 8 existing
roots, 275,644 files and a total apparent size of 23.1 GiB (24,773,799,062
bytes, about 24.8 GB decimal).

```text
# Disk scan

- home: `/home/you`
- generated: 2026-11-11T20:42:31.000792+00:00

## Summary

- roots scanned: 8
- total: 23.1 GiB
- files: 275644
- low-risk candidates: 2.3 GiB
- medium-risk candidates: 15.5 GiB
- high-risk candidates: 3.7 GiB

## Roots

### Codex home — 15.7 GiB

- path: `/home/you/.codex`
- files: 44853
- `sessions` — 7.9 GiB (agent-session, medium risk)
- `thread_history_1.sqlite` — 3.5 GiB (database, high risk)
- `archived_sessions` — 916.2 MiB (agent-session, medium risk)
- `packages` — 746.4 MiB (plugin-package, medium risk)
- `visualizations` — 683.2 MiB (agent-cache, low risk)
- `plugins` — 565.6 MiB (plugin-package, medium risk)
- `generated_images` — 401.5 MiB (agent-cache, low risk)
- `worktrees` — 294.3 MiB (other, medium risk)

### Claude Code home — 2.9 GiB

- path: `/home/you/.claude`
- files: 141644
- `plugins` — 2.8 GiB (plugin-package, medium risk)
- `transcripts` — 68.6 MiB (agent-session, medium risk)
- `projects` — 62.8 MiB (agent-session, medium risk)
- `skills` — 13.5 MiB (other, medium risk)
- `cache` — 455.1 KiB (agent-cache, low risk)
...

# ... other existing roots elided ...

## Largest files

- `/home/you/.codex/thread_history_1.sqlite` — 3.5 GiB (database, high risk)
- `/home/you/.codex/sessions/2026/11/03/rollout-...jsonl` — 1.1 GiB (agent-session, medium risk)
- `/home/you/.codex/sessions/2026/08/05/rollout-...jsonl.zst` — 651.5 MiB (agent-session, medium risk)
- `/home/you/.codex/sessions/2026/10/26/rollout-...jsonl` — 439.1 MiB (agent-session, medium risk)
- `/home/you/.codex/plugins/.../codex` — 261.0 MiB (plugin-package, medium risk)
...

## Suggested review

- 7.9 GiB — agent-session / medium risk: `/home/you/.codex/sessions`
  - Review age and keep what matters: archive old sessions elsewhere or prune them with the tool's own controls.
- 3.5 GiB — database / high risk: `/home/you/.codex/thread_history_1.sqlite`
  - Never delete: back it up first and consider the tool's own maintenance command (for example VACUUM).
- 2.8 GiB — plugin-package / medium risk: `/home/you/.claude/plugins`
  - Plugins and package caches are usually reinstallable; check for local development plugins first.
- 1.6 GiB — plugin-package / medium risk: `/home/you/.cursor/extensions`
  - Plugins and package caches are usually reinstallable; check for local development plugins first.
- 916.2 MiB — agent-session / medium risk: `/home/you/.codex/archived_sessions`
  - Review age and keep what matters: archive old sessions elsewhere or prune them with the tool's own controls.
...

## Limitations

- Sizes are apparent file sizes; APFS compression, clones, snapshots and hard links can change the real reclaimable space.
- Only metadata was read: no file contents, credentials, session text or account data were read, stored or uploaded.
- Directory symlinks are never followed, so linked roots and external volumes are not counted.
- Known roots are discovery hints and may be version-specific; paths that do not exist are omitted.
- The audit is read-only. It never deletes, moves, compresses or archives anything; every suggestion is a plan for the user.
- Database and Git object sizes are reported for awareness only; deleting them directly can lose history or state.
```

The largest entries are sessions and a database under the Codex home, plugin
packages under Claude Code and Cursor, and build/cache output under Xcode. The
audit ranks and labels them; it does not decide that any of them should be
removed.

## Safety and privacy

- **Metadata only.** The scan reads names, sizes and modification times. It does
  not read file contents, credentials, session transcripts, account data or
  configuration values.
- **No network.** Nothing is uploaded, and no remote service is contacted.
- **No writes.** The audit never deletes, moves, compresses, archives, links or
  repairs anything. Suggestions are text for a human review.
- **No symlink following during traversal.** Symlinked files and directories
  encountered while walking a root are skipped and counted, so linked trees and
  external volumes are not traversed. Paths you pass explicitly as `--home`,
  `--root` or `--project` are normalized first, so a symlinked root is scanned
  at its resolved target.
- **Sensitive paths.** Output contains absolute home and project paths, which can
  reveal which tools and projects you use. Redact paths before sharing scan
  output publicly or attaching it to an issue.
- **Not a cleanup tool.** Use it to decide *what to review*; perform any cleanup
  with the owning tool's own controls, after a backup, and with explicit user
  authorization.

## Limitations

The fixed caveats in every result, restated:

1. **Sizes are apparent file sizes.** APFS compression, clones, snapshots and
   hard links can change the real reclaimable space; the total is not a promise
   of what deletion would free.
2. **Only metadata was read.** No file contents, credentials, session text or
   account data were read, stored or uploaded.
3. **Directory symlinks are never followed during traversal.** Linked roots and
   external volumes are not counted; only a root path passed explicitly is
   resolved before scanning.
4. **Known roots are discovery hints.** They may be version-specific, and paths
   that do not exist are omitted.
5. **The audit is read-only.** It never deletes, moves, compresses or archives
   anything; every suggestion is a plan for the user.
6. **Database and Git object sizes are reported for awareness only.** Deleting
   them directly can lose history or state.

Additional practical caveats:

- Classification is name-based and can be wrong. Verify a candidate by opening
  its directory and checking the owning tool's documentation before acting.
- A per-root entry limit (`--max-entries`, default 400000) can mark a large root
  `truncated`; its sizes are then incomplete.
- The largest-files list only includes files at or above `--min-file-mb`, and
  only files encountered during the scan; symlinks and unreadable entries are
  not included.
- Top-file categories are inherited from the nearest meaningful parent
  directory, so a large file inside a classified directory can carry that
  directory's category.

To act on a result, start with the **Suggested review** list, verify the owning
tool and file age, back up anything that may matter, and use the tool's own
prune, cache-clear or maintenance command. Never delete a database or `.git`
objects directly.

## Relation to the other read-only audits

- [`agents scan`](agent-environments.md) reports which agent tools, rule roots,
  skill roots and Skill Atlas copies exist, and flags version mismatch. It
  answers "what is configured here?"; `disk scan` answers "what is using space?".
- [`projects audit`](project-root-audit.md) groups duplicated project copies,
  hashes project documents and flags nested roots. It answers "which copy is
  which?"; `disk scan --project .` adds a size view for one project but does not
  group copies, compare documents or recommend consolidation.
- All three are read-only, run locally, and produce plans rather than changes.
  A typical review is: `agents scan` to see the environment, `projects audit` to
  understand copies, then `disk scan` to see where space goes before deciding
  what to archive or prune with the owning tools.
