# Skill Atlas: two-stage multi-agent development

## Product boundary

Keep Skill Atlas as the primary Skill discovery, comparison, recommendation,
installation planning, and skill orchestration product. Consolidate the
Closeout project into a bundled, evidence-driven verification module. Keep
standalone Closeout installations functional and never silently replace them.

## Stage 1: shared protocol and reliable recovery

1. Reuse each project's own AGENTS.md, architecture decisions, Git Issues,
   pull requests, and existing PROJECT_STATE.md/CONTEXT.md when present.
2. Use one task ID per handoff. Save local JSON checkpoints with branch,
   commit, dirty-worktree fingerprint, completed work, remaining work,
   reported test command/result, and one next action.
3. Distinguish checkpoint (intermediate), handoff (explicit transition),
   and resume (read-only receiving-agent check). All clients share one data
   contract, not a fabricated shared LLM memory.
4. Preserve the original Closeout audit, permission boundaries and evals
   inside Skill Atlas. Do not equate documentation with verified runtime.
5. Recheck real Git state. Stop and report conflicting uncommitted changes.
   Checkpoint files are local until reviewed, committed and pushed.
6. Provide optional installation adapters for Codex, Claude Code and OpenCode.
   Discover DeepSeek Harness, WorkBuddy and other platforms' actual loading
   contracts before claiming integration.

Success criteria:
- Existing discover/recommend/orchestrate/monitor/market/manage tests pass.
- Closeout inventory and eval validation pass.
- A synthetic Codex -> OpenCode -> Codex checkpoint/handoff/resume cycle
  preserves task context and flags divergent Git state.
- No automatic push, destructive cleanup, credential reads, provider switching,
  or unsupported usage-limit assumptions.

## Stage 2: optional agent orchestrator

**Not implemented yet.** After Stage 1 is validated with real agents:

1. Evaluate each provider's documented CLI/API, permissions, quotas and
   supported background or interactive operation.
2. Introduce a durable task queue and explicit task ownership with
   worktree isolation for parallel writers.
3. Use provider error codes and verified task states to distinguish
   quota exhaustion, transient failure, and task-level errors.
4. Allow routing to a different available agent only with supported
   credentials, compatible tooling and the user's approved policy.
5. Run project-native tests and Closeout verification before review.
6. Keep merges, deployments, database migrations and destructive actions
   behind explicit approvals; record costs and traceable results.

Never claim subscription quota pooling, transparent reasoning transfer,
or guaranteed failover when a provider rate-limits mid-operation.

## Sample project rule appendix

Add to project AGENTS.md without replacing existing engineering rules:

> Before a new task, inspect the project state and Git status. After a
> meaningful milestone, save a task-scoped Skill Atlas checkpoint. Before
> switching agents, create a handoff. On resume, compare checkpoint evidence
> with the real Git tree and review changed files before continuing. Run
> project-native tests; treat all saved test results as agent-reported.
> Never auto-commit, push, merge, migrate or deploy without authorization.

This is a behavioral rule, not a deterministic hook. For unavoidable token
exhaustion, local Git evidence and available commits are the fallback.
