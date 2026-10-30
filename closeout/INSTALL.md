# closeout (净化) — Install & Smoke Test

Beginner guides: [中文](GETTING_STARTED.zh-CN.md) | [English](GETTING_STARTED.en.md) | [Русский](GETTING_STARTED.ru.md)

## Recommended Safe Install

From the repository root, preview all operations first:

```bash
python3 scripts/install_closeout.py --all-platforms --commands
```

After reviewing every destination, apply explicitly:

```bash
python3 scripts/install_closeout.py --all-platforms --commands --apply --confirm
```

The installer creates one canonical copy at `~/.agents/skills/closeout`, links
the selected platform skill paths, refuses all conflicts before writing, and
never overwrites existing paths. Restart installed Agent applications after the
installer completes.

## Manual Install (Advanced)

```bash
# Option A: Symlink into your local skills directory
# OpenCode
ln -s /absolute/path/to/session-closeout-skill/closeout ~/.config/opencode/skills/closeout

# Claude Code
ln -s /absolute/path/to/session-closeout-skill/closeout ~/.claude/skills/closeout

# Codex
ln -s /absolute/path/to/session-closeout-skill/closeout ~/.codex/skills/closeout
```

## Optional Slash Command Adapters

Installing a skill does not automatically add it to a platform's `/` menu.
OpenCode and Claude Code can share the bundled command adapter:

```bash
mkdir -p ~/.config/opencode/commands ~/.claude/commands
ln -s /absolute/path/to/session-closeout-skill/closeout/commands/closeout.md \
  ~/.config/opencode/commands/closeout.md
ln -s /absolute/path/to/session-closeout-skill/closeout/commands/closeout.md \
  ~/.claude/commands/closeout.md
```

Codex invokes the skill by name or natural language rather than registering a
custom `/closeout` menu command.

```bash
# Option B: Copy (if you prefer isolation)
cp -r /path/to/session-closeout-skill/closeout ~/.config/opencode/skills/closeout
```

## Verify Install

```bash
# Should show closeout in skill list
# OpenCode
opencode skill list

# Or just check the directory exists
ls ~/.config/opencode/skills/closeout/
# Expected: SKILL.md  references/  evals/
```

## Smoke Test (run once after install)

1. **Open a project** that has some code, a README, and optionally a CLAUDE.md
2. **Make a small change** (e.g., update a version number, add a command to README)
3. **Trigger closeout** (use `/closeout` after installing the optional command
   adapter):
   ```
   /closeout
   ```
   or natural language:
   ```
   sync docs and memory
   净化一下
   ```
4. **Verify behavior**:
   - Skill inventories markdown + rule files
   - Compares against current code/config
   - Applies safe auto-fixes (e.g., missing `.env*` in `.gitignore`)
   - Lists any deletion candidates (throw-away plans, `*_old.*` files)
   - Produces two-phase report with **Impact**, **Changed/Created**, **Needs Your Decision**, **Residual**
5. **Confirm it did NOT**:
   - Delete branches/worktrees (out of scope)
   - Trigger on "tidy up this file" (excluded)
   - Write to memory without explicit authorization

## Expected Artifacts After Smoke Test

- Updated README/CLAUDE.md (if discrepancies existed)
- `references/verification-checklist.md` items all `pass` or `waived-with-reason`
- Report output in chat following the two-phase format

## Local Dev Notes

- The runtime skill is self-contained; the repository-level installer is only for setup
- All platform logic lives in `references/platform-behavior.md` (read-only guidance)
- `evals/evals.json` covers trigger, permission, behavior, and regression layers
- `scripts/run_evals.py validate` checks the deterministic eval contract
- Line budget: SKILL.md ≤ 500 lines
