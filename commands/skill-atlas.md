---
description: Manage skills, recommend workflows, guide cross-agent context and handoff, and relay local agent messages
---

Use the `skill-atlas` skill for this request.

Treat `$ARGUMENTS` as the user's requested Skill Atlas command or task. If no
arguments are supplied, run `manage scan`. Preserve the skill's read-only
defaults and require explicit confirmation before any installation, update,
deletion, overwrite, or symlink change.

For natural-language requests about shared rules, project context, or agent
handoff, follow the skill's Cross-Agent Context and Handoff workflow. Do not
translate these requests into an unsupported CLI subcommand.

For requests to hand a compact review or action note to another local agent,
use the `message` commands (`send`, `inbox`, `show`, `ack`, `approve`) and keep
the transport boundaries: no network, no agent startup or notification, and no
completion for `--requires-approval` messages before a person approves. See
`docs/agent-messaging.md`.

For requests to search public Skills, MCP servers, AI tools or alternatives,
use the unified CLI with `--search-mode hybrid` (or `web` to skip local
inventory). Follow `docs/external-search.md`: report actual per-source
execution, limitations, times and URLs. Local briefs and generated query
suggestions are not completed searches. External hits remain review-required;
never install or promote them automatically.
