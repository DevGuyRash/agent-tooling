# GoalSpec Workflows

## Author one concrete goal

1. Inventory capabilities.
2. Classify the raw request.
3. Compile `.goals/current.md` with the six launchability fields.
4. Validate and lock the contract hash.
5. Render a paste-ready Codex `/goal` objective.
6. Do not execute the goal during authoring unless the user explicitly launches `/goal`.

## Scan an area for candidate goals

1. Stay read-only.
2. Inspect only within the exploration budget.
3. Produce candidates with evidence, readiness, suggested verifier, scope, risk, and dependencies.
4. Update `.goals/GOALS.md` and `.goals/frontier.md` if requested.
5. Recommend at most one next ready goal.

## Audit a completed run

1. Compare final report/evidence/diffs against `.goals/current.md`.
2. Verify `.goals/current.sha256` still matches.
3. Treat missing evidence as inconclusive, not achieved.
4. Treat contract mutation as audit failure.
5. Record follow-up candidates without continuing the current goal.

## Select next goal

Prefer a ready goal with a strong verifier, low risk, no blockers, and clear scope. Do not select conditional, blocked, maintenance-loop, or too-broad goals unless the user explicitly asks to repair them first.
