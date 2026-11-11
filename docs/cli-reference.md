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
