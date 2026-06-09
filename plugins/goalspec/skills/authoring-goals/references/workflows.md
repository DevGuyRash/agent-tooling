# GoalSpec Workflows

## Author one concrete goal

1. Inventory capabilities.
2. Classify the raw request.
3. Record the verbatim request as provenance: `record_provenance.py --request <file|-> --update-contract`. This writes `.goals/provenance/<id>.md` (reference only, not execution scope) and inserts a `## Provenance` pointer (artifact path + request hash) into `current.md`. Never inline the raw request into `current.md` — the executor reads `current.md` as source of truth and would re-attract the sprawl.
4. Compile `.goals/current.md` with the six launchability fields.
5. Validate and lock the contract hash.
6. Render a paste-ready Codex `/goal` objective (render excludes provenance).
7. Do not execute the goal during authoring unless the user explicitly launches `/goal`.

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

## Decompose a large request

For a high/extreme-risk or broad/multi-objective/activity-shaped request:

1. Score the raw request (`score_goal_risk.py`) and name the risk level and why.
2. Do not compile it into one contract. Write a non-executable campaign from the campaign template (`.goals/campaign-*.md`).
3. Split it into finite child candidates, each with a readiness status: `ready | conditional | blocked | not-launchable`.
4. Compile at most one ready child into `.goals/current.md`; validate and lock it. The campaign parent is never executed, never rendered, and gets no contract hash.
5. If no child is ready, stop at the campaign/backlog and report the missing fields or decisions blocking the most promising child.
6. Record the remaining children as candidates/backlog, not as implicit scope of the launched child.

## Greenfield / from spec

When there is no existing code to scan:

1. Skip the repo scan; still inventory the languages, tooling, and test runners that will exist.
2. Author from the prompt or spec. If a spec/PRD/design doc exists, scan that document as the discovery surface.
3. Make the first goal small and verifiable: a minimal artifact plus a smoke test and run instructions, with a verifier that actually executes.
4. Keep the full spine — greenfield does not waive terminal state, verifier, budget, scope, give-up, or completeness.

## Select next goal

Prefer a ready goal with a strong verifier, low risk, no blockers, and clear scope. Do not select conditional, blocked, maintenance-loop, or too-broad goals unless the user explicitly asks to repair them first.
