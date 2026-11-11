# Project Root and Duplicate Documentation Audit

`projects audit` is a read-only audit for a concrete local problem: the same
project can exist in several directories, each copy can carry its own
`AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, or `PROJECT_STATE.md`, and an agent can
read stale or conflicting instructions depending on which copy it opens. The
audit finds candidate project roots, groups copies that look like the same
project, compares agent-facing project documents by hash, reports nested
project roots, and suggests plan-only cleanup actions.

The audit only reads directory entries, file metadata, selected `.git` metadata
files, and document bytes for hashing. It never runs `git` (`.git/config` and
`.git/HEAD` are parsed by hand), never opens a network connection, never prints
or stores document contents, and never writes, moves, merges, archives, or
deletes anything. Every recommendation is a plan that requires explicit user
confirmation.

## What the audit does and does not prove

The audit reports:

- candidate project roots in the supplied scope, with the evidence that made
  each directory count as a project;
- parsed repository identity (remote URL and HEAD branch, when readable) and
  worktree/bare status;
- likely-duplicate groups using two evidence levels: a normalized git remote
  (confirmed) or a case-folded directory name (probable);
- SHA-256 comparison of agent-facing project documents, including divergent and
  byte-identical copies;
- nested project pairs; and
- deterministic, plan-only recommendations that always require user
  confirmation.

The audit does **not** prove:

- that two copies are the same project — both identity signals are heuristics;
- which copy is newer, better, canonical, complete, or authoritative;
- that a document will be loaded at runtime by any tool;
- that an audit result covers every project copy on the machine (discovery is
  depth-bounded and skips linked/hidden trees);
- that a repository is healthy; `git` is not executed and unusual repositories
  may be parsed incompletely;
- that any suggested action is safe to run automatically.

Treat the output as discovery evidence and review the actual files before
acting.

## Quickstart

Run from a shell in any directory. Markdown is the default output.

```bash
# Audit one project plus another checkout you already know about.
python3 <skill-root>/scripts/skill_atlas.py projects audit \
  --project . --project /path/to/other-copy

# Discover project roots up to two levels below a directory.
# The scanned root itself is not reported as a project; add --project for it.
python3 <skill-root>/scripts/skill_atlas.py projects audit \
  --root ~/Projects --depth 2

# Machine-readable result for a script or a review note.
python3 <skill-root>/scripts/skill_atlas.py projects audit \
  --root ~/Projects --project . --format json
```

| Flag | Meaning |
|---|---|
| `--project PATH` | Audit this directory as a project even if it has no discovery markers. May be repeated. A non-directory path is audited anyway and produces a warning. |
| `--root PATH` | Search this directory's descendants for project roots. The root itself is not reported; use `--project` for it. May be repeated. |
| `--depth N` | Maximum discovery depth below each root. Direct children are depth 1; the default is `2`. A project `N` levels below a root is discovered when `N <= depth`, so `--depth 0` disables discovery below that root. |
| `--format markdown\|json` | Markdown report (default) or the full result object. |

Flags may be combined and repeated. With no `--project` and no `--root`, the
audit returns an empty result rather than scanning the current directory
implicitly.

## Discovery

A directory counts as a project when either:

- it contains a `.git` entry (directory, or a `.git` file pointing at a linked
  worktree or submodule git directory); or
- at least **two** discovery markers exist among
  `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `PROJECT_STATE.md`,
  `PROJECT_INDEX.md`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`,
  `.cursor/rules`, and `.codebuddy/CODEBUDDY.md`.

Discovery behavior:

- `--project` paths are always audited, even without `.git` or markers.
- Discovery walks below each `--root` at most `--depth` levels and never follows
  directory symlinks.
- Hidden directories (names starting with `.`), `node_modules`, and
  `__pycache__` are skipped wholesale, so `.git` internals are never treated as
  project roots.
- Unreadable directories are skipped with a warning; unreadable documents are
  recorded with a null hash.
- A symlink loop passed directly as a root produces a warning, not a crash; a
  symlinked root that resolves normally is audited once.

## Identity: confirmed versus probable

A duplicate group needs at least two audited projects. Identity is assigned in
this order:

| Evidence | Key | Reliability |
|---|---|---|
| `git-remote` | `git-remote:<normalized remote>` | **Confirmed**: normalized git remote, compared case-insensitively |
| `directory-name` | `name:<case-folded directory name>` | **Probable**: same directory basename only |

Git-remote normalization:

- `https://github.com/acme/widgets.git`, `git@github.com:acme/widgets.git`, and
  `ssh://git@github.com/acme/widgets.git` all normalize to
  `github.com/acme/widgets`.
- The host and the owner/repository path are compared case-insensitively, so
  `git@github.com:Jorgut/Demo.git` and `https://github.com/jorgut/demo` group
  together.
- URL credentials are ignored for identity, `.git` suffixes and trailing slashes
  are stripped, and `origin` is preferred over other remotes.
- The original remote URL is still reported unchanged on the project record.
- Local-path remotes are normalized textually; relative paths are not resolved
  against the filesystem.

Additional rules:

- Copies with **different** remotes are never merged, even when their directory
  names match.
- A copy with a usable remote and a copy without one do not share an identity
  key, so they are not grouped.
- A matching directory name is weak evidence: unrelated projects can share a
  basename, and a group is not proof of duplication.

## Comparing project documents

Only these agent-facing documents are compared:

`AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `PROJECT_STATE.md`,
`PROJECT_INDEX.md`, `CODEBUDDY.md`, `.cursor/rules`, `.agent/rules`.

Note the asymmetry with discovery: `.codebuddy/CODEBUDDY.md` is a discovery
marker, but the compared document is `CODEBUDDY.md` at the project root.

For each document the audit records its path, size, modification time, a
SHA-256 hash, and a `too_large` flag. Rules:

- Only files at or below **256 KiB** are hashed. A larger file is
  recorded with `too_large: true` and no hash, so divergence inside oversized
  documents is not detected.
- Directories (such as `.cursor/rules` when it is a directory) are recorded but
  never hashed.
- Missing or unreadable documents have a null hash.
- Document bytes are read only to compute the hash. Contents are never printed,
  stored in the result, or compared semantically.

Within a duplicate group:

- **Divergent** means at least two copies have hashes and at least two hashes
  differ. The report lists each variant's path, size, mtime, and a 12-character
  hash prefix.
- **Identical** means at least two copies have hashes and all are equal. The
  report lists the document name, hash prefix, and paths.
- A document with a single hashed copy in the group, or with all other copies
  missing/unreadable/oversized, is simply not compared.

Hash equality proves byte identity. Hash difference proves that two documents
differ; it does **not** prove which one is newer, better, or authoritative.
File mtimes are reported as additional evidence, but copies can be touched or
synced independently, so mtime is not a reliable version ordering.

## Nested project roots

Any audited project path strictly inside another audited project path is
reported as an `outer`/`inner` pair. This usually means one checkout contains
another repository (vendored copy, nested worktree, or an accidentally copied
project). Nested pairs are reported independently of duplicate groups, and the
order of `--project` arguments does not change the reported pairs.

A nested pair does not automatically mean the outer project is wrong; it is a
configuration and cleanup question for the user.

## Recommendations are plans only

The audit emits one recommendation per duplicate group. Every recommendation
sets `requires_user_confirmation: true` and lists suggested actions such as:

- keep one path as the canonical candidate;
- review each divergent document across the copies;
- archive the remaining duplicate copies only after user confirmation; and
- do not move, merge, delete, or rewrite files automatically.

The canonical candidate is deterministic but still a heuristic:

- For confirmed `git-remote` groups, the newest `PROJECT_STATE.md`/`CONTEXT.md`
  mtime is preferred (freshness is trusted only at this evidence level), then
  the path with more existing documents, then the shorter path, then lexical
  order.
- For probable `directory-name` groups, freshness is ignored: the path with more
  existing documents wins, then the shorter path, then lexical order.

The audit never archives anything itself. If you choose to consolidate, back up
first and review every divergent document; do not let a plan replace human
judgment.

## Reading the report

Markdown output has these sections:

- **Summary** — project count, duplicate groups, divergent documents, nested
  pairs, and scanned roots.
- **Projects** — one `### <path>` block per project: name, discovery evidence,
  parsed git remote/HEAD/worktree status, markers present, hashed documents, and
  oversized documents.
- **Duplicate groups** — identity, evidence level, paths, divergent documents
  with variants, and identical documents.
- **Nested project pairs** — `outer` contains `inner` lines.
- **Recommendations** — canonical candidate, confirmation flag, and suggested
  actions.
- **Warnings** — only when roots, explicit paths, or directories could not be
  read.
- **Limitations** — the fixed caveat list.

JSON output has `schema_version` (currently `1`):

| Key | Contents |
|---|---|
| `audit` | `roots`, `explicit_projects`, `depth`, `generated_at`, `warnings` |
| `projects` | Array of project records: `path`, `name`, `git`, `markers`, `docs`, `discovered_by`, `evidence` |
| `duplicate_groups` | Array of `{identity, evidence, paths, divergent_docs, shared_identical_docs}` |
| `nested_pairs` | Array of `{outer, inner}` |
| `recommendations` | Array of `{identity, evidence, canonical_candidate, suggested_actions, requires_user_confirmation}` |
| `summary` | `projects`, `duplicate_groups`, `divergent_docs`, `nested_pairs`, `roots_scanned` |
| `limitations` | Fixed list of limitation strings |

Nested object shapes: a project `git` object is `{is_repo, remote_url,
remote_name, head_ref, worktree_or_bare}`; a marker is `{name, path, exists,
size, mtime}`; a document is `{name, path, size, mtime, sha256, too_large}`; a
divergent document is `{name, distinct_hashes, variants}` where each variant is
`{path, size, mtime, sha256}`; an identical document is `{name, sha256, paths}`.
Group-level hashes are 12-character prefixes; full 64-character hashes remain
in the project records.

### Worked example output

Sanitized excerpt from a fixture with two copies of the same GitHub project (one
uses an `https://` remote, the other an `ssh`/SCP remote with different casing),
two same-named projects without git, and a nested repository. Paths are
replaced; some project blocks and sections are elided for space.

```text
# Skill Atlas Project Root Audit

- roots scanned: `/path/to/scan`
- explicit projects: none
- discovery depth: 4
- generated: 2026-11-11T13:24:44.826078+00:00

## Summary

- projects: 6
- duplicate groups: 2
- divergent docs: 3
- nested project pairs: 1
- roots scanned: 1

## Projects

### `/path/to/scan/alpha/widgets`

- name: widgets
- discovered by: git
- git: `origin` = `https://github.com/acme/widgets.git`
- HEAD: refs/heads/main
- worktree or bare: false
- markers present: AGENTS.md, CONTEXT.md
- docs hashed: AGENTS.md (2d1196a18405), CONTEXT.md (c8d2dac43eb3)

### `/path/to/scan/beta/widgets`

- name: widgets
- discovered by: git
- git: `origin` = `git@github.com:ACME/Widgets.git`
- HEAD: refs/heads/main
- worktree or bare: false
- markers present: AGENTS.md, CONTEXT.md
- docs hashed: AGENTS.md (30a474c8f7fc), CONTEXT.md (b32f40aee122)

# ... other project blocks ...

## Duplicate groups

### `git-remote:github.com/acme/widgets` (git-remote)

- `/path/to/scan/alpha/widgets`
- `/path/to/scan/beta/widgets`
- divergent docs:
  - AGENTS.md (2 distinct hashes)
    - `/path/to/scan/alpha/widgets/AGENTS.md` size=15 mtime=1794403484.655314 sha256=2d1196a18405
    - `/path/to/scan/beta/widgets/AGENTS.md` size=15 mtime=1794403484.6648 sha256=30a474c8f7fc
  - CONTEXT.md (2 distinct hashes)
    - `/path/to/scan/alpha/widgets/CONTEXT.md` size=12 mtime=1767207600.0 sha256=c8d2dac43eb3
    - `/path/to/scan/beta/widgets/CONTEXT.md` size=12 mtime=1780254000.0 sha256=b32f40aee122
- identical docs: none

### `name:sample` (directory-name)

- `/path/to/scan/one/sample`
- `/path/to/scan/two/sample`
- divergent docs:
  - AGENTS.md (2 distinct hashes)
    - `/path/to/scan/one/sample/AGENTS.md` size=15 mtime=1794403484.674684 sha256=eb85eff4b0c1
    - `/path/to/scan/two/sample/AGENTS.md` size=16 mtime=1794403484.675262 sha256=57b28e6f2019
- identical docs: CLAUDE.md (65228ffefd2e)

## Nested project pairs

- `/path/to/scan/nested/outer` contains `/path/to/scan/nested/outer/inner`

## Recommendations

### `git-remote:github.com/acme/widgets`

- canonical candidate: `/path/to/scan/beta/widgets`
- requires user confirmation: true
- suggested actions:
  - keep `/path/to/scan/beta/widgets` as the canonical candidate
  - review divergent AGENTS.md across 2 copies
  - review divergent CONTEXT.md across 2 copies
  - archive the 1 duplicate copy only after user confirmation
  - do not move, merge, delete or rewrite files automatically

## Limitations

- Identity is a heuristic: a matching normalized git remote is stronger evidence than a matching directory name, and a shared directory name alone does not prove two paths are the same project.
- File hashes prove that two documents differ; they do not prove which copy is newer, better or authoritative.
- Discovery is depth-bounded, skips hidden directories and node_modules, and does not traverse directory symlinks, so deeper or linked project roots can be missed; pass --project or --root explicitly for those.
- git was not executed: .git/config and .git/HEAD were parsed by hand, so unusual, bare, submodule or partially written repositories may be reported incompletely.
- Only file metadata and documentation hashes were read; document contents were never printed, stored in the result, or compared semantically.
- Recommendations are plans only. The audit never moves, merges, archives, rewrites or deletes files, and every suggested action requires user confirmation.
- Files larger than 256 KiB are not hashed, so divergence in oversized documents is not detected.
```

In this example the two `widgets` copies group as **confirmed** because their
remotes normalize to the same `github.com/acme/widgets` (the `ACME/Widgets`
casing folds too). The `sample` directories group only as **probable** because
their basenames match and neither has git. Both `AGENTS.md` and `CONTEXT.md`
diverge in the confirmed group, so the recommendation asks for review and for
confirmation before archiving one copy.

## Security and privacy

- **Read-only.** The audit creates, modifies, moves, archives, and deletes
  nothing. It does not run installers and does not change project files.
- **No git execution.** `.git/config`, `.git/HEAD`, worktree `gitdir` pointers,
  and `commondir` are parsed by hand; only small metadata files (up to 1 MiB) are
  read. No git subprocess is spawned.
- **No network.** No socket is opened and no remote is contacted.
- **No document contents printed.** Only paths, sizes, mtimes, and hashes
  appear in the result. Document bytes are read only to compute hashes.
- **Sensitive paths.** Output contains absolute project paths. Redact them
  before sharing audit output publicly or attaching it to an issue.
- **Remote URLs may contain credentials.** The raw remote URL is reported as
  stored in `.git/config`; a URL such as
  `https://user:token@github.com/acme/widgets.git` would appear in the output.
  Redact remote URLs as well as paths before sharing.
- **Not an authorization boundary.** `--project` and `--root` define scope;
  reviewing and executing any recommendation remains a user decision.

## Limitations

The fixed caveats in every result, restated:

1. **Identity is a heuristic.** A matching normalized remote is stronger than a
   matching directory name; a shared name alone does not prove two paths are the
   same project.
2. **Hashes prove difference, not authority.** The audit cannot say which copy
   is newer, better, or canonical.
3. **Discovery is depth-bounded.** It skips hidden directories and
   `node_modules`, does not traverse directory symlinks, and can miss deeper or
   linked roots; pass `--project` or `--root` explicitly for those.
4. **git was not executed.** Unusual, bare, submodule, or partially written
   repositories may be reported incompletely.
5. **Document contents were never exposed.** Only metadata and hashes appear in
   the result; bytes were read only to compute hashes and no semantic comparison
   was performed.
6. **Recommendations are plans only.** Nothing is moved, merged, archived,
   rewritten, or deleted, and every action requires user confirmation.
7. **Oversized documents are skipped.** Files larger than 256 KiB are not
   hashed, so divergence in them is not detected.

To act on a result, open the actual copies and review the divergent documents,
confirm which checkout you intend to keep, make a backup, and only then perform
a reviewed change manually or with explicit authorization.

## Relation to the cross-agent workflow

The audit supports the
[Discover before configuring](cross-agent-collaboration.md#discover-before-configuring)
and state-maintenance parts of the cross-agent workflow. Before choosing a
canonical checkout, configuring shared rules, or handing a task to another
agent, use the audit to spot:

- the same project stored in several directories (which copy did the agent
  read?);
- divergent `AGENTS.md`/`CLAUDE.md` rules across those copies;
- divergent `CONTEXT.md`/`PROJECT_STATE.md` task state; and
- a project nested inside another project.

The audit is discovery evidence only. It does not verify that any tool loaded a
rule file, does not verify a handoff, and does not replace the configured /
loaded / handoff-verified distinction in the collaboration guide. Its sibling
command [`agents scan`](agent-environments.md) covers installed agent tools and
rule/skill roots, while `projects audit` covers project copies and their
documents.
