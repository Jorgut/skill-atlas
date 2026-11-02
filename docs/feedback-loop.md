# Skill Atlas Feedback Loop

Local-first issue reporting. No hidden telemetry or background monitoring.

## Detect an objective failure

python3 scripts/skill_atlas.py feedback detect --project . --task issue-10

The detector reads the current Git checkpoint. When it differs from
saved evidence, it builds a safe report draft using only the names
of changed Git evidence fields. No private diff or local file path is
included. Detection itself is read-only.

## Report a problem in natural language

An Agent may translate a user's description into the CLI fields below.
The CLI does not send data merely because an Agent describes a failure.

python3 scripts/skill_atlas.py feedback prepare --title "Missing state" --summary "The receiving Agent did not load the checkpoint" --category handoff --source-project JANSO --output /tmp/atlas-feedback.json

Preview before any network access:

python3 scripts/skill_atlas.py feedback submit --file /tmp/atlas-feedback.json

With explicit approval and a GitHub token with Issues write permission,
repeat the submit command with --confirm. The CLI scans open and closed
GitHub Issues for matching fingerprints and similar titles. Duplicate
checks fail closed on network errors. Reports are restricted to the
Jorgut/skill-atlas repository.

Redaction masks common credentials, email addresses and local home
paths. It cannot prove the report contains no private data, so
always review the report. No project sources, logs, attachments or
complete conversation transcripts are automatically uploaded.

## CI-only automatic reporting

The skill-atlas-ci-feedback.yml workflow listens to failures in the
Skill Atlas integration test workflow on pushes to main only. It
uses an Issues-write scoped GitHub Actions token to report a short
constant description with the CI run URL, never test logs.

The --team-auto CLI option is allowed only when
SKILL_ATLAS_TEAM_AUTOREPORT=1, category ci-failure, and source
skill-atlas. Other uses require human confirmation.

External users do not opt into any remote telemetry merely by
installing the Skill. The workflow does not report failures from
third-party projects.
