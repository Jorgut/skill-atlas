---
description: Manage skills, recommend workflows, and guide cross-agent context and handoff
---

Use the `skill-atlas` skill for this request.

Treat `$ARGUMENTS` as the user's requested Skill Atlas command or task. If no
arguments are supplied, run `manage scan`. Preserve the skill's read-only
defaults and require explicit confirmation before any installation, update,
deletion, overwrite, or symlink change.

For natural-language requests about shared rules, project context, or agent
handoff, follow the skill's Cross-Agent Context and Handoff workflow. Do not
translate these requests into an unsupported CLI subcommand.
