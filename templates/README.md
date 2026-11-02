# Public Collaboration Templates

These are reusable starting points, not the author's live rules or project history. They contain placeholders rather than personal paths, account identifiers, or active project progress.

| Template | Role | Destination |
| --- | --- | --- |
| [Global rules](global-AGENTS.template.md) | Stable cross-project principles, first-principles reasoning, UI hierarchy, preservation and handoff | The user-rule entry supported by your tool, or a shared rules file explicitly read by it |
| [Project rules](project-AGENTS.template.md) | Project-specific scope, structure, commands and boundaries | The project's supported rule file, commonly `AGENTS.md` |
| [Project context](CONTEXT.template.md) | Objective, facts, decisions, progress, ownership and evidence | Existing state file, or project `CONTEXT.md` when needed |

## Apply selectively

1. Inspect your existing rules and state. Choose only the missing pieces; do not overwrite existing files or introduce duplicate state.
2. Copy the chosen template to an authorized destination and replace its placeholders with verified facts. Remove unused fields instead of inventing requirements or test results.
3. Discover each tool's effective rules entry, instruction precedence and permissions. A shared Markdown file is useful only when the tool actually loads or reads it. Paths written in rules are not automatically expanded on every platform.
4. For several projects, an optional index can map project names to confirmed roots, rules and state. Keep machine-specific paths in local configuration.
5. Validate a fresh task by checking which files were read and whether the agent can identify the correct objective and next action. Report configuration separately from verified loading and handoff.

The `.template.md` suffix keeps these examples distinct from active rule files. Do not rename them in the Skill Atlas repository to activate them for all users; install adapted copies in your intended user/project location.

Agents maintain meaningful project state during authorized work. Human confirmation remains necessary for unresolved goals, permissions, and consequential actions. The context template is suitable for public fictional examples; actual context may belong in a private repository or local storage. Review it before committing, and never copy credentials or private transcripts into a public example.

For platform-specific discovery, WorkBuddy/Kimi guidance and optional checkpoint commands, see [Cross-Agent Context and Handoff](../docs/cross-agent-collaboration.md). These templates do not install hooks, switch models, dispatch tasks, or synchronize chats. No installer behavior is changed by copying this directory.
