# Skill Atlas 0.16: Evidence-Driven Agent Workflows

Roadmap and gap analysis for the 0.16 iteration.

- Status: planning document. It changes no product behavior and ships no code.
- Baseline: `main` = `3036ab8`, version `0.15.1-beta`, verified 2026-11-20.
- Authority: this document is a plan. Each task still needs its own branch,
  pull request, tests, documentation and review. Nothing here is an
  implementation claim.

Related: [Issue #3](https://github.com/Jorgut/skill-atlas/issues/3) (Stage 1
follow-up), [Issue #4](https://github.com/Jorgut/skill-atlas/issues/4) (Stage 2
proposal, explicitly out of scope), [multi-agent development](multi-agent-development.md),
[Model-Aware Handoff](model-aware-handoff.md), [Agent Handoff Messages](agent-messaging.md),
[Cross-Agent Context and Handoff](cross-agent-collaboration.md).

## 1. Why this iteration exists

The 0.15 line could record a checkpoint, a handoff, a local message envelope and
a Git sync warning. The `0.16.0-beta` cut adds one more slice — `sync summary`,
which turns the read-only Git check into an end-of-block nudge (PR #38) — but the
structural gap is unchanged. What Skill Atlas still cannot do is connect four
things that users and reviewers keep separating:

1. what an agent **claims** it did,
2. what the repository **actually** contains,
3. what tests were **actually** run against which commit,
4. what the receiving agent **verified** before continuing.

A checkpoint today is a short narrative plus Git fingerprints. A "tests passed"
line is stored as `agent-reported` and nothing checks it against the commit it
describes. The 0.16 iteration closes that gap in small, reviewable steps, and
adds a measurement for the cost and fidelity of the handoff itself (TASK 07).

The design constraint stays the same as 0.15: local-first, read-only by default,
no automatic dispatch, no automatic model switching, no credentials or session
content, and no claim that is stronger than the evidence behind it. Section 13
assesses what this iteration does to the Skill itself, positively and negatively.

## 2. Verified baseline

Everything in this section was executed or inspected on 2026-11-20. Commands are
reproducible from a clean checkout of `ae5a98d`. The baseline moved while this
document was being written: PR #38 merged at 15:06 and cut `0.16.0-beta`, so the
first draft's `3036ab8` / `0.15.1-beta` figures were re-measured rather than
carried over. That is exactly the drift this roadmap is meant to make visible.

| Fact | Verified value |
|---|---|
| Source repository | `/Users/aj/Jorgut-skills/skill-atlas` |
| Branch / commit | `main` = `ae5a98d` (`Merge pull request #38 from Jorgut/feat/summary-dirty`) |
| Version | `0.16.0-beta` (`skill.json`) |
| Working tree | clean; `main...origin/main` in sync |
| Installation copy | `~/.cc-switch/skills/skill-atlas` and `~/.agents/skills/skill-atlas` both at `ae5a98d`, `0.16.0-beta` |
| Open pull requests | none |
| Open issues | #3 (Stage 1 follow-up), #4 (Stage 2 proposal) |
| Environment | macOS 26.7.1, Python 3.12.4 |
| Local agent tools | `codex` 0.164.0, `opencode` 1.19.5, `claude` 2.1.268, `cursor-agent` 2026.05.24; `kimi` and `dsh` not on `PATH` |

### 2.1 Test baseline

```bash
python3 -m compileall -q scripts closeout tests
TMPDIR=/private/tmp python3 -m unittest discover -s tests -v
python3 closeout/scripts/run_evals.py validate
```

| Gate | Result |
|---|---|
| `compileall` | exit 0 |
| `unittest discover` | `Ran 272 tests in 24.301s` — OK |
| `run_evals.py validate` | `{"valid": true, "cases": 12, "kinds": ["behavior", "permission", "regression", "trigger"]}` |

This is the reproducible baseline for every later task: a PR whose suite differs
from 272 passing tests must explain the delta.

### 2.2 Behavioral probes run for this document

Three probes were run in disposable repositories under `/private/tmp`, never in a
project the user owns. They are listed because they change the shape of TASK 01.

| Probe | Command | Observed |
|---|---|---|
| Checkpoint size | `checkpoint --task probe-1 ...` in a two-file repository | 1297 bytes; keys `agent, completed, git, kind, next_action, recorded_at, remaining, schema_version, summary, task, tests` |
| Dirty-tree detection | append one line, then `resume` | `review-required` |
| Cross-worktree resume | write a checkpoint in worktree A, read it from worktree B | `no-checkpoint` |

The third probe is the important one. `.agent-state/` is created under
`git rev-parse --show-toplevel`, so it is **per worktree, not per repository**.
A handoff recorded in one worktree is invisible from a sibling worktree of the
same repository. That is exactly the layout this project recommends for parallel
tasks, so it is a confirmed gap, not a hypothetical one.

Also confirmed: Skill Atlas does not add `.agent-state/` to the target project's
ignore rules. In a project without that entry, `checkpoint` leaves
`.agent-state/tasks/<task>.json` and `.agent-state/history/...` as untracked
files, which a user can commit by accident. The documentation says state "stays
uncommitted"; there is no mechanism or warning behind that sentence.

## 3. Existing modules that 0.16 must extend

| Module | Current responsibility | Contract today | Tests | Doc |
|---|---|---|---|---|
| `scripts/agent_handoff.py` | `checkpoint`, `handoff`, `resume`, `sync status`, `sync summary`, `sync notify` | `.agent-state/tasks/<task>.json`, `schema_version: 1` | `tests/test_agent_handoff.py` | `docs/cross-agent-collaboration.md` |
| `scripts/agent_messages.py` | `message send/inbox/show/ack/approve` | immutable envelope + append-only receipts, `schema_version: 1` | `test_agent_messages*.py` (3 files) | `docs/agent-messaging.md` |
| `scripts/handoff_advisor.py` | read-only model/agent advice | `.skill-atlas/model-agent-profiles.json`, `schema_version: 1` | `tests/test_handoff_advisor.py` | `docs/model-aware-handoff.md` |
| `scripts/agent_environments.py` | `agents scan` local tool evidence | levels `not-detected` / `detected` / `configured`, plus `candidate` paths | `tests/test_agent_environments.py` | `docs/agent-environments.md` |
| `scripts/external_search.py` | executed public search | provider results + provenance, bounded | `test_external_search*.py` | `docs/external-search.md` |
| `scripts/skill_atlas.py` | unified CLI entry point | subcommand tree, `--format markdown\|json` | covered indirectly | `docs/cli-reference.md` |
| `closeout/` | bundled inventory + evals | 12 eval cases, read-only | `tests/test_closeout_tools.py` | `closeout/SKILL.md` |

Two invariants hold across all of them and must survive 0.16:

- read-only unless an explicit `--apply --confirm` pair is supplied;
- no network call unless a search mode, provider or `--fetch` is explicitly requested.

## 4. Gap matrix

Status vocabulary: **implemented** (usable and documented), **partial** (exists
but weaker than the 0.16 acceptance criteria), **missing** (no implementation),
**blocked** (cannot be finished in this iteration without something external).

### TASK 01 — Evidence-based handoff v2: **partial**

Implemented today:

- Git snapshot with branch, commit, tracked-patch digest, untracked sizes and
  mtimes, and a porcelain digest (`fingerprint`);
- read-only `git.sync` block and warnings on every checkpoint/handoff;
- `resume` comparing five fields and returning `review-required` on drift;
- a per-task current snapshot plus immutable history, written under a file lock.

Missing against 1.1–1.4:

| Requirement | Evidence of the gap |
|---|---|
| `task_id`, `source_agent`, `target_agent` | only `task` and `agent`; there is no target agent, so a handoff record cannot say who is expected to receive it |
| repository / worktree identity | not stored; `git.branch` + `git.commit` only, and `.agent-state` is per-worktree (see 2.2) |
| changed-files evidence | only `working_tree_changes` (a count) and digests; no file list, so a receiver cannot see *what* moved |
| test evidence | one `command`, one `result`, `evidence: agent-reported`; no timestamp, exit code, counts, commit binding, or log reference |
| verification status | no `recorded` / `verification-required` / `verified` / `review-required` / `insufficient-evidence` state on the record itself |
| dependency-file existence | `resume` never checks that files referenced by the handoff still exist |
| test evidence vs current code | `resume` compares Git fields but never asks whether the test evidence was produced at the recorded commit |

### TASK 02 — Skill–model outcome tracking: **missing**

`grep -rn outcome scripts/ docs/` returns only prose uses of the word. There is
no outcome schema, no store, no `outcome` command group, and no way to answer
"which skill/model combinations passed this kind of task".

### TASK 03 — Evidence-based recommendation v2: **partial**

`handoff_advisor.py` already implements the hard gates and the honesty rules that
TASK 03 must preserve: capability and tool exclusions, `access_status`, bounded
score intervals, `provisional-shortlist` instead of a forced winner, and the
`>= 5` trials / `90` day window in `_quality()`.

Missing: any data source other than a hand-authored registry entry. The adviser
reads `task_evaluations` that a person typed; it has no way to consult recorded
outcomes, and no way to show sample size or evidence age derived from real runs.

### TASK 04 — Agent compatibility and onboarding: **partial**

`agents scan` reports `not-detected` / `detected` / `configured` only, and the
code base has no `loaded` or `handoff-verified` evidence path. There is no
published compatibility matrix, no five-minute onboarding flow, and no fixture
repository covering success, mismatch, test failure, insufficient evidence and an
unsupported agent.

The important asymmetry is already correct and must not regress: candidate paths
stay hints and never reach `configured`.

### TASK 05 — Remote skill verification (admission deferred): **missing**

`external_search.py` executes bounded searches, deduplicates provenance, and
labels results as metadata candidates. It has no verification stage, no trust
policy, no pinned-revision or content-hash check, no admission record and no
approval gate. Nothing in the current code grants execution authority to a remote
skill, which is the correct starting point — the gap is the absent verification
pipeline, not an unsafe default.

Scope decision (2026-11-20): 0.16 delivers **verification records and threat
tests only**. A candidate gains a recorded verification result — pinned revision,
content hash, integrity check, permission requirements and adversarial-content
warnings — or it stays unverified. The admission stage is explicitly **not
implemented**, is documented as such, and moves to 0.17. This keeps the safety
boundary the original request asked for while refusing to grow a second product
surface in the same release.

### TASK 06 — Stage 2 orchestration: **deferred**

Correctly absent: no background agent execution, no automatic provider switching,
no automatic merge or deploy. This document adds no Stage 2 work.

### TASK 07 — Handoff context budget and fidelity: **missing** (new, see 8)

## 5. Overlap with existing issues

| Task | Relation to #3 | Rule |
|---|---|---|
| 00 | #3 is an input, not a duplicate | this document cites #3; it does not restate its acceptance criteria as new work |
| 01 | #3 requires a real Codex → OpenCode → Codex handoff on disposable branches | TASK 01 supplies the record format and the verification; the real run is the shared acceptance evidence for both |
| 02, 03 | independent | no #3 overlap |
| 04 | #3 requires verifying instruction loading per platform | TASK 04 turns that into the `loaded` and `handoff-verified` levels; the platform verification itself is #3's work |
| 05 | independent | no #3 overlap |
| 06 | #4 proposes it | out of scope for 0.16; do not expand it |

No new tracking issue is created by this document. If one is wanted later it
should be a single 0.16 tracker that links the seven pull requests, not a copy of
them.

## 6. Dependency graph

```text
                     Issue #3 (Stage 1 follow-up, external constraint)
                        |                        |
                        | real-agent evidence    | loading verification
                        v                        v
  TASK 01  handoff evidence v2  ------------>  TASK 04  compatibility & onboarding
     |        |                                        ^
     |        |                                        | needs 01's evidence levels
     |        v                                        |
     |   TASK 07  context budget & fidelity            |
     |                                                |
     v                                                |
  TASK 02  outcome tracking                           |
     |                                                |
     v                                                |
  TASK 03  outcome-aware advice                       |
                                                      |
  TASK 05  remote skill verification (no admission)  --- needs only external_search
```

Hard edges: 02 needs 01's schema; 03 needs 02's store; 07 needs 01's record and
`critical_facts`; 04 needs 01's evidence states plus real-agent runs. There is no
edge from 05 to the handoff tasks, which is why it can be scheduled anywhere.

## 7. Proposed pull requests

One task, one branch, one pull request, merged before the dependent task starts.

| # | Branch | Change | Files (expected) | Depends on | Risk |
|---|---|---|---|---|---|
| 00 | `docs/016-evidence-roadmap` | this document | `docs/roadmap-evidence-driven-workflows.md`, `README.md` (one index row) | — | none, docs only |
| 01 | `feat/evidence-handoff-v2` | versioned evidence records, test evidence, receiver verification, new states | `scripts/agent_handoff.py`, `scripts/skill_atlas.py`, `tests/test_agent_handoff.py`, `docs/cross-agent-collaboration.md`, `docs/cli-reference.md` | 00 | medium: schema v2 read/write |
| 02 | `feat/skill-model-outcomes` | outcome schema, `outcome record/list/show/summary` | `scripts/outcomes.py` (new), `scripts/skill_atlas.py`, `tests/test_outcomes.py` (new), `docs/outcomes.md` (new), `docs/cli-reference.md` | 01 | medium: new state store |
| 03 | `feat/outcome-aware-recommendations` | consult outcomes in `handoff advise` | `scripts/handoff_advisor.py`, `tests/test_handoff_advisor.py`, `docs/model-aware-handoff.md` | 02 | low–medium: ranking stability |
| 04 | `feat/agent-compatibility-onboarding` | `loaded` / `handoff-verified` evidence, matrix, onboarding, fixtures | `scripts/agent_environments.py`, `tests/test_agent_environments.py`, `docs/agent-environments.md`, `docs/GETTING_STARTED.*`, `examples/handoff-fixture/` | 01, #3 runs | medium: claim surface |
| 05 | `feat/remote-skill-trust` | verification record for external candidates plus threat tests; admission explicitly not implemented | `scripts/external_search.py`, `scripts/security_review_skills.py`, new `scripts/skill_verification.py`, tests, `docs/external-search.md` | — | medium: security wording |
| 07 | `feat/handoff-context-budget` | context measurement and fidelity probe | `scripts/agent_context.py` (new), `scripts/agent_handoff.py`, `scripts/skill_atlas.py`, tests, `docs/handoff-context.md` (new) | 01 | low: additive records |

Parallel work is allowed only between branches that share no file: 05 can run
alongside 01; 04 must wait for 01 because both touch the evidence vocabulary.

## 8. TASK 07: handoff context budget and fidelity

This task is new in 0.16 and comes from a concrete user question: when a project
is handed off, does the receiving agent re-read the whole project, how much
context does it consume, and what is lost when it only reads the handoff?

### 8.1 Measured starting point

| Measurement | Value | Source |
|---|---|---|
| One checkpoint record | 1297 bytes (≈0.3k tokens) | probe in 2.2 |
| Tracked `.py` + `.md` in this repository | 1.13 MB (≈296k tokens at bytes/4) | `git ls-tree -r -l HEAD` |
| Whole tracked tree incl. assets | 9.05 MB | same |

The ratio is roughly 1:900. Re-reading the entire project does not fit in any
practical context window, so compression is not optional and "read only the
handoff" is not a shortcut — it is the only feasible strategy. The real question
is therefore not *how many tokens* a handoff costs. It is whether a small handoff
lets the receiver **verify the right things cheaply**, and whether the receiver
notices what the handoff left out.

### 8.2 Data-source boundary (decided)

Three sources are distinguishable, and they must never be mixed in one number:

| Source | Meaning | Trust label |
|---|---|---|
| `locally-observed` | measured by Skill Atlas itself: artifact size, pointer targets, declared read set | locally observed |
| `agent-reported` | the agent says what it read or how many tokens it used | `agent-reported` |
| `provider-observed` | token counts read from a tool's local session store | **not in 0.16** |

Decision for 0.16: Skill Atlas keeps its "no session data" promise. No provider
session file is read by any command in this iteration. The provider adapter is
recorded here as future work and requires an explicit opt-in flag plus its own
privacy review before it can exist.

### 8.3 Metrics

| Metric | Definition | Answers |
|---|---|---|
| `artifact_bytes` / `artifact_tokens_estimate` | size of the checkpoint and message records for a task | what a handoff costs to transmit |
| `rescan_ratio` | bytes the receiver declares it read ÷ bytes of the referenced tree | did it re-read the project |
| `compensation_reads` | files opened beyond the pointers the handoff supplied | how much the handoff failed to explain |
| `pointer_hit_rate` | supplied pointers that were used or verified ÷ pointers supplied | are the pointers useful |
| `probe_recall` | critical facts the receiver restated correctly ÷ critical facts recorded | did compression lose something that mattered |
| `unverified_share` | conclusions with no verifiable reference | how much of the handoff is narrative only |

Only the first is measurable without cooperation. The rest require either a
declared read set or the probe, and must be labelled accordingly in output.

### 8.4 Record sketch (additive, versioned)

`checkpoint` v2 gains an optional `context` block; nothing is required, so v1
readers and existing files keep working:

```json
{
  "schema_version": 2,
  "task": "issue-28",
  "context": {
    "budget": {
      "artifact_bytes": 1297,
      "artifact_tokens_estimate": 324,
      "pointer_count": 4,
      "referenced_bytes": 48213,
      "full_rescan_bytes": 1183259,
      "observed_at": "2026-11-20T10:00:00Z"
    },
    "usage": [
      {
        "agent": "OpenCode",
        "phase": "pre-verification",
        "source": "handoff",
        "bytes": 1297,
        "tokens": null,
        "evidence": "locally-observed"
      }
    ],
    "probe": {
      "critical_facts": 6,
      "restated_correctly": 4,
      "missing": ["the rejected cache design", "the migration guard"],
      "result": "partial-recall"
    }
  }
}
```

`critical_facts` themselves belong to TASK 01's evidence record, not here: each
fact is an obligation with a kind (`invariant`, `decision`, `rejected-alternative`,
`trap`, `verification`), one sentence, and a pointer. TASK 07 only measures them.

### 8.5 Acceptance for TASK 07

- `context report --task` prints every metric with its evidence label, and prints
  `unverified` where only a declaration exists.
- A repository with no `.agent-state` still returns a clean empty report.
- No session file, credential, source file content or diff is read; the command
  reads only `.agent-state` records and `git ls-tree` metadata.
- Deleting `.agent-state` never changes a pass/fail result elsewhere.
- The probe never blocks a resume; it reports `partial-recall` or
  `review-required` and leaves the decision to the receiver.

## 9. Compatibility and rollback policy

- **Schema versions are additive.** TASK 01 reads `schema_version: 1` and writes
  `2`; `resume` accepts both, and an old reader must fail with a named error
  rather than misinterpreting a v2 file. The same rule applies to the outcome
  store in TASK 02 and to message envelopes.
- **CLI compatibility.** No existing flag, subcommand or JSON key is renamed or
  removed in 0.16. New keys are additive; new commands are new subcommands.
- **Rollback.** TASK 00 is a documentation revert. Code tasks are reverted with a
  single `git revert`; because state files are local and uncommitted, a revert
  never needs a data migration. A v2 state file left behind is readable by the
  reverted v1 code only through the compatibility reader, so the revert order is:
  revert the code, keep the state, verify `resume` still reports honestly.
- **Evidence vocabulary is shared.** `recorded`, `verification-required`,
  `verified`, `review-required`, `insufficient-evidence` must mean the same thing
  in the CLI, the JSON and the documentation, or the vocabulary is rejected in
  review.

## 10. Release gates and evidence labels

Every code task must pass, in its own worktree:

```bash
python3 -m compileall -q scripts closeout tests
python3 -m unittest discover -s tests -v
python3 closeout/scripts/run_evals.py validate
```

Additionally: no CLI regression, no unauthorized network behavior, no sensitive
data in JSON/logs/Git, explicit handling of older state files, diagnosable test
failures, documented recovery for partial failures, and documentation that
matches the implementation.

Every claim in a PR body carries exactly one label: `simulated`, `locally tested`,
or `real-agent verified`. A task whose real-agent run was impossible is reported
as `blocked` with the reason, never as complete.

### Documentation budget

`SKILL.md` is loaded into an agent's context every time the skill is selected, so
its size is a user cost, not an author convenience. Two rules apply from the first
PR that edits it (TASK 01):

- the frontmatter `description` stays at or below 70 words — it is the trigger
  surface, and every added capability cluster dilutes it;
- `SKILL.md` size is a **ratchet**, not an absolute cap: the reviewed baseline is
  committed next to the test (currently 605 lines / 43,605 bytes), and growth
  beyond a small allowance requires
  updating that baseline in the same pull request. The author consciously signs
  the growth; there is no arbitrary line count to game.

A new capability occupies at most "when to use it, one command, one link" in
`SKILL.md`; detail belongs in `docs/`. Section 13 records why this exists.

## 11. Risks and open decisions

| Risk | Impact | Mitigation |
|---|---|---|
| Schema v2 breaks old checkpoints | silent misinterpretation of a handoff | dual reader + named error + fixture from a real v1 file |
| Per-worktree `.agent-state` | handoff invisible to the next worktree | decide in TASK 01: shared state under `--git-common-dir`, or an explicit transfer step; must not silently change the location for existing users |
| Untracked `.agent-state` in user projects | accidental commit of local state | warn on checkpoint when the path is not ignored, or document the one-line ignore rule |
| `handoff advise` ranking shifts once outcomes exist | users see a different recommendation with no explanation | keep the 5-trial / 90-day gate, show sample size and evidence age, keep `provisional-shortlist` |
| Compatibility wording overreaches | claims of support that were never verified | the five evidence levels are the only allowed vocabulary; `configured` never becomes `loaded` without a runtime observation |
| Remote trust scope creep | accidental execution authority | 0.16 stops at verification records; admission is not implemented; no install, no execution |
| `SKILL.md` grows past the context it is meant to save | every invocation pays the extra tokens | router rule + ratchet in section 10, rationale in section 13 |

Open decisions to settle before the dependent task starts:

1. Shared vs per-worktree state location (TASK 01, blocks 07's cross-worktree story).
2. Whether a 0.16 tracker issue is wanted, or the six PRs are tracked by #3 alone.
3. Whether `context` is a new top-level command group or a `handoff context`
   subcommand. Current proposal: top-level `context`, matching `message`, `sync`
   and `disk`.
4. Whether the real-agent fixture repository is published in `examples/` or kept
   as a generated fixture in tests.

## 12. Non-goals

Not in 0.16: automatic cross-provider dispatch, automatic model switching,
unauthorized background agent execution, automatic PR merge or deploy, reading
conversation history, reading provider session files, live cost or quota
calculation, and remote-skill **admission** (verification records ship, admission
does not). The first six remain Stage 2; admission moves to 0.17. All of them
stay deferred until verified evidence, permission control and a human approval
mechanism exist.

## 13. Impact on the Skill itself

The Skill is three artifacts at once: a Markdown file an agent reads, a CLI other
code calls, and a promise a stranger trusts. 0.16 changes all three, unevenly.

### 13.1 Measured starting point

| Surface | Value |
|---|---|
| `SKILL.md` | 605 lines, 43,605 bytes, ≈10.9k tokens at bytes/4 |
| frontmatter `description` | ≈50 words, 9 capability clusters |
| top-level sections | 25 |
| subcommands (`add_parser` calls) | 44 |
| `docs/` | 5,477 lines, 281 kB, ≈70k tokens |
| tests | 272 in 24s |
| `checkpoint` / `handoff` / `resume` mentions | 53 across 5 files (`SKILL.md` 18) |
| deployment | 1 canonical copy + 5 symlinks, switched at once, no staged rollout |

Estimated 0.16 growth: six capability sections at 25–35 lines each, about +150 to
+200 lines, which is **+25% to +33% on every invocation** — including the requests
that never touch a handoff.

### 13.2 Positive

- The narrative stays coherent. 0.15 started from a version label that hid three
  merged pull requests; 0.16 pushes the same logic onto tests, handoffs and
  outcomes.
- Evidence vocabulary reaches the instructions. After TASK 01 a receiving agent
  meets `verification-required` and `insufficient-evidence` instead of treating
  `checkpoint-consistent` as permission to continue.
- `handoff-verified` stops being an unbacked phrase in the collaboration guide and
  becomes a recorded level.
- The differentiation is real: most skill managers stop at installation. The
  unmet need is "how do I know it actually did the work".

### 13.3 Negative

| Mechanism | Effect |
|---|---|
| Load tax | `SKILL.md` is injected on every selection. Adding sections spends other people's context to save our documentation effort. |
| Trigger dilution | The description already lists nine capability clusters. `outcome`, `context` and `trust` are common words; Claude Code and OpenCode select skills semantically, so a false trigger costs the full load. A top-level `context` command is the riskiest of the three names. |
| Internal contradiction | `checkpoint`/`handoff`/`resume` already appear 17 times in `SKILL.md`, 12 in `agent-messaging.md`, 12 in `model-aware-handoff.md`, 7 in `cross-agent-collaboration.md` and 4 in `closeout/SKILL.md`. Two more sections make seven places that describe one state machine; an agent will follow whichever line it reads first. |
| Hidden contracts | `resume` status strings are consumed inside the project: `handoff_advisor.py` sets `handoff_ready` from `checkpoint-consistent`. The MCP adapter mirrors `agent_messages` limits into a JSON Schema. Renaming a value or adding a field breaks a caller, not just a document. |
| Promise surface | `verified` means the evidence matches the current HEAD, not that the code is correct. `"we have a trust policy"` will be read as a safety endorsement. `rescan_ratio` derived from declarations will be read as a measurement. |
| Release surface | Six merges means six windows where the installed copy, the source checkout and a running agent's loaded instructions disagree. |

### 13.4 Guardrails (decided 2026-11-20)

1. **Router plus ratchet.** `SKILL.md` describes when to use a capability and
   links to detail; the ratchet and the description cap are defined in section 10.
2. **Status vocabulary freeze.** `checkpoint-consistent`, `review-required` and
   `no-checkpoint` are an API. New evidence semantics go into subfields; the
   outer values and their consumers stay unchanged.
3. **Scope ruling.** TASK 05 ships verification records and threat tests.
   Admission is documented as absent and moves to 0.17. TASK 07 measures locally
   and never reads session files.

### 13.5 What these guardrails do not fix

- Wording cannot fully control how strong a claim feels. Some readers will treat
  `verified` as `correct` no matter what the documentation says, so the CLI output
  itself has to carry the qualifier.
- Threat tests enumerate known bad patterns; passing them never proves a remote
  skill is safe.
- The ratchet slows growth; it does not make a long file good. Review still has to
  ask whether a paragraph belongs in `docs/` instead.

## Appendix: verification log

```text
# Re-verified after PR #38 moved main from 3036ab8 (0.15.1-beta) to ae5a98d (0.16.0-beta).
$ git -C /Users/aj/Jorgut-skills/skill-atlas log --oneline -1 origin/main
ae5a98d Merge pull request #38 from Jorgut/feat/summary-dirty

$ git -C /Users/aj/Jorgut-skills/skill-atlas status --porcelain --branch
## main...origin/main            (clean)

$ wc -l scripts/*.py | tail -1
10804 total

$ python3 -m unittest discover -s tests
Ran 272 tests in 24.301s
OK

$ python3 closeout/scripts/run_evals.py validate
{"valid": true, "cases": 12, "kinds": ["behavior", "permission", "regression", "trigger"]}
```

Probe repositories were created under `/private/tmp`, measured, and removed; no
user project was modified.
