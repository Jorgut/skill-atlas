# Project Profiles

Use profiles to select relevant evidence, not to impose a new toolchain. Prefer commands already declared by the project.

| Profile | Common indicators | Minimum verification evidence |
| --- | --- | --- |
| Web application | `package.json`, routes/pages, frontend source | repository build/test, route inventory, browser check when available, deployment/live check only in release mode |
| API or service | API routes, OpenAPI, server manifest, migrations | tests, schema/route comparison, auth boundary review, migration state, health/API response when available |
| Library or package | package metadata, exported modules, publish config | tests, package version, public API examples, package/build artifact |
| Desktop application | Xcode, SwiftPM, Electron, Tauri, native manifests | build, signing/permissions when relevant, launch smoke test, platform-specific behavior |
| Agent Skill | `SKILL.md`, commands, evals, installer | Skill validator, trigger/non-trigger evals, permission evals, strict security scan, installer idempotency, platform load check |
| Documentation | Markdown-first repository, docs generator | link/index check, command and version verification, source citation review |

Multiple profiles may apply. Choose one primary profile and add only the complementary gates needed for the actual artifact.

If no profile matches, use the project's own rules, manifests, and existing CI commands. Mark unavailable runtime or external evidence `pending` rather than guessing.
