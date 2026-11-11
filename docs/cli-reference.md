# Component CLI Reference

The unified command tree is documented in [SKILL.md](../SKILL.md). Use these lower-level helpers for automation, custom output formats, or debugging. They preserve the same permission and review requirements.

For executed public discovery use the unified CLI, not the offline component helpers:

```bash
python3 <skill-root>/scripts/skill_atlas.py discover similar pdf --search-mode web --format json
python3 <skill-root>/scripts/skill_atlas.py recommend tool blender --search-mode hybrid
python3 <skill-root>/scripts/skill_atlas.py market refresh --category pdf --search-mode web
```

See [external search](external-search.md) for provider/authentication options,
status contracts, bounded requests, and the review boundary. Existing
`--mode quick|balanced|benchmark` remains research depth; `--search-mode`
controls local/network scope. Lower-level discovery/recommendation helpers
below remain offline unless their existing command explicitly checks upstream.

Markdown summary:

```bash
python3 <skill-root>/scripts/audit_skills.py --format markdown
```

Machine-readable JSON:

```bash
python3 <skill-root>/scripts/audit_skills.py --format json
```

Recommend skills for a product:

```bash
python3 <skill-root>/scripts/recommend_skills.py --request "A concise task or product description" --format markdown
python3 <skill-root>/scripts/recommend_skills.py --request "A concise task or product description" --format json
python3 <skill-root>/scripts/recommend_skills.py --request "A concise task or product description" --root /custom/skills
```

`--product` remains a compatibility alias for older callers.

Full TSV inventory:

```bash
python3 <skill-root>/scripts/audit_skills.py --format tsv
```

Check recorded upstream URLs. This requires network permission in sandboxed environments:

```bash
python3 <skill-root>/scripts/audit_skills.py --check-upstream --format markdown
```

Scan a custom root:

```bash
python3 <skill-root>/scripts/audit_skills.py --root /path/to/search --format markdown
```

Generate external discovery briefs:

```bash
python3 <skill-root>/scripts/discovery_brief.py --format markdown
python3 <skill-root>/scripts/discovery_brief.py --focus ux --limit 20
python3 <skill-root>/scripts/discovery_brief.py --format json
```

Generate full external discovery batches:

```bash
python3 <skill-root>/scripts/make_discovery_batches.py --format markdown --batch-size 25
python3 <skill-root>/scripts/make_discovery_batches.py --format json --batch-size 25
```

Run static security review:

```bash
python3 <skill-root>/scripts/security_review_skills.py --path /path/to/skill --format markdown
python3 <skill-root>/scripts/security_review_skills.py --path /path/to/skill --format json
python3 <skill-root>/scripts/security_review_skills.py --path /path/to/skill --strict --format markdown
```

Review default local user skill roots:

```bash
python3 <skill-root>/scripts/security_review_skills.py --format markdown
```

## Local project root audit

The unified CLI includes a read-only `projects audit` command for duplicated
project copies and divergent project documents:

```bash
python3 <skill-root>/scripts/skill_atlas.py projects audit \
  --project . --project /path/to/other-copy
python3 <skill-root>/scripts/skill_atlas.py projects audit \
  --root ~/Projects --depth 2 --format json
```

`--root` searches descendants only; the root itself is not reported (use
`--project` for it). `--depth` limits discovery: direct children are depth 1,
and the default is 2. The audit groups copies as confirmed (normalized git
remote, compared case-insensitively) or probable (case-folded directory name),
hashes the listed agent-facing project documents up to 256 KiB without printing
their contents, and flags divergent documents and nested project roots. It never
runs git (`.git/config` and `.git/HEAD` are parsed by hand), writes nothing, and
makes no network calls. Recommendations are plans requiring user confirmation.
See [Project Root and Duplicate Documentation Audit](project-root-audit.md) for
identity rules, the hash cap, output contract, and limitations.

## Local agent environment scan

The unified CLI includes a read-only `agents scan` command that reports which
cataloged coding-agent tools leave local evidence, their rule and skill roots,
shared physical skill roots, and local Skill Atlas copy versions:

```bash
python3 <skill-root>/scripts/skill_atlas.py agents scan
python3 <skill-root>/scripts/skill_atlas.py agents scan --project . --format json
python3 <skill-root>/scripts/skill_atlas.py agents scan --home /path/to/home
```

It reads filesystem metadata and local `skill.json` manifests only: it never
executes a tool, opens no network connection, reads no credentials or session
data, and writes nothing. Levels are file-evidence levels only (`not-detected`,
`detected`, `configured`) and never prove runtime loading. Candidate paths and
home overrides remain unverified hints. See
[Local Agent Environment Scan](agent-environments.md) for the tool catalog, JSON
contract, limitations, and verification guidance.

## Local disk usage audit

The unified CLI includes a read-only `disk scan` command for agent homes,
caches, sessions, plugins, project media, build artifacts, and Git objects:

```bash
python3 <skill-root>/scripts/skill_atlas.py disk scan
python3 <skill-root>/scripts/skill_atlas.py disk scan \
  --root ~/Documents/ChatGPT --root ~/Documents/Codex --min-file-mb 100
python3 <skill-root>/scripts/skill_atlas.py disk scan --project . --format json
```

Flags: `--home PATH` (known-root base, default user home), repeated
`--root PATH`, `--project PATH`, `--top N` (default 15, bounded to 0–100),
`--min-file-mb N` (default 200; files whose allocated size is at or above),
`--max-entries N` (default 400000, per-root safety limit), and `--format
markdown|json`. Sizes are reported as allocated bytes (`st_blocks × 512`, the
real disk usage) with apparent bytes (`st_size`) in parentheses when they
differ; the largest-files threshold, ordering, and risk totals use allocated
bytes. The scan reads metadata only, never follows symlinks while walking, and
never deletes, moves, compresses, or archives anything; categories, risk levels,
and suggested actions are name-based heuristics and plans, not cleanup. See
[Disk Usage Audit](disk-scan.md) for known roots, categories, the JSON contract,
and limitations.

## Local agent messages

The unified CLI includes an optional `message` group for compact cross-agent
handoff notes. All actions accept `--project` and `--task`; Markdown is the
default output and `--format json` returns the full result object.

```bash
python3 <skill-root>/scripts/skill_atlas.py message send --project . --task issue-28 \
  --from Codex --to "Claude Code" --summary "Review the camera diff" \
  --conclusion "Camera works; selection remains" --evidence src/camera.ts \
  --requires-approval --request-id review-28-1

python3 <skill-root>/scripts/skill_atlas.py message inbox --project . --task issue-28 \
  --agent "Claude Code"
python3 <skill-root>/scripts/skill_atlas.py message show --project . --task issue-28 \
  --id <message-id>
python3 <skill-root>/scripts/skill_atlas.py message ack --project . --task issue-28 \
  --id <message-id> --agent "Claude Code" --status taken --note "reviewing"
python3 <skill-root>/scripts/skill_atlas.py message approve --project . --task issue-28 \
  --id <message-id> --by "AJ" --note "review approved"
```

This is local file transport under `.agent-state/messages/<task>/`. It sends
nothing over the network, does not notify or start the recipient, and refuses
to record `completed` for a `--requires-approval` message until a person
approves it. Keep `.agent-state/messages/` uncommitted and never place
secrets in a payload. See [Agent Handoff Messages](agent-messaging.md) for states, data
layout, limits, and a worked example.
