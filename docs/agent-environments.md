# Local Agent Environment Scan

`agents scan` is a read-only discovery command added in `0.8.0-beta`. It
answers a narrow question: which coding-agent tools leave evidence on this
machine, which rule and skill roots does each tool's documentation or
convention point at, and do the local Skill Atlas copies agree on a version?

The scan only reads filesystem metadata and local Skill Atlas `skill.json`
manifests. It never executes an agent tool, opens a network connection, reads
credentials or session data, or writes, links, or deletes anything. Its output
is **discovery evidence**, not proof that any tool is installed correctly,
configured for a project, or currently loading the files it points at.

## What the scan does and does not prove

The scan reports:

- a reviewed catalog of coding-agent tools and the paths each one conventionally
  uses for home roots, rule/instruction entries, project rules, and skill roots;
- whether each of those paths exists, is a symlink, is broken, is readable, and
  (for skill roots) how many visible child directories it contains;
- whether each tool's executable name is found in the supplied `PATH`
  (existence only, never executed);
- shared skill roots: the same physical directory reached through more than one
  tool's skill-root path;
- local Skill Atlas copies under scanned skill roots, their manifest versions,
  and a `version_mismatch` flag when copies disagree;
- explicit limitations in every result.

The scan does **not** prove:

- that a tool is installed, healthy, or running;
- that a tool loaded, read, or honored any of the reported files;
- the tool's version (no tool version command is run);
- that a Skill Atlas copy is the one a given tool actually resolves at runtime;
- that candidate paths are current, correct, or supported by the tool's own
  documentation.

Missing, unreadable, or broken paths are reported as evidence and notes; they
do not abort the scan.

## Evidence levels

Every tool gets exactly one level. These are **file-evidence levels**, never
runtime states:

| Level | Meaning |
|---|---|
| `not-detected` | No tool-specific evidence was found in the scan scope. Shared skill roots alone do not change this. |
| `detected` | At least one tool-specific path or executable exists. Candidate-only evidence can produce `detected`, but never `configured`. |
| `configured` | A **documented** instruction entry exists, or the tool is otherwise detected and a **documented** skill root contains at least one skill. |

`configured` means documented configuration evidence exists on disk. It is not
`loaded` and not `handoff-verified`; those claims still require runtime evidence
from the tool itself. A present rule file is not loading, and a present skill
root is not proof that a tool reads it.

Two important consequences:

- A shared root such as `~/.agents/skills` can be listed for several tools but
  is not tool-specific evidence. It cannot by itself make a tool `detected` or
  `configured`.
- A candidate path that happens to exist only supports `detected`. Only paths
  explicitly documented in this repository can reach `configured`.

## Quickstart

Run from a project checkout. Markdown is the default output.

```bash
# Scan the current user's home; project rules are not read unless --project is given.
python3 <skill-root>/scripts/skill_atlas.py agents scan

# Also report project-scoped rule candidates, and produce machine-readable JSON.
python3 <skill-root>/scripts/skill_atlas.py agents scan --project . --format json

# Scan a different home directory, for example a test fixture or another account.
python3 <skill-root>/scripts/skill_atlas.py agents scan --home /path/to/home
```

| Flag | Meaning |
|---|---|
| `--home PATH` | User home directory to scan. Defaults to the current user's home. |
| `--project PATH` | Optional project directory whose rule files are reported. Without it, `project_rules` stays empty and the output says `project: not scanned`. |
| `--format markdown\|json` | Markdown summary (default) or the full result object. |

The scan is not recursive, does not follow arbitrary trees, and does not infer
project roots. It checks only the fixed paths in its catalog, one additional
conventional Skill Atlas copy root (`~/.cc-switch/skills`), and executable names
in `PATH`.

## Environment handling

The process environment is part of the scan scope:

- `PATH` is used only to check whether a catalog executable name exists. A hit
  means an executable file was found; it is never run, and its version is not
  read.
- Documented home overrides relocate tool-specific paths when set:
  `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, `OPENCODE_CONFIG_DIR`, `DSH_HOME`,
  `WORKBUDDY_HOME`, and `KIMI_CODE_HOME`. `KIMI_CODE_HOME` relocates Kimi's
  specific paths but not the shared `~/.agents/` root.
- `--home` changes the home prefix used for non-overridden paths; it does not
  clear environment overrides or replace `PATH`.

For reproducible output, run the scan with a controlled environment and a
fixture home. Do not treat `--home` as a security boundary.

## Tool catalog

Only paths explicitly described in this repository's documentation are marked
`documented`: [Cross-Agent Context and Handoff](cross-agent-collaboration.md)
(Codex, Claude Code, OpenCode, DeepSeek Harness, WorkBuddy, Kimi Code) and
[Kimi Code CLI integration](kimi-code.md) (Kimi Code details). Everything else,
including conventional-looking paths, is a `candidate` discovery hint.

### Tools with documented evidence

| Tool | ID | Documented rule entries | Documented project rules | Documented skill roots |
|---|---|---|---|---|
| Codex | `codex` | `~/.codex/AGENTS.md` (`$CODEX_HOME/AGENTS.md`) | `AGENTS.md` | — |
| Claude Code | `claude-code` | `~/.claude/CLAUDE.md` (`$CLAUDE_CONFIG_DIR/CLAUDE.md`) | `CLAUDE.md` | — |
| OpenCode | `opencode` | `~/.config/opencode/AGENTS.md` (`$OPENCODE_CONFIG_DIR/AGENTS.md`) | `AGENTS.md` | — |
| DeepSeek Harness | `deepseek-harness` | `~/.dsh/AGENTS.md` (`$DSH_HOME/AGENTS.md`) | `AGENTS.md` | — |
| WorkBuddy | `workbuddy` | `~/.workbuddy/rules` (`$WORKBUDDY_HOME/rules`) | `CODEBUDDY.md`, `.codebuddy/CODEBUDDY.md`, `AGENTS.md` | — |
| Kimi Code CLI | `kimi-code` | `~/.kimi-code/AGENTS.md` (`$KIMI_CODE_HOME/AGENTS.md`), `~/.agents/AGENTS.md` | `AGENTS.md`, `.kimi-code/AGENTS.md` | `~/.agents/skills`, `~/.kimi-code/skills` |

These tools also list additional tool roots and candidate skill roots that are
scanned for detection but never count as documented evidence, for example
`~/.codex`, `~/.codex/skills`, `~/.claude/skills`, `~/.config/opencode`,
`~/.dsh`, and `~/.workbuddy`, plus the shared `~/.agents/skills` root that only
Kimi Code documents as its own skill root.

### Candidate-only tools

None of these tools has documented paths in this repository yet, so they can be
`detected` at most, never `configured`:

| Tool | ID | Candidate rule and project paths |
|---|---|---|
| Cursor | `cursor` | `~/.cursor/rules`, project `.cursor/rules`, `.cursorrules` |
| Trae | `trae` | `~/.trae/rules`, project `.trae/rules`, `AGENTS.md` |
| Qoder | `qoder` | `~/.qoder/AGENTS.md`, project `.qoder/rules`, `AGENTS.md` |
| Gemini CLI | `gemini-cli` | `~/.gemini/GEMINI.md`, project `GEMINI.md` |
| Copilot CLI | `copilot-cli` | `~/.copilot/copilot-instructions.md`, project `.github/copilot-instructions.md` |
| CodeBuddy | `codebuddy` | `~/.codebuddy/CODEBUDDY.md`, project `CODEBUDDY.md`, `.codebuddy/CODEBUDDY.md` |
| Antigravity | `antigravity` | `~/.antigravity/rules`, project `.agent/rules` |
| Cline | `cline` | `~/.cline/rules`, project `.clinerules` |

Candidate skill roots for these tools (`~/.cursor/skills`, `~/.trae/skills`,
and so on) are scanned for detection only.

## Reading the report

Markdown output has these sections:

- **Summary** — counts of detected and configured tools, Skill Atlas copies, and
  the version-mismatch flag.
- **Tools** — one `### <name> (<id>): <level>` block per catalog tool, showing
  found executables, home roots, rule entries (labeled `documented` or
  `candidate`), shared or tool-specific skill roots with skill counts, project
  rules, and notes.
- **Shared skill roots** — physical paths reached by more than one tool.
- **Skill Atlas copies** — path, version, aliases, and symlink target.
- **Limitations** — the fixed caveat list reproduced below.

JSON output has `schema_version` (currently `1`) and:

| Key | Contents |
|---|---|
| `scan` | `home`, `project` (or `null`), `generated_at` |
| `tools` | Array of tool objects; each has `id`, `name`, `evidence_paths`, `detected`, `executables`, `roots`, `instruction_entries`, `project_rules`, `skill_roots`, `level`, `notes` |
| `shared_skill_roots` | Array of `{path, tools}` entries |
| `skill_atlas_copies` | Array of `{path, aliases, is_symlink, target, version, readable}` |
| `summary` | `tools_detected`, `tools_configured`, `skill_atlas_copies`, `version_mismatch` |
| `limitations` | Fixed list of limitation strings |

`evidence_paths` contains only existing tool-specific roots, instruction
entries, and skill roots. It excludes project rules and shared-only skill roots
by design.

### Worked example output

Sanitized excerpt (absolute home and project paths replaced, and some tool
sections elided for space; the real output contains one `###` section per
catalog tool):

```text
# Skill Atlas Agent Environment Scan

- home: `/home/you`
- project: `/path/to/project`
- generated: 2026-11-11T13:07:05.810712+00:00

## Summary

- tools detected: 3
- tools configured: 2
- skill atlas copies: 2
- version mismatch: true

## Tools

### Codex (`codex`): configured
- home root: `/home/you/.codex` (readable)
- rule entry (documented): `/home/you/.codex/AGENTS.md`
- skill root (root): `/home/you/.codex/skills` (1 skills)
- skill root (root): `/home/you/.agents/skills` (1 skills)
- project rule: `/path/to/project/AGENTS.md`
- note: documented configuration evidence present; runtime loading was not verified

### Claude Code (`claude-code`): configured
- home root: `/home/you/.claude` (readable)
- rule entry (documented): `/home/you/.claude/CLAUDE.md`
- skill root (root): `/home/you/.claude/skills` (1 skills)
- note: documented configuration evidence present; runtime loading was not verified

### OpenCode (`opencode`): not-detected
- project rule: `/path/to/project/AGENTS.md`

### Cursor (`cursor`): detected
- home root: `/home/you/.cursor` (readable)
- rule entry (candidate): `/home/you/.cursor/rules`
- note: candidate rule paths are unverified discovery hints
- note: local evidence only; candidate paths and runtime loading are unverified

# ... one section for every other catalog tool ...

## Shared skill roots

- `/home/you/.agents/skills`: codex, deepseek-harness, kimi-code

## Skill Atlas copies

- `/home/you/.claude/skills/skill-atlas`: 0.7.0-beta
- `/home/you/.codex/skills/skill-atlas`: 0.8.0-beta

## Limitations

- Runtime loading was not verified: existing files and directories do not prove any tool loaded them.
- Agent tool versions were not read and no agent tool was executed; a PATH hit only proves an executable file exists.
- Candidate paths and home environment-variable overrides are unverified discovery hints and may be version-specific or outdated.
- No network connection was opened, no credentials or session data were read, and no files or links were created or modified.
- Configured means documented configuration evidence exists; loaded and handoff-verified claims remain out of scope.
- Project rule candidates are project-scoped hints; their presence does not prove a tool is installed or active.
```

In this example, Codex and Claude Code are `configured` because documented rule
entries exist; Cursor is only `detected` because all of its paths are
candidates; OpenCode is `not-detected` even though the shared
`~/.agents/skills` root exists, because shared evidence is not tool-specific.
The two Skill Atlas copies disagree (`0.7.0-beta` and `0.8.0-beta`), so
`version mismatch` is `true`.

## Skill Atlas copy audit

The scan looks for a `skill-atlas/` directory under the catalog's skill roots
plus one extra conventional root, `~/.cc-switch/skills`. For each copy it:

- groups aliases that resolve to the same physical directory, so symlinked or
  duplicate roots are reported once with `aliases` and a `target`;
- reads only that copy's `skill.json` to report its `version`;
- marks the copy `readable: false` when the manifest is missing or unreadable,
  in which case `version` is `null`;
- sets `version_mismatch: true` only when at least two different readable
  versions are found.

A mismatch is a maintenance hint, not proof of which copy any tool loads. Use
the tool's own resolution behavior and the [cross-agent verification
levels](cross-agent-collaboration.md) before rewriting links or installations.
The scan never repairs, links, or deletes copies.

## Security and privacy

- **Read-only.** The scan creates, modifies, and deletes nothing. It does not
  run installers, link files, or execute agent tools.
- **No network.** No socket is opened; the catalog is local and the scan is
  offline.
- **No credential or session reads.** It inspects filesystem metadata and reads
  only `skill.json` manifests of local Skill Atlas copies. It does not read
  credential files, auth stores, session logs, chat history, or model
  configuration contents.
- **Sensitive paths.** Output contains absolute home and project paths. Redact
  them before sharing scan output publicly or attaching it to an issue.
- **Not a security boundary.** `--home` and environment overrides control scan
  scope, not access. The scan is diagnostic evidence for an authorized local
  environment.

## Limitations and how to verify a tool

The fixed limitations are the authoritative caveats:

1. **Runtime loading was not verified.** Existing files and directories do not
   prove any tool loaded them.
2. **No agent tool was executed and no tool versions were read.** A `PATH` hit
   only proves an executable file exists.
3. **Candidate paths and home overrides are unverified hints.** They may be
   version-specific or outdated.
4. **No network, credentials, or writes occurred.** No files or links were
   created or modified.
5. **`configured` is documented configuration evidence only.** `loaded` and
   `handoff-verified` remain out of scope.
6. **Project rule candidates are project-scoped hints.** Their presence does
   not prove a tool is installed or active.

To verify a tool for real:

1. Check that tool's own current documentation and version command — the
   catalog may lag a tool's actual behavior.
2. Start a fresh session with the tool and confirm which instruction and skill
   files it reports loading.
3. Distinguish **configured** (files exist), **loaded** (the tool demonstrably
   read them), and **handoff-verified** (a receiving agent correctly used the
   project objective, ownership, and next action).
4. Only then claim runtime behavior. Never upgrade scan output to a loading or
   handoff claim.

## Relation to the cross-agent workflow

Use the scan as the read-only evidence-gathering step described in
[Discover before configuring](cross-agent-collaboration.md#discover-before-configuring).
It collects candidate tool entries and roots before any configuration is
proposed; it does not configure anything and does not verify a handoff. The
catalog marks a path `documented` only when this repository's documentation
describes it, so candidate paths must be checked against the participating
tool's installed version first.

The scan is also independent of the optional local message transport
([Agent Handoff Messages](agent-messaging.md)): it never sends a message,
starts an agent, or checks an inbox.
