# Cross-Agent Context and Handoff

Use this workflow when configuring cooperation across agent tools, diagnosing missing shared context, or organizing project memory. Rule-entry setup is an agent-led workflow. Optional checkpoint, handoff, and resume CLI commands are documented below; they do not provide startup hooks, message transport, or automatic model switching.

## Discover before configuring

Identify the user's actual task, project root, relevant checkouts, participating tools, and their configured instruction sources. Inspect existing rules and state before proposing additions. A tool name, installed skill, symlink, or similarly named repository is not evidence of a working context handoff.

Separate these responsibilities:

| Layer | Purpose | Discovery examples |
|---|---|---|
| Shared general rules | Stable principles, preservation, model/tool selection, collaboration boundaries | A user-controlled rules file referenced or loaded by each tool |
| Tool entry | Load shared rules within that tool's own instruction hierarchy | Global instruction file or supported configuration |
| Project rules | Project constraints, workflows, validation, ownership conventions | Existing `AGENTS.md` or `CLAUDE.md` |
| Project index | Map confirmed project roots to rules and state | Optional existing registry or a small user-approved Markdown index |
| Project state | Current objective, decisions, progress, evidence, blockers, next action | Existing `PROJECT_STATE.md`, `CONTEXT.md`, or equivalent |

An index is useful for multiple projects; do not introduce it for a single project without a concrete need. Reuse an established state file rather than forcing a new filename. Global context must not substitute an unrelated objective for the user's current project request.

Inspect each participating tool's current documentation, installed implementation, and configuration. Common entry candidates include Codex's global `AGENTS.md`, Claude Code's applicable `CLAUDE.md`, OpenCode's configured global `AGENTS.md`, and DeepSeek Harness's home `AGENTS.md`. These are discovery hints, not universal paths or proof of automatic loading. For Hermes and other tools, discover the supported entry rather than guessing.

Confirm environment overrides, instruction precedence, filesystem permissions, project-root discovery, and whether external file references are actually loaded. If references are not expanded, use a supported instructions setting or explicitly instruct the agent to read the target. Avoid copying complete rules into every tool entry when one maintained source is sufficient.

## WorkBuddy adapter discovery

The macOS WorkBuddy build inspected on 2026-10-30 exposes a user/project rules loader and a separate project-guidance loader. Treat these findings as version-specific discovery evidence, not proof of runtime loading on another installation.

- **User rules:** inspect the effective user configuration root and its `rules/` directory. In the inspected installation, the candidate was `~/.workbuddy/rules/`; Markdown `.md` and `.mdc` files are supported. Verify the root from the installed loader, configuration, or diagnostics before writing.
- **Rule metadata:** the inspected parser recognizes `alwaysApply: true` for always-applied rules and `enabled: false` to disable a rule. Use a small, independently named adapter rather than overwriting a user's existing rule.
- **Project guidance:** the inspected loader checks the task working directory in this order: `CODEBUDDY.md`, `.codebuddy/CODEBUDDY.md`, then `AGENTS.md`, taking the first readable file. Do not assume that all three are merged or that it searches parent directories. Inspect existing higher-priority guidance before relying on `AGENTS.md`.
- **Loading conditions:** guidance/rules injection depends on the request path and mode; quick/ask-like paths or previously injected context can skip relevant loaders. Verify a suitable fresh task rather than assuming every request reloads external edits.
- **Account and memory scope:** the application also has account-scoped user memory. It is a separate mechanism; do not overwrite memory files, databases, credentials, or account state to install a rules adapter. Check account/environment overrides when observed behavior differs from the configured path.

A minimal rule can use this shape, replacing placeholders with verified paths before installation:

```markdown
---
alwaysApply: true
---
# Shared collaboration entry

Before substantive work, use the file-reading tool to read <shared-rules-file>,
<project-index-if-used>, and the actual project's existing rules and state.
Preserve other agents' updates and record file scope before overlapping edits.
Report inaccessible paths and distinguish configured files from verified loading.
```

After configuration, use the verification levels below. Ask the receiving WorkBuddy task to identify the files it actually read and summarize the project's objective, current ownership, and next action. Do not dispatch that request without user authorization. If the application has not produced loading evidence, report **configured; loading unverified**.

For current product behavior, consult the installed implementation and [WorkBuddy project documentation](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project); do not apply CodeBuddy CLI/IDE instructions to WorkBuddy solely because the products share a name or file convention.

## Plan and apply a narrow integration

For a setup request, report the discovered entry paths, proposed shared source, project-state paths, exact additions, backup location, and rollback method. Respect explicit authorization already provided in the session; ask only for unresolved choices or required permissions. An audit or recommendation alone does not authorize writes.

Back up existing files before editing, re-read them before writing, and preserve concurrent updates. Add a small adapter to each supported tool entry and project routing only where needed. Preserve unrelated provider, model, plugin, credential, permission, and startup configuration. Do not replace existing symlinks or consolidate physical skill copies as an incidental part of context setup.

Keep paths configurable or discover them from the environment. Do not publish a user's absolute paths, private project details, credentials, or session transcripts in a reusable skill. Machine-local adapters may contain verified local paths.

## Maintain state while working

During authorized task execution, agents should read the actual project's rules and state, then maintain meaningful progress there. Keep state concise:

- objective and observable completion criteria;
- confirmed decisions, their rationale, and material assumptions;
- completed work and relevant evidence;
- unverified items, blockers, and next action;
- participating agents and file scope when work overlaps.

Use first-principles reasoning to choose execution: start from the outcome, facts, assumptions, and actual constraints, then select the simplest feasible approach. Assess models, tools, skills, and agent participation by task fit, available capabilities, quality, time, and cost. Multiple agents are optional; add them when independent work or review justifies coordination overhead. Verify current model claims rather than embedding a permanent model ranking.

Before overlapping edits, confirm current ownership and scope. Re-read shared state before updating it. Old assignments are historical evidence, not reliable live locks. Resolve overlapping changes before writing; do not switch another agent's branch or overwrite its work. A state-file update is a handoff record, not authorization to send a message or start work in another thread.

For historical context already mixing multiple projects, keep the source intact. Register confirmed project paths and place new detailed progress in the corresponding project state. Extract historical summaries incrementally with source pointers and uncertainty notes when requested; do not bulk move, delete, or rewrite history based on guessed ownership. Ask only when project identity cannot be safely determined.

## Verify the handoff

Distinguish evidence levels in the report:

1. **Configured:** entry files exist, referenced paths resolve, original content is preserved, and changes match the plan.
2. **Loaded:** a fresh request or supported diagnostic shows the target tool loaded the entry and read the relevant shared/project files.
3. **Handoff verified:** a receiving agent correctly identifies the project objective, decisions, current ownership, and next action from those files. An authorized disposable marker can test write-back when needed; never modify product state merely to prove connectivity.

Stop at the strongest supported claim. Do not infer runtime loading from file existence or claim live chat synchronization, model switching, task dispatch, or accepted assignments without tool evidence. Do not interrupt an active user session or send a cross-thread test prompt without authorization. When runtime verification is unavailable, finish the safe configuration and clearly record what remains unverified.

Keep setup reversible: retain backups outside managed skill trees, record every changed path, and restore only the intended change after checking for newer edits. Report platform-specific limitations rather than presenting one tool's behavior as universal.


## Integrated task checkpoints

This repository includes optional concrete local commands for
`checkpoint`, `handoff`, and `resume`. These commands persist a small
task-scoped JSON record in `.agent-state/tasks/<task>.json` and immutable
history records under `.agent-state/history/<task>/`.
They are complementary to an existing `PROJECT_STATE.md` or `CONTEXT.md`,
not an instruction to overwrite those files.

The command records Git state without storing a raw diff or session
transcript. If the new working tree or commit differs from the saved
snapshot, resume returns `review-required`; the receiving agent must
inspect the difference rather than assuming the previous work is valid.
The CLI does not start other agents, execute tests, write Git commits,
or transfer local files between machines. Actual automatic triggers
remain platform-specific.

The integrated Closeout audit and evidence rules live under
`closeout/`. See [the staged implementation plan](multi-agent-development.md).


## Kimi Code CLI

Current Kimi Code CLI loads generic user-level Skills from
`~/.agents/skills/` and supports project `AGENTS.md` and
`.kimi-code/AGENTS.md`. The installer selects Kimi's native shared route
instead of creating extra links. A custom `KIMI_CODE_HOME` affects its
Kimi-specific directory, not the generic shared Skill root.

Review [Kimi Code support](kimi-code.md) for official documentation and
verification steps. Do not confuse the current TypeScript Kimi Code CLI with
the older Python kimi-cli, whose configuration defaults differ.
