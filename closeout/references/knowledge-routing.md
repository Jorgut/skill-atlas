# Knowledge Routing Reference

## Change Type → Destination Layer Mapping

| Change Observed | Primary Destination | Secondary / Pointer | Notes |
|-----------------|---------------------|---------------------|-------|
| New CLI command, flag, or subcommand | **Rule file** (CLAUDE.md/AGENTS.md) | Docs: command reference table | Mechanically verifiable; auto-fix class |
| Port number, env var name, config key | **Rule file** | Docs: configuration section | Auto-fix if mechanically verifiable |
| API endpoint added/changed/removed | **Docs** (README or `docs/api.md`) | Rule file: pointer to doc | Human-facing; not auto-fix |
| Architecture decision (new service, DB, pattern) | **Docs** (`docs/architecture.md` or ADR) | Rule file: one-line summary + link | Stable mechanism → docs |
| Directory structure convention | **Rule file** | Docs: contributing guide | Enforceable convention → rule file |
| Naming convention (kebab-case, snake_case, etc.) | **Rule file** | — | Mechanically checkable |
| Required file existence (CLAUDE.md, LICENSE, etc.) | **Rule file** | — | Auto-fix by creating from template |
| Broken symlink (AGENTS.md → CLAUDE.md) | **Rule file** (fix symlink) | — | Auto-fix |
| `.gitignore` missing security entries (`.env*`, `*.pem`) | **Rule file** (patch `.gitignore`) | — | Auto-fix |
| Version bump (package.json, Cargo.toml, go.mod) | **Rule file** (update version ref) | Docs: changelog pointer | Auto-fix if mechanically verifiable |
| Deprecated command/flag removed | **Rule file** (remove entry) | Docs: migration note | Report-first if could break users |
| Session-specific learning (workaround, tribal knowledge) | **Agent memory** | — | Only if authorized; not for stable mechanisms |
| User preference (editor, shell, workflow) | **Agent memory** | — | Personal; not project knowledge |
| Bug fix / incident detail | **Git history / incident doc** | Docs: if process changed | Not in rule file or memory |
| Temporary workaround | **Agent memory** (short-term) | — | Must have expiry or review trigger |
| Cross-project dependency change | **Rule file** (both projects) | Docs: integration guide | **Report-first, confirm-before-act** |
| Memory entry that duplicates docs/rule content | **Memory** (condense to pointer) | Docs/Rule: keep authoritative | "减优于加" — prefer pointer over duplication |

## Routing Principles

1. **Mechanically verifiable → Rule file** (auto-fix eligible)
2. **Human-facing, stable, explanatory → Docs** (README, `docs/`)
3. **Personal, transient, non-obvious → Agent memory** (with authorization)
4. **One authoritative source per fact** — others hold short pointers
5. **Unknown change type → Flag for user decision** (never guess)

## Layer Responsibilities (Non-Overlapping)

| Layer | Audience | Content Type | Mutation Policy |
|-------|----------|--------------|-----------------|
| **Rule files** (CLAUDE.md/AGENTS.md) | Current & future AI agents | Constraints, commands, conventions, pointers | Auto-fix safe; report-first for destructive |
| **Docs** (README, `docs/`) | Humans, downstream devs | How-to, architecture, API, operations | Edit for clarity; never auto-delete |
| **Agent memory** | Cross-session AI continuity | Preferences, workarounds, tribal knowledge | Authorized only; read-only for unknown platforms |
| **Git / Changelog / Incident docs** | Historical record | What happened, why, when | Append-only; never modified by closeout |