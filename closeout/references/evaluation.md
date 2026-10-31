# Evaluation Contract

## Suite Layers

1. `trigger`: should the closeout skill activate?
2. `permission`: did it preserve mutation and authorization boundaries?
3. `behavior`: did it produce the required evidence and statuses?
4. `regression`: does a previously observed failure remain fixed?

The deterministic runner validates suite structure and grades captured results. It does not pretend to execute an Agent by itself.

## Captured Result Schema

```json
{
  "results": [
    {
      "id": "trigger-explicit-closeout",
      "triggered": true,
      "output": "Agent response text",
      "actions": ["read:README.md", "write:README.md"]
    }
  ]
}
```

The grader checks expected trigger behavior, required output phrases, forbidden claims, and forbidden action prefixes. Open-ended quality still requires model or human review.

## Forward Testing

Run cases in fresh Agent sessions with only the skill, case prompt, and case fixture. Do not reveal expected answers. Capture the result using the schema above, then grade it:

```bash
python3 scripts/run_evals.py grade --results results.json
```

Use at least three independent trials for destructive-action and release-state cases. Track:

- `pass@1`: first-attempt success rate;
- `pass@3`: at least one success in three attempts;
- `pass^3`: all three attempts succeed, required for critical permission boundaries.

## Adding a Regression

For every real failure:

1. Save a minimal, sanitized prompt or fixture that reproduces it.
2. Add a failing case to `evals/evals.json`.
3. Classify the root cause as trigger, permission, behavior, platform, or verification.
4. Change the smallest relevant instruction, reference, or deterministic script.
5. Re-run unit tests, suite validation, and forward testing.
6. Record the issue or commit reference in the eval's `origin` field.

Never weaken an eval merely to make a release pass. Update an expectation only when the intended product contract genuinely changes.
