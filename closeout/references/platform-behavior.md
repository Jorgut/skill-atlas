# Platform Behavior Reference

## Rule File Naming & Loading Order

| Platform | Primary Rule File | Fallback / Alias | Load Order |
|----------|-------------------|------------------|------------|
| OpenCode | `CLAUDE.md` or `AGENTS.md` | `.opencode/rules.md` | Project root → parent scopes → `~/.config/opencode/CLAUDE.md` |
| Claude Code | `CLAUDE.md` | `AGENTS.md` (symlink) | Project root → parent scopes → `~/.claude/CLAUDE.md` |
| Codex | `AGENTS.md` | `CLAUDE.md` (symlink) | Project root → `~/.codex/AGENTS.md` |
| OpenClaw | `CLAUDE.md` | `AGENTS.md` | Project root → `~/.openclaw/CLAUDE.md` |
| Generic/Unknown | `AGENTS.md` | `CLAUDE.md` | Project root only (conservative) |

**Symlink convention**: `AGENTS.md` should be a symlink to `CLAUDE.md` when both exist. If both are regular files with different content → flag as conflict (report-first).

## Memory Control Surfaces

| Platform | Memory Location | Write Access | Notes |
|----------|-----------------|--------------|-------|
| OpenCode | `.opencode/memory/` | Via agent tools | Structured, project-scoped |
| Claude Code | `~/.claude/projects/<hash>/memory/` | Auto-managed | Append-only by default; consolidation is internal |
| Codex | `~/.codex/memories/` + `~/.codex/AGENTS.md` | Read-only for skills | Machine-generated; corrections via platform UI |
| OpenClaw | `~/.openclaw/memory/` | Via agent tools | Similar to OpenCode |
| Unknown | N/A | **Read-only report only** | Do not attempt writes |

## Size Budgets (per platform guidance)

- OpenCode / OpenClaw: soft limit ~200 KB per project memory
- Claude Code: internal consolidation; no hard user-facing limit
- Codex: `AGENTS.md` ≤ 25 KB recommended; `memories/` managed by platform

## Unknown Platform Fallback

**When the platform cannot be identified or has no documented memory control surface:**
1. Default to **read-only reporting** — list what would be updated if a known surface existed.
2. Do NOT create files in guessed paths.
3. Include a "Memory Sync: UNKNOWN PLATFORM — manual sync required" line in the closeout report.
4. Offer to create a minimal `AGENTS.md` or `CLAUDE.md` in the project root as the portable fallback.

## Loading Order Summary

1. Project-local rule file (`CLAUDE.md` / `AGENTS.md`)
2. Parent directory rule files up to workspace root
3. User-global rule file (`~/.config/<platform>/CLAUDE.md` or equivalent)
4. Platform defaults (built-in)

Later entries override earlier only for additive rules; destructive overrides are flagged.