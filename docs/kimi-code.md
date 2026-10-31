# Kimi Code CLI integration

## Current verified official interfaces

This integration targets the official TypeScript-based **Kimi Code CLI**
from [MoonshotAI/kimi-code](https://github.com/MoonshotAI/kimi-code),
not the older Python-based `kimi-cli` project.

Official references:

- [Agent Skills](https://moonshotai.github.io/kimi-code/en/customization/skills):
  native user-level `~/.agents/skills/`, Kimi-specific `~/.kimi-code/skills/`,
  project-level `.agents/skills/` and `.kimi-code/skills/`.
- [Agents and instruction files](https://moonshotai.github.io/kimi-code/en/customization/agents):
  user `~/.kimi-code/AGENTS.md` or shared `~/.agents/AGENTS.md`;
  project `AGENTS.md` or `.kimi-code/AGENTS.md`.
- [Kimi command](https://moonshotai.github.io/kimi-code/en/reference/kimi-command):
  interactive `kimi`, one-shot `kimi -p`, `--output-format stream-json`,
  `--skills-dir`, `kimi acp`.
- [Lifecycle hooks](https://moonshotai.github.io/kimi-code/en/customization/hooks):
  configuration under user `config.toml`; platform-specific event contracts.

## Install safely

The existing Skill Atlas installer copies one canonical version into
`~/.agents/skills/skill-atlas`, a location Kimi Code CLI already scans.

```bash
# Preview; does not write
python3 scripts/skill_atlas.py install --platform kimi --with-closeout

# Apply only after reviewing all paths and conflicts
python3 scripts/skill_atlas.py install --platform kimi --with-closeout --apply --confirm
```

The optional Closeout install links the bundled Closeout package to
`~/.agents/skills/closeout`. Both Skills are natively discoverable by Kimi.
The installer deliberately does **not** create duplicate
`~/.kimi-code/skills/` links. It refuses conflicts with an existing
standalone Closeout installation instead of overwriting it.

The `KIMI_CODE_HOME` environment variable relocates Kimi-specific
`skills/` and `AGENTS.md` but does not relocate the shared
`~/.agents/skills/` root. If launched with `--skills-dir`, note that
the flag replaces automatically discovered user/project Skill directories
for that invocation, so add the shared root explicitly if needed.

## Actual handoff workflow

In a disposable Git repository containing a task and `AGENTS.md`:

1. Open the directory in Kimi Code CLI and confirm skill catalog loading.
   Invoke `/skill:skill-atlas` and `/skill:closeout` inside Kimi.
2. Use `python3 /path/to/skill-atlas/scripts/skill_atlas.py resume
   --project . --task issue-28` to inspect the last checkpoint without writes.
3. Read actual task files and Git diff. If state is consistent, continue
   with project-native tests and save `checkpoint` or `handoff`.
4. Ask another authorized Agent to run `resume` in the same checkout
   or at an appropriate committed/pushed checkpoint on another machine.
5. Mark the result `configured`, `loaded`, or `handoff-verified`
   only after evidence supports the corresponding claim.

Kimi Code CLI has optional lifecycle hooks such as `SessionStart`,
`PostToolUse`, `PreCompact`, and `SessionEnd`. Hook setup must be
user-approved and tested with the installed Kimi version. Hook failures
may be fail-open; do not depend on them as a security boundary or
promise a checkpoint on sudden process termination.

## What is *not* implemented

- No Kimi authentication, quota reads, provider error classification,
  automatic model switching, task dispatch, or unattended execution.
- `kimi -c` resumes a **Kimi** session; Skill Atlas `resume`
  reads a task checkpoint that can be shared across different Agents.
- No inspection of Kimi's local credential files or private session logs.
- No proof of an actual Kimi-to-Codex handoff until an end-to-end
  smoke test runs on a user-controlled development environment.
