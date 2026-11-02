# Model-Aware Handoff

This is an evidence-aware, **read-only** Stage 1 adviser. It is not an automatic
agent router, provider API, quota service, or a live model leaderboard.

## Run before handing a task to another agent

Use a task-scoped checkpoint created by the existing Skill Atlas commands:

```bash
python3 /path/to/skill-atlas/scripts/skill_atlas.py handoff advise \
  --project ./JANSO --task issue-10 --format json

# Without a checkpoint, supply the task manually. This is not handoff-ready:
python3 scripts/skill_atlas.py handoff advise --project . --task issue-10 \
  --description "Fix React canvas zoom and coordinate transformations" \
  --task-type code --profiles /path/to/reviewed-profiles.json
```

The default local profile source is `.skill-atlas/model-agent-profiles.json`
under the target project. It is **not** created automatically. Start with
[`examples/model-agent-profiles.example.json`](../examples/model-agent-profiles.example.json),
replace all placeholder IDs with real identifiers and add factual evidence.
It must not contain API keys, access tokens, credentials, or secret data.

The adviser reads the previous checkpoint's `next_action` when no
`--description` is given. It checks the current Git branch, HEAD, dirty-worktree
digest, and current state against the checkpoint. A mismatch produces
`handoff_ready=false`, even if model comparisons are available. With no
checkpoint the system may still offer an advisory shortlist but cannot
claim handoff readiness.

## Separate registries

- **Models**: ID, supported capability areas, inspectable capability evidence,
  access status, optional task-specific success metrics, optional user-reviewed
  relative cost score.
- **Agents**: ID, declared supported model IDs, required tool access,
  access status, optional user-reviewed handoff-safety score.

The example file contains deliberately fictitious IDs. It is a schema example,
not an active model ranking or a claim about provider subscriptions.

## Decision sequence

1. Determine the next task type (explicit override is best; text classifier
   provides a conservative initial guess).
2. Apply **hard exclusions** to model capability, supported agent-model pair,
   required tool set, and user-declared unavailable access.
3. Score eligible pairs with declared task fit (35), observed comparable task
   success (25), tool coverage (20), user-reviewed relative cost (15), and
   user-reviewed handoff safety (5).
4. Missing quality, cost, or safety evidence is **not** filled with guessed
   zeros or invented averages: scores become a bounded interval.
5. A primary suggestion exists only when one candidate is demonstrably
   better on the available inputs and its own score is fully evidenced.
   Otherwise output a **provisional shortlist**, with missing evidence.
6. Treat any access status as a local assertion, never a real-time availability,
   quota, or billing check. Automatic selection requires a separate Stage 2
   provider adapter and authorization.

The evaluator requires >=5 trials in the same task type and a timestamp within
90 days to count observed success rates. The cost score is explicitly a
**user-reviewed relative score**, not a live API price quote. Real-time cost,
latency, service health, model version compatibility, and authorization need
separate verification before execution.

## Output contracts

Possible statuses:
`needs-task-description-or-type`, `needs-profiles`,
`no-eligible-candidates`, `provisional-shortlist`, `evidence-ranked`.

All outputs include `read_only=true`, `automatic_dispatch=false`,
`no_provider_authentication_or_quota_checks=true` and the checkpoint
validation state. No commands are executed in external model providers.

## Later improvements

Connect project test results and user-approved model benchmarks with dated,
per-task evidence. Add provider adapters to validate the available model
catalog and real cost data, without storing credentials in registry files.
Model names and claims change; never hard-code permanent brand rankings.
