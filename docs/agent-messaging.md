# Agent Handoff Messages

`message` is an optional, local file-based transport for short handoff notes
between agents and people working in the same project checkout. It was added in
`0.7.0-beta`. Messages are written under `.agent-state/messages/<task>/` inside
the receiving project's Git root and are read explicitly with the commands
below.

**What it is not:**

- not a message bus, queue service, or daemon;
- not network transport: it opens no sockets, sends no telemetry, and calls no
  external service;
- not an agent dispatcher: it never starts, resumes, wakes, or notifies the
  recipient, and it never performs the requested work;
- not live chat synchronization and not a substitute for human decisions.
  A message marked `--requires-approval` cannot be recorded as `completed`
  until a person runs `message approve`.

The transport only records intent and receipts. A receiving agent still has to
run `inbox`, decide whether to accept the work, and acknowledge it. A person
still decides whether a flagged message may complete, and merges, deployments,
and other protected actions keep their normal review and permission gates.

This is a Stage 1.5 slice of the multi-agent plan: local transport and explicit
acknowledgements. The Stage 2 orchestrator is still not implemented; see
[the two-stage development plan](multi-agent-development.md).

## Quickstart

Run these steps inside the project Git repository. `--project .` is the default
for most commands, but it is shown explicitly here.

```bash
# 1. Record the task checkpoint first (existing command, unchanged)
python3 <skill-root>/scripts/skill_atlas.py checkpoint --project . --task issue-28 \
  --agent Codex --summary "Camera control implemented" \
  --completed "Camera basics" --remaining "Object selection" \
  --next-action "Review the camera diff"

# 2. Queue one compact message. Nothing is sent or delivered yet.
python3 <skill-root>/scripts/skill_atlas.py message send --project . --task issue-28 \
  --from Codex --to "Claude Code" \
  --summary "Review the camera diff" \
  --conclusion "Camera works; selection remains" \
  --evidence src/camera.ts --requires-approval
# Prints the new message ID, for example msg_20261111T120000_ab12cd34ef

# 3. The recipient reads its inbox. This is a read-only local read.
python3 <skill-root>/scripts/skill_atlas.py message inbox --project . --task issue-28 \
  --agent "Claude Code"

# 4. The recipient shows the full envelope and receipts when it decides to act.
python3 <skill-root>/scripts/skill_atlas.py message show --project . --task issue-28 \
  --id <message-id>

# 5. The recipient acknowledges what actually happened.
python3 <skill-root>/scripts/skill_atlas.py message ack --project . --task issue-28 \
  --id <message-id> --agent "Claude Code" --status taken --note "reviewing"

# 6. For a flagged message, a person records approval before completion.
python3 <skill-root>/scripts/skill_atlas.py message approve --project . --task issue-28 \
  --id <message-id> --by "AJ" --note "review approved"

# 7. Only now can the recipient record completion.
python3 <skill-root>/scripts/skill_atlas.py message ack --project . --task issue-28 \
  --id <message-id> --agent "Claude Code" --status completed --note "merged to main"
```

`--project` must resolve to a Git repository. A non-Git directory is refused.
Message IDs and task-scoped history are local to this checkout; they are never
transferred automatically to another machine.

## Command reference

All five actions accept `--project`, `--task`, and `--format markdown|json`.
Markdown is the default. Invalid, conflicting, or refused operations exit with
status 2 and a message on stderr; the local state is not changed.

| Command | Purpose | Key flags |
|---|---|---|
| `message send` | Queue one compact message for another agent or person | `--from NAME`, `--to NAME`, `--summary TEXT` (required); `--conclusion TEXT`, `--evidence PATH` (repeatable), `--request-id ID`, `--ttl-hours HOURS` (default 24), `--reply-to MESSAGE_ID`, `--pass N`, `--requires-approval` |
| `message inbox` | List messages addressed to one agent; read-only | `--agent NAME` (required); `--status active\|all\|queued\|taken\|completed\|refused` (default `active`), `--include-expired` |
| `message show` | Show one message with its local receipts; read-only | `--id MESSAGE_ID` (required) |
| `message ack` | Record `taken`, `completed`, or `refused` | `--id MESSAGE_ID`, `--agent NAME`, `--status taken\|completed\|refused`, `--note TEXT` |
| `message approve` | Record a person's approval for a message that requires it | `--id MESSAGE_ID`, `--by PERSON`, `--note TEXT` |

Recipient names are matched case-insensitively, while the stored display name is
preserved. An agent name must start with a letter or digit and use at most 64
letters, digits, spaces, dots, dashes, underscores, or colons. A task ID uses at
most 80 letters, digits, dots, dashes, or underscores.

`send` notes:

- `--summary` is the one-line handoff. `--conclusion` is a short conclusion, not
  a transcript. `--evidence` takes short local pointers (paths, commit SHAs,
  issue numbers) and may be repeated.
- `--request-id` makes retries safe. Repeating the same request ID with the same
  content and options returns `duplicate` and the original message instead of
  creating a second message. Reusing the request ID with different content or
  options is refused. When omitted, an `auto-...` ID is generated.
- A retry is resolved before the reply chain is validated, so it still returns
  the original message after the parent has expired or been refused.
- `--reply-to` answers an existing message in the same task. The chain pass is
  derived automatically (`parent pass + 1`); `--pass` is only for validating or
  supplying that number explicitly.
- `--requires-approval` marks the message for the human approval gate.

`inbox` notes:

- The default `active` view hides terminal (`completed`, `refused`) and expired
  messages. `--status all` includes terminal messages; expired open messages are
  included only with `--include-expired`.
- At most 200 messages are returned per call; `truncated` is reported when more
  matched. Nothing is modified.

`approve` notes:

- Only a message sent with `--requires-approval` can be approved; approving any
  other message is refused.
- Expired or already terminal messages cannot be approved. Only one approval
  record is accepted: repeating it for the same person returns `duplicate`, and
  a different approver is refused so that the recorded person can confirm.

## States, receipts, and idempotency

| State | Meaning |
|---|---|
| `queued` | Written by the sender. No recipient action yet. |
| `taken` | The addressed recipient acknowledged taking the work. |
| `completed` | The addressed recipient recorded completion. If the message requires approval, a recorded approval must exist first. |
| `refused` | The addressed recipient declined the message. |
| `expired` | Derived, not stored: an open message whose `expires_at` has passed. `show` reports `status: expired`; `inbox` hides these by default; `ack` and `approve` are refused. |

The lifecycle is `queued` → `taken` → `completed` or `refused`; a recipient may
also record `completed` or `refused` directly from `queued`. Terminal statuses
cannot be changed, and repeating the same acknowledgement returns `duplicate`
without writing again. Only the addressed recipient may acknowledge a message.

Each message has an immutable JSON envelope plus separate mutable state, so an
acknowledgement never rewrites what the sender wrote. Every transition appends
one event to `receipts/<message-id>.jsonl` (`queued`, `taken`, `completed`,
`refused`, `approved`). Receipts are append-only local records, written under a
writer lock; they are evidence, not a tamper-proof audit log.

## Data layout

```text
<project-git-root>/.agent-state/
├── .lock                              # local writer lock (shared with checkpoints)
└── messages/
    └── <task>/
        ├── envelopes/<message-id>.json   # immutable message content
        ├── status/<message-id>.json      # current state, rewritten atomically
        ├── requests/<request-id>.json    # idempotency records
        ├── receipts/<message-id>.jsonl   # append-only transition events
        └── approvals/<message-id>.json   # person approval records, when required
```

The transport creates files only under `.agent-state/messages/`, never inside
your source tree. Keep message state out of Git: this repository ignores
`.agent-state/messages/` and `.agent-state/.lock`; in another project, add
those paths to `.gitignore` before creating state. Checkpoint files under
`.agent-state/tasks/` and `.agent-state/history/` keep their documented
behavior and may still be committed deliberately when a task must move between
machines. Committed or pushed message state is not the intended usage and may
expose project details.

## Limits

| Limit | Value |
|---|---|
| Default TTL | 24 hours |
| Maximum TTL | 720 hours (30 days) |
| Message chain | 10 passes; a further reply is refused |
| Inbox results per call | 200 (with truncation flag) |
| Messages per task | 5000 |
| Summary / conclusion / note | 2000 / 4000 / 2000 characters |
| Evidence entries | 20, each at most 300 characters |
| Task ID / request ID | 80 / 128 characters with restricted character sets |

A long exchange is a signal to stop and ask the user rather than continue
replying. The pass limit exists to bound local message chains, not to substitute
for task ownership.

## Safety and privacy

- **Local only.** No network calls, no telemetry, and no credential access. The
  transport never starts another agent and never executes the requested action.
- **No secrets.** Envelopes, status files, receipts, and approvals are plain
  JSON/JSONL on disk. Do not put API keys, tokens, passwords, private keys, full
  file contents, or session transcripts in a payload. Use short pointers and
  summaries instead.
- **Uncommitted message state.** `.agent-state/messages/` must stay uncommitted.
  It is a local working record; checkpoints follow their own documented rule.
- **Approval is a local label, not an identity check.** `message approve --by`
  records the name a person supplies; the tool does not authenticate that
  person. Do not approve on someone else's behalf, and do not treat an approval
  as a merge, deployment, or security sign-off.
- **No delivery guarantee.** A queued file does not mean the recipient read it.
  Only the recipient's own `ack` shows that. Do not report a message as
  delivered, taken, or completed without the corresponding local receipt.
- **No symlinked state paths.** The transport refuses to use an `.agent-state`
  tree, message subdirectory, or lock file that resolves through a symlink, so a
  repository cannot redirect message state outside its Git root.
- **Shared filesystem caveat.** Anyone with write access to the checkout can
  edit these local files. Treat receipts as local evidence, not as an
  audit-grade ledger.

## Worked example: Codex → Claude Code review with human approval

Scenario: `issue-28` needs a camera-control review. Codex implemented the change
and hands a compact review request to Claude Code. A person must approve before
the message can be completed, and the merge remains a separate human action.

```bash
# Codex: record the milestone, then queue the review request.
python3 <skill-root>/scripts/skill_atlas.py checkpoint --project . --task issue-28 \
  --agent Codex --summary "Camera control implemented" \
  --completed "Camera basics" --remaining "Object selection" \
  --next-action "Review the camera diff"
python3 <skill-root>/scripts/skill_atlas.py message send --project . --task issue-28 \
  --from Codex --to "Claude Code" \
  --summary "Review camera diff before merge" \
  --conclusion "Camera control works; selection is not started" \
  --evidence src/camera.ts --evidence "commit $(git rev-parse --short HEAD)" \
  --requires-approval
# Response includes the message ID, for example:
# - id: msg_20261111T120000_ab12cd34ef

# Claude Code (or the person operating it): read and inspect the message.
python3 <skill-root>/scripts/skill_atlas.py message inbox --project . --task issue-28 \
  --agent "Claude Code"
python3 <skill-root>/scripts/skill_atlas.py message show --project . --task issue-28 \
  --id msg_20261111T120000_ab12cd34ef

# Claude Code: accept the review and record the outcome.
python3 <skill-root>/scripts/skill_atlas.py message ack --project . --task issue-28 \
  --id msg_20261111T120000_ab12cd34ef --agent "Claude Code" \
  --status taken --note "reviewing camera diff"

# Claude Code: reply with the review result; the pass becomes 2 automatically.
python3 <skill-root>/scripts/skill_atlas.py message send --project . --task issue-28 \
  --from "Claude Code" --to Codex \
  --summary "Review complete: one fix needed" \
  --conclusion "Transform math is correct; add a null check in camera.ts" \
  --evidence src/camera.ts \
  --reply-to msg_20261111T120000_ab12cd34ef

# Codex: read the reply when it next checks its inbox.
python3 <skill-root>/scripts/skill_atlas.py message inbox --project . --task issue-28 \
  --agent Codex --status all

# A person reviews the change and records approval for the flagged message.
python3 <skill-root>/scripts/skill_atlas.py message approve --project . --task issue-28 \
  --id msg_20261111T120000_ab12cd34ef --by "AJ" --note "review approved"

# Claude Code: only now can completion be recorded. The merge is separate.
python3 <skill-root>/scripts/skill_atlas.py message ack --project . --task issue-28 \
  --id msg_20261111T120000_ab12cd34ef --agent "Claude Code" \
  --status completed --note "fix applied; merged after review"
```

What this example does **not** do: it does not wake Claude Code, prompt a model,
merge the branch, or notify anyone. Each step runs because a person or an
already-running agent chose to run it. If Claude Code never checks its inbox,
the message simply stays `queued` until its TTL expires.

## Optional MCP adapter

`scripts/mcp_agent_messages.py` (optional, added alongside this release) wraps
the same local transport as a stdio MCP server, so an MCP-capable client can
call `send_message`, `get_inbox`, `get_message`, and `ack_message` as tools.
The server requires `--agent`, which is the default sender/recipient for tool
calls; `send_message` can override it with `from`, and `get_inbox` and
`ack_message` can override it with `agent`. There is deliberately no approval
tool: approval stays a human CLI action. The adapter is a local stdio process;
it does not add network transport, recipient notifications, agent startup, or
dispatch. Protocol messages go to stdout; diagnostics go to stderr.

A generic client configuration example, using the common `mcpServers` shape:

```json
{
  "mcpServers": {
    "skill-atlas-messages": {
      "command": "python3",
      "args": [
        "/path/to/skill-atlas/scripts/mcp_agent_messages.py",
        "--project", "/path/to/your/project",
        "--agent", "Claude Code"
      ]
    }
  }
}
```

**Verify before relying on this.** MCP client configuration formats and file
locations differ between products and versions (for example `mcpServers` vs.
other keys, JSON vs. TOML, or a UI form), and the exact flag spellings must be
confirmed with `python3 <skill-root>/scripts/mcp_agent_messages.py --help`.
The example above was **not runtime-verified with any specific MCP client in
this change**. It is a starting point, not a claim of tested integration; treat
the adapter as optional and verify the client's current documentation and that
the process starts and lists tools before using it.

## Prior art

Agent HUD (<https://github.com/jazzenchen/agent-hud-open>) is an independent
open-source project that also presents agent activity and handoffs. It is
mentioned only as prior art for readers comparing approaches. Skill Atlas does
not integrate with, depend on, or endorse it, and no compatibility is claimed.

## Relationship to checkpoints and the Stage 2 orchestrator

- `checkpoint`, `handoff`, and `resume` record task evidence in
  `.agent-state/tasks/` and `.agent-state/history/`. Messages are additive:
  use a checkpoint for durable "what happened", and a message for a compact
  "please review/act" note.
- Messages do not create, claim, or transfer task ownership, do not isolate
  worktrees, and do not route work to whichever provider happens to be
  available.
- The Stage 2 orchestrator, durable task queue, provider adapters, quota and
  error handling, and automatic dispatch remain unimplemented. See
  [the two-stage development plan](multi-agent-development.md).
