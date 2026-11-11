# Disk Usage Audit

`disk scan` audits the space that agent work produces locally: agent homes,
session transcripts, caches, plugins, attachments, project media, build
artifacts and Git objects. It was added in `0.9.0-beta`; since `0.9.1-beta` it
reports both apparent and allocated sizes, and `0.10.0-beta` adds an explicit,
opt-in Trash cleanup path.

Every result reports two sizes. **Allocated size** (`st_blocks × 512`) is the
real disk usage; **apparent size** (`st_size`) is the logical file length and
can be much larger for sparse files. When the two differ, sizes are printed as
`<allocated> allocated (<apparent> apparent)`. The largest-files threshold,
reclaimable ordering and risk totals all use allocated bytes.

The audit reads file metadata only. It never reads file contents, credentials,
session text or account data and never follows symlinks while walking a tree.
By default it never moves or deletes anything and every suggestion is a plan for
the user. Only the explicit `--apply --to-trash --confirm` combination moves
selected low/medium risk candidates into a trash directory; permanent deletion
and `rm -rf` are never used. Its job is to show where space goes and how risky
each candidate is before anyone cleans anything up.

## What the audit does and does not prove

The audit reports:

- which known agent roots exist under `--home`, plus any repeated `--root`
  directories and one optional `--project` directory;
- apparent and allocated sizes per root and per direct child entry, plus
  allocated totals per category;
- the largest files whose allocated size is at or above a size threshold
  (`--min-file-mb`, default 200 MB);
- a category and risk level for every reported entry;
- a **suggested review** list with one suggested action per category; and
- explicit limitations in every result.

With `--apply --to-trash --confirm`, it can also move selected low/medium risk
direct-child candidates into a trash directory and report the result.

The audit does **not** prove:

- how much disk space deleting an entry would actually free — allocated size is
  real disk consumption, but APFS clones, snapshots, hard links and filesystem
  behavior can still make reclaimable space differ;
- that moving a path to Trash frees space immediately — the space is released
  only after the Trash is emptied, and this tool never empties it;
- which size is meaningful for a given file — allocated size shows disk
  consumption, while apparent size shows logical length and can be far larger
  for sparse files;
- that a candidate is safe to remove or move to Trash — categories and risks
  are name-based heuristics, not an inspection of the data;
- that a large file is unused, stale, or duplicated;
- that the scan covers the whole machine — known roots are discovery hints, and
  linked roots or external volumes are not followed;
- that any suggested action has been or will be performed; in particular,
  `--apply` results are direct moves to Trash, not permanent deletion.

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

# Opt-in: move selected low/medium-risk candidates to Trash. Review first.
python3 <skill-root>/scripts/skill_atlas.py disk scan --apply --to-trash --confirm
```

The command is safe to run repeatedly without `--apply --to-trash --confirm`:
it creates and changes no state.

| Flag | Meaning |
|---|---|
| `--home PATH` | Home directory whose known agent roots are audited. Defaults to the current user's home. |
| `--root PATH` | Additional directory to audit. May be repeated. |
| `--project PATH` | Optional project directory to include in the audit. |
| `--top N` | Number of largest files to report, ranked by allocated size (default 15; bounded to 0–100). |
| `--min-file-mb N` | Report files whose allocated size is at or above this size in MB (default 200). `0` includes every file size. |
| `--max-entries N` | Per-root safety limit on filesystem entries (default 400000, minimum 1000). When hit, that root is marked truncated and its sizes are incomplete. |
| `--apply` | Opt-in move step. Requires `--to-trash` and `--confirm`; without all three flags nothing is moved. |
| `--to-trash` | Move selected low/medium risk candidates into the trash directory. Permanent deletion is not supported. |
| `--confirm` | Explicit confirmation for `--apply`. |
| `--risk low\|medium` | Cleanup risk to move. May be repeated. Default: `low`. High risk is not selectable. |
| `--trash-dir PATH` | Destination trash directory (default `~/.Trash`). Must already exist; mainly for tests and external volumes. |
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
(`other` is excluded), ranked by allocated size. The summary's
low/medium/high-risk byte totals are allocated-byte sums of those direct-child
candidates, not of the whole disk and not of the largest files list. Every
suggestion is plan-only text; the audit has no delete, move, compress or archive
command.

## Reading the report

Markdown output has these sections:

- **Summary** — existing roots scanned, total allocated size (with apparent size
  when different), file count, and allocated low/medium/high-risk candidate
  totals.
- **Roots** — one `### <label> — <size>` block per existing root, with its path,
  file count, notes for truncated or unreadable entries, and up to the 8 largest
  direct children ranked by allocated size, with category and risk.
- **Largest files** — files whose allocated size is at or above `--min-file-mb`,
  up to `--top` entries, ranked and thresholded by allocated size, with inherited
  category and risk.
- **Suggested review** — up to 20 reclaimable direct-child candidates ranked by
  allocated size, each with a suggested action.
- **Applied** — only with `--apply`: status, trash directory, selected risks,
  number of moved entries, reclaimed allocated bytes, each moved/skipped/failed
  path and its reason, and a reminder to empty the Trash.
- **Limitations** — the fixed caveat list.

JSON output has `schema_version` (currently `1`):

| Key | Contents |
|---|---|
| `scan` | `home`, `project` (or `null`), `generated_at`, `top_files`, `min_file_mb`, `min_file_basis` (`"allocated_bytes"`) |
| `roots` | Array of scanned roots: `id`, `label`, `evidence`, `source`, `path`, `exists`, `size_bytes`, `allocated_bytes`, `files`, `entries`, `categories`, `skipped`, `symlinks_skipped`, `truncated` |
| `top_files` | Array of `{path, size_bytes, allocated_bytes, modified_at, category, risk}` |
| `reclaimable` | Array of `{path, size_bytes, allocated_bytes, category, risk, suggested_action, root_id}`; contains every direct-child candidate, while Markdown shows up to 20 |
| `nested_roots_skipped` | Existing requested or known roots skipped because a parent root already covers them |
| `apply` | Present only with `--apply`: `{status, trash_dir, selected_risks, moved, skipped, failed, reclaimed_allocated_bytes}`. `status` is `applied` when at least one path moved, otherwise `no-candidates` |
| `summary` | `roots_scanned`, `total_bytes`, `total_allocated_bytes`, `files`, `low_risk_bytes`, `medium_risk_bytes`, `high_risk_bytes`; the risk totals are allocated bytes only |
| `limitations` | Fixed list of limitation strings |

Root `entries` are direct children with `name`, `path`, `is_dir`, `size_bytes`,
`allocated_bytes`, `files`, `category` and `risk`. `categories` aggregates the
children's allocated bytes by category (`{category, allocated_bytes}`).
`skipped` counts unreadable entries; `symlinks_skipped` counts symlinks that
were not followed.

### Worked example output

A run that added extra roots on the machine that motivated this change reported
**96.9 GB apparent and 59.0 GB allocated across 10 roots**. Xcode developer data
was the clearest sparse-file case: **38.25 GiB apparent but only 1.27 GiB
allocated**. The report prints allocated size first whenever it differs from
apparent size; this is a sanitized excerpt from another real run (paths
replaced, roots elided):

```text
# Disk scan

- home: `/home/you`
- generated: 2026-11-11T21:33:20.938118+00:00

## Summary

- roots scanned: 8
- total: 22.9 GiB allocated (22.3 GiB apparent)
- files: 242428
- low-risk candidates: 1.6 GiB
- medium-risk candidates: 16.0 GiB
- high-risk candidates: 3.7 GiB

## Roots

### Claude Code home — 3.3 GiB allocated (2.9 GiB apparent)

- path: `/home/you/.claude`
- files: 141644
- `plugins` — 3.2 GiB allocated (2.8 GiB apparent) (plugin-package, medium risk)
- `transcripts` — 71.3 MiB allocated (68.6 MiB apparent) (agent-session, medium risk)
- `projects` — 62.8 MiB allocated (62.8 MiB apparent) (agent-session, medium risk)
- `skills` — 14.8 MiB allocated (13.5 MiB apparent) (other, medium risk)
...

### Codex home — 14.9 GiB allocated (14.8 GiB apparent)

- path: `/home/you/.codex`
- files: 8793
- `sessions` — 8.0 GiB allocated (7.9 GiB apparent) (agent-session, medium risk)
- `thread_history_1.sqlite` — 3.5 GiB allocated (3.5 GiB apparent) (database, high risk)
- `archived_sessions` — 916.7 MiB allocated (916.2 MiB apparent) (agent-session, medium risk)
...

### Xcode developer data — 1.3 GiB allocated (1.2 GiB apparent)

- path: `/home/you/Library/Developer/Xcode`
- files: 10953
- `DerivedData` — 662.5 MiB allocated (649.3 MiB apparent) (build-artifact, low risk)
- `CodingAssistant` — 513.0 MiB allocated (499.0 MiB apparent) (agent-cache, low risk)
...

# ... other existing roots elided ...

## Largest files

- `/home/you/.codex/thread_history_1.sqlite` — 3.5 GiB allocated (3.5 GiB apparent) (database, high risk)
- `/home/you/.codex/sessions/2026/11/03/rollout-...jsonl` — 1.1 GiB allocated (1.1 GiB apparent) (agent-session, medium risk)
- `/home/you/.codex/sessions/2026/08/05/rollout-...jsonl.zst` — 651.5 MiB allocated (651.5 MiB apparent) (agent-session, medium risk)
...

## Suggested review

- 8.0 GiB allocated (7.9 GiB apparent) — agent-session / medium risk: `/home/you/.codex/sessions`
  - Review age and keep what matters: archive old sessions elsewhere or prune them with the tool's own controls.
- 3.5 GiB allocated (3.5 GiB apparent) — database / high risk: `/home/you/.codex/thread_history_1.sqlite`
  - Never delete: back it up first and consider the tool's own maintenance command (for example VACUUM).
- 3.2 GiB allocated (2.8 GiB apparent) — plugin-package / medium risk: `/home/you/.claude/plugins`
  - Plugins and package caches are usually reinstallable; check for local development plugins first.
...

## Limitations

- Both apparent and allocated sizes are reported. Allocated size (st_blocks x 512) is the real disk usage; apparent size is what tools such as du --apparent-size show, and sparse files can have a huge apparent size with almost no allocation.
- Only metadata was read: no file contents, credentials, session text or account data were read, stored or uploaded.
- Directory symlinks are never followed, so linked roots and external volumes are not counted.
- Known roots are discovery hints and may be version-specific; paths that do not exist are omitted.
- The scan is read-only. `--apply --to-trash --confirm` moves selected low/medium risk paths into the trash directory; it never deletes them permanently, and high-risk paths are never moved.
- Database and Git object sizes are reported for awareness only; deleting them directly can lose history or state.
```

In this excerpt the allocated total is slightly larger than apparent because many
small files round up to whole blocks; sparse-file workloads show the opposite,
sometimes by orders of magnitude. The largest entries are sessions and a
database under the Codex home, plugin packages under Claude Code, and
build/cache output under Xcode. The audit ranks and labels them; it does not
decide that any of them should be removed.

## Moving candidates to Trash (optional)

The default command is read-only. A move happens only when all three explicit
flags are present:

```bash
# Read-only preview: review the Suggested review list first.
python3 <skill-root>/scripts/skill_atlas.py disk scan

# Move low-risk direct-child candidates (the default risk set) to ~/.Trash.
python3 <skill-root>/scripts/skill_atlas.py disk scan --apply --to-trash --confirm

# Include medium-risk candidates and choose a different trash directory.
python3 <skill-root>/scripts/skill_atlas.py disk scan --apply --to-trash --confirm \
  --risk low --risk medium --trash-dir ~/.Trash
```

Rules:

- **All three flags are required.** `--apply` without `--to-trash` is refused
  ("permanent deletion is not supported"), and `--apply` without `--confirm` is
  refused. A refused request exits with status 2 and moves nothing.
- **Only direct-child candidates are moved.** The move step uses the scan's
  `reclaimable` list (direct children of the scanned roots whose category is not
  `other`) and only entries whose risk is selected by `--risk`. `--risk` may be
  repeated; choices are `low` and `medium`, and the default is `low`.
- **High-risk entries are never moved.** Databases, `.git` objects, and any
  other `high` risk entry cannot be selected, so they stay where they are.
  Symlinks are never moved either.
- **Moves go to a trash directory with unique names.** The default destination
  is `~/.Trash`; `--trash-dir` overrides it (mainly for tests and external
  volumes) and the directory must already exist. If a name is taken, a
  timestamp suffix is added instead of overwriting.
- **No permanent deletion.** The tool never uses `rm -rf` and never deletes a
  path permanently. A cross-volume move copies the data and then removes the
  source, as `shutil.move` does.
- **Space is freed only after the Trash is emptied.** Moving a file out of a
  scanned root lowers the scan's totals, but the bytes are still on disk until
  the Trash is emptied. The tool never empties the Trash.
- **Failures are reported, not hidden.** Paths that no longer exist, overlap the
  trash directory, or fail to move appear in `skipped` or `failed` with a
  reason; the rest are moved or skipped independently.

The JSON result gains an `apply` object only when `--apply` is used:
`{status, trash_dir, selected_risks, moved, skipped, failed,
reclaimed_allocated_bytes}`. Each `moved` item has `path`, `trash_path`,
`size_bytes`, `allocated_bytes`, `category`, and `risk`; `skipped` and `failed`
items add a `reason`. `reclaimed_allocated_bytes` sums the allocated bytes of
moved paths only. Markdown adds an **Applied** section with the same facts and a
reminder to empty the Trash.

Safety before applying:

1. Run the read-only scan and review the **Suggested review** list.
2. Close tools that may be using the files; do not run cleanup while a tool is
   writing to them.
3. Use the default `--risk low` first. Add `--risk medium` only after reviewing
   those candidates, because they include sessions, plugins, media, and archives.
4. Check the **Applied** section and the Trash after the move. Restore anything
   that was moved by mistake from the Trash, then empty it deliberately when
   you are satisfied; emptying the Trash is what actually frees the space.

## Safety and privacy

- **Metadata only.** The scan reads names, apparent and allocated sizes (the
  latter from block counts), and modification times. It does not read file
  contents, credentials, session transcripts, account data or configuration
  values.
- **No network.** Nothing is uploaded, and no remote service is contacted.
- **Read-only by default; opt-in Trash moves.** Without all three of `--apply`,
  `--to-trash`, and `--confirm`, the scan only reads metadata and writes nothing.
  With all three, selected low/medium direct-child candidates are moved into the
  trash directory via `shutil.move`; high-risk entries and symlinks are never
  moved, nothing is permanently deleted, and `rm -rf` is never used.
- **No symlink following during traversal.** Symlinked files and directories
  encountered while walking a root are skipped and counted, so linked trees and
  external volumes are not traversed. Paths you pass explicitly as `--home`,
  `--root` or `--project` are normalized first, so a symlinked root is scanned
  at its resolved target.
- **Sensitive paths.** Output contains absolute home and project paths, which can
  reveal which tools and projects you use. Redact paths before sharing scan
  output publicly or attaching it to an issue.
- **Human review before applying.** Use the read-only scan to decide *what to
  review*. Close tools that may be using the files, run cleanup only
  deliberately, check the Applied section, and restore from the Trash rather
  than deleting anything permanently. The tool never empties the Trash.

## Limitations

The fixed caveats in every result, restated:

1. **Both apparent and allocated sizes are reported.** Allocated size
   (`st_blocks × 512`) is the real disk usage; apparent size is what tools such
   as `du --apparent-size` show, and sparse files can have a huge apparent size
   with almost no allocation.
2. **APFS compression, clones, snapshots and hard links can make the real
   reclaimable space different from either size.** Deleting a path does not
   always free all of its allocated blocks.
3. **Only metadata was read.** No file contents, credentials, session text or
   account data were read, stored or uploaded.
4. **Directory symlinks are never followed during traversal.** Linked roots and
   external volumes are not counted; only a root path passed explicitly is
   resolved before scanning.
5. **Known roots are discovery hints.** They may be version-specific, and paths
   that do not exist are omitted.
6. **The default scan is read-only.** The fixed text says the audit never
   deletes, moves, compresses or archives anything; when
   `--apply --to-trash --confirm` is used, it moves the selected candidates into
   Trash as described above and still never permanently deletes them.
7. **Database and Git object sizes are reported for awareness only.** Deleting
   them directly can lose history or state; cleanup never moves high-risk
   entries.

Additional practical caveats:

- Space is freed only after the Trash is emptied. Moving files out of a scanned
  root lowers the reported totals but does not release disk space by itself.
- A cleanup request can refuse (missing flags, high-risk selection, missing
  trash directory) or partially fail (permissions, cross-volume errors); check
  `skipped` and `failed` in the `apply` result instead of assuming every path
  moved.
- Allocated size can be slightly larger than apparent size for many small
  files, because allocation happens in blocks.
- Classification is name-based and can be wrong. Verify a candidate by opening
  its directory and checking the owning tool's documentation before acting.
- A per-root entry limit (`--max-entries`, default 400000) can mark a large root
  `truncated`; its sizes are then incomplete.
- The largest-files list only includes files whose allocated size is at or above
  `--min-file-mb`, and only files encountered during the scan; symlinks and
  unreadable entries are not included. A file with a large apparent size but
  little allocation may therefore not appear.
- Top-file categories are inherited from the nearest meaningful parent
  directory, so a large file inside a classified directory can carry that
  directory's category.

To act on a result, start with the **Suggested review** list, verify the owning
tool and file age, and back up anything that may matter. If you choose the
opt-in cleanup, run `disk scan --apply --to-trash --confirm` deliberately
(start with the default `--risk low`), inspect the **Applied** section, restore
anything moved by mistake from the Trash, and empty the Trash yourself only when
satisfied. Never delete a database or `.git` objects directly.

## Relation to the other read-only audits

- [`agents scan`](agent-environments.md) reports which agent tools, rule roots,
  skill roots and Skill Atlas copies exist, and flags version mismatch. It
  answers "what is configured here?"; `disk scan` answers "what is using space?".
- [`projects audit`](project-root-audit.md) groups duplicated project copies,
  hashes project documents and flags nested roots. It answers "which copy is
  which?"; `disk scan --project .` adds a size view for one project but does not
  group copies, compare documents or recommend consolidation.
- All three are local and read-only by default. Only
  `disk scan --apply --to-trash --confirm` changes anything, and it only moves
  selected low/medium risk candidates to the Trash. A typical review is:
  `agents scan` to see the environment, `projects audit` to understand copies,
  then `disk scan` to see where space goes before deciding what to archive or
  prune with the owning tools.
