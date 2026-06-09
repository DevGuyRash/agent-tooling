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

The verifier result is the oracle, not the report prose. `run_verifiers.py --run`
writes a machine-readable `goalspec.verifier.v1` result file
(`.goals/evidence/verifiers/result.json`) recording each verifier's
`exit_code`/`passed` and an `overall_passed`. `audit_goal.py` reads that file as
the sole upgrade path to `achieved`.

1. Run the contract's verifiers and produce the result file:
   `run_verifiers.py .goals/current.md --run`.
2. Audit against the frozen contract: `audit_goal.py .goals/current.md --report <report> --evidence-dir .goals/evidence`.
3. The audit returns exactly one verdict:
   - `achieved` — verifier `overall_passed` is true AND required report sections are present AND `.goals/current.sha256` matches AND no scope violation.
   - `not achieved` — the verifier result did not pass.
   - `inconclusive` — no verifier result file for an executable verifier (run the verifiers), or required sections/evidence are missing. Report headings and a non-empty evidence dir are necessary but never sufficient.
   - `blocked` / `scope violation` — declared in the report's `## Result` line; these downgrade the verdict but can never upgrade it to achieved.
   - `contract mutated` — `current.md` no longer matches its hash lock.
4. For a human/artifact/MCP verifier there is no machine result; the report
   attestation is the recorded oracle, so name that gate explicitly in the
   contract's `## Verifier` section or audit stays inconclusive.
5. Record follow-up candidates without continuing the current goal.

## Select next goal

Prefer a ready goal with a strong verifier, low risk, no blockers, and clear scope. Do not select conditional, blocked, maintenance-loop, or too-broad goals unless the user explicitly asks to repair them first.
