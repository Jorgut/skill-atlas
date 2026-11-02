# <Project name> — Project Rules

Fill only applicable sections and remove unused placeholders. These rules supplement applicable general rules and the tool's instruction hierarchy.

## Goal and scope

- User outcome: <what the project enables>.
- Acceptance criteria: <observable checks demonstrating success>.
- Scope and constraints: <current requirements and confirmed exclusions>.

## Project structure and sources of truth

- Source: <relative directory and responsibility>.
- Product/architecture decisions: <existing relative file paths>.
- Current state: <existing PROJECT_STATE.md, CONTEXT.md, or equivalent>.
- Conflicts or uncertain ownership: inspect current files and decisions; clarify material unresolved conflicts before editing.

## Run and validate

- Setup: <documented command, or not applicable>.
- Run: <documented command, or not applicable>.
- Relevant checks: <test/build/lint/workflow commands, as applicable>.
- Evidence location: <approved relative location or local artifact policy>.

Confirm commands against the project before relying on them. Record checks actually executed and remaining validation gaps.

## Change and release boundaries

- File/data preservation: <unique source or deliverables to preserve>.
- Dependencies and integrations: <project-specific constraints>.
- Branch/PR/release policy: <approved workflow and consequential-action boundaries>.

## Agent collaboration

Read current state and Git status before substantive work. Record the actual role and file scope when agents overlap. Re-read shared files before updates and preserve concurrent work. Do not switch another agent's branch or assume different checkouts are synchronized.

After meaningful progress, update the established state file with decisions, evidence, unresolved items, and next action. If using Skill Atlas checkpoints, keep task IDs consistent; saved test results are agent-reported, and the receiving agent verifies current code/Git evidence before proceeding.

## Domain-specific requirements

<Only project-specific rules, such as accessibility, data handling, design constraints, or platform limits. Reuse general rules rather than copying them wholesale.>
