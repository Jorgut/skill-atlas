# Component CLI Reference

The unified command tree is documented in [SKILL.md](../SKILL.md). Use these lower-level helpers for automation, custom output formats, or debugging. They preserve the same permission and review requirements.

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
