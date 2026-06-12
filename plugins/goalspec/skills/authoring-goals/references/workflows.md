# GoalSpec Workflows

## Author one concrete goal

1. Inventory capabilities.
2. Classify the raw request.
3. Record the verbatim request as provenance: `record_provenance.py --request <file|-> --update-contract`. This writes `.goals/provenance/<id>.md` (reference only, not execution scope) and inserts a `## Provenance` pointer (artifact path + request hash) into `current.md`. Never inline the raw request into `current.md` — the executor reads `current.md` as source of truth and would re-attract the sprawl.
4. Compile `.goals/current.md` with the six launchability fields.
5. Validate and lock the contract hash.
6. Render a paste-ready Codex `/goal` objective, preferably with `--pointer` (render excludes provenance). End with the launch line verbatim — it is the deliverable; do not create or edit a host thread goal during authoring.
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
   `run_verifiers.py .goals/current.md --run`. Declared `Pinned:` companions are
   checked first; a missing or mutated companion fails the run loudly and no
   commands execute against it.
2. Audit against the frozen contract: `audit_goal.py .goals/current.md --report <report> --evidence-dir .goals/evidence`. The audit re-checks the pins itself.
3. The audit returns exactly one verdict:
   - `achieved` — verifier `overall_passed` is true AND required report sections are present AND `.goals/current.sha256` matches AND no scope violation.
   - `not achieved` — the verifier result did not pass, or a pinned companion is missing/mutated.
   - `inconclusive` — no verifier result file for an executable verifier (run the verifiers), or required sections/evidence are missing. Report headings and a non-empty evidence dir are necessary but never sufficient.
   - `blocked` / `scope violation` — declared in the report's `## Result` line; these downgrade the verdict but can never upgrade it to achieved.
   - `contract mutated` — `current.md` no longer matches its hash lock.
4. For a human/artifact/MCP verifier there is no machine result; the report
   attestation is the recorded oracle, so name that gate explicitly in the
   contract's `## Verifier` section or audit stays inconclusive.
5. Record follow-up candidates without continuing the current goal.

## Decompose a large request

For a high/extreme-risk or broad/multi-objective/activity-shaped request. The outcome: a campaign grounded in the user's words, each child adding execution information over its sources, the execution horizon locked, the tail sketched.

1. **Intent Inventory.** Re-read the verbatim request and write the distinct intents as short verbatim quotes; record the request with `record_provenance.py --request <file> --contract .goals/campaign-<slug>.md --update-contract` (the manifest is what the request compiled into). Score it (`score_goal_risk.py`) and state the risk level and your routing decision. Candidate extraction surfaces the sources' own decision registers as `needs human decision` items — route each to a conditional child or an `Owner decision required:` line.
2. **Skeleton.** Write the campaign manifest from the template (`.goals/campaign-*.md`): `## Coverage` maps every inventory item to a child id or `deferred: <reason>`; children carry readiness statuses (`ready | conditional | blocked | not-launchable`), declared dependencies, and at least a sketched Terminal state and Verifier each. When the source defines its own work units (epics, tickets), the near wave decomposes to that grain rather than wrapping milestones.
3. **Ground each child.** Each child should read as if its sources were open while it was written: bound to the specific source sections it implements, oracle derived from its own terminal clauses. One good pattern — not the required one — is a fresh scoped pass per child, holding only the verbatim ask, that child's source sections, the contract template, and neighbor interfaces, so later children are read from sources instead of pattern-completed from earlier siblings (see the child-author note in `references/custom-agents.md`). Pin shared companion artifacts the verifiers depend on (`- Pinned: <path> sha256 <hash>`). Give a child an executable oracle when the chain should advance through it unattended; a gate-only child is a pause point.
4. **Adversarial review.** After `validate_campaign.py` passes, copy the `review anchor` from its output, then spawn the `decomposition-reviewer` agent (or run a fresh self-review against rubric check 10). Apply or explicitly decline each finding in the manifest's `## Decomposition Review` section, closing with one verdict per child and the `Anchor:` line. If applying findings changed the manifest, re-validate (new anchor), confirm the verdicts still describe the edited graph, and update the Anchor line — a stale anchor warns on every later validation. A review that only records findings has not closed.
5. **Lock the execution horizon.** Materialize and lock full contracts for the children that can execute next (`validate_goal.py <path> --write-hash`); leave the tail sketched-conditional — it materializes at selection, when its contract and pins can reflect reality. Sync the mirror (`graph_goal.py --sync-campaign <manifest>`). For an autonomous chain, every ready child is in the horizon: lock them all, then the aggregate (`validate_campaign.py <manifest> --write-hash`).
6. **Render and hand off.** Human-stepped: compile at most one ready child into `.goals/current.md`, validate, lock, render with `--pointer`. Autonomous: `render_goal.py --campaign <manifest> --pointer` (this also freezes the chain runtime into `.goals/bin/`). End your final message with the launch line verbatim — that line is the entire handoff; do not create or edit a host thread goal during authoring. If no child is ready, stop at the campaign and report the decision blocking the most promising child.

Remaining children are candidates/backlog, never implicit scope of the launched child. Before handing off, re-read the original request once more: anything it explicitly asks that no child covers gets covered or recorded as deferred with a reason.

## Run a campaign autonomously

The chain executes every ready child of a frozen campaign in one `/goal`. The plan is frozen, evidence is the truth, checkmarks are a derived view. The rendered mission is durable: pasted into any new thread it derives the next pending child from state, skips what is done, pauses at gates, and stops when complete.

1. Author each ready child as a full contract at `.goals/children/G-00N/current.md` (six-field spine, same as any goal); validate and lock each one (`validate_goal.py <path> --write-hash`).
2. In the manifest, set `## Chain Budget` (numeric max child attempts) and `## Chain Failure Policy` (`halt-on-failure` or `skip-dependents-and-continue`); give each ready child `- Contract:` and `- Depends on:` lines. The hash-locked manifest is the dependency truth; `graph.json` is only a mirror.
3. Lock the campaign: `validate_campaign.py .goals/campaign-<slug>.md --write-hash` (writes the aggregate `.goals/campaign.sha256`; any manifest edit or child swap breaks it).
4. Render ONE chain `/goal`: `render_goal.py --campaign .goals/campaign-<slug>.md --pointer`. It refuses unless the campaign lock and every ready child lock match — no unlocked override — and freezes the chain runtime into `.goals/bin/` (workspace-local copies the chain invokes, hashes in `MANIFEST.sha256`, overwritten on re-render) so the mission survives plugin upgrades.
5. Execute. Unattended: `launch_goal.py <workspace> --campaign .goals/campaign-<slug>.md` (external wall-clock ceiling; the wrapper re-runs verifiers per attempted child at close, then audits). Interactive: paste the rendered `/goal`; afterwards re-run `run_verifiers.py` per child yourself before auditing.
6. During the run the executor only writes `.goals/evidence/` and `.goals/reports/`; after each child it follows `campaign_status.py`'s `next_child` and stops on `chain_should_stop`. If the status helper itself fails, it stops and reports blocked. An attestation-only child (no executable verifier command) is a pause point: the executor does the work, writes the report, and the chain stops until the owner records the gate outcome (e.g. `Human gate: approved by owner`) in that child's report and relaunches the same line — the audit, not the executor's word, advances it.
7. Audit: `audit_campaign.py .goals/campaign-<slug>.md` — verdicts `campaign achieved | partial: n/m | not achieved | campaign mutated`; skipped children are labeled by the failed dependency; a mutated `.goals/bin/` runtime warns (wrapper-side re-runs stay authoritative). Harvested `follow_up_candidates` are the next campaign's input.
8. Close: set `GOALSPEC_ALLOW_CONTRACT_WRITE=1` for the close commands (the armed scope guard otherwise denies them all, including removing the lock itself), then archive/remove `.goals/campaign.sha256` and run `graph_goal.py --status` / `update_ledger.py` per child.

## Greenfield / from spec

When there is no existing code to scan:

1. Skip the repo scan; still inventory the languages, tooling, and test runners that will exist.
2. Author from the prompt or spec. If a spec/PRD/design doc exists, scan that document as the discovery surface.
3. Make the first goal small and verifiable: a minimal artifact plus a smoke test and run instructions, with a verifier that actually executes.
4. Keep the full spine — greenfield does not waive terminal state, verifier, budget, scope, give-up, or completeness.

## Select next goal

Prefer a ready goal with a strong verifier, low risk, no blockers, and clear scope. Do not select conditional, blocked, maintenance-loop, or too-broad goals unless the user explicitly asks to repair them first. Selection is the moment the rolling wave advances: a conditional child whose decision has landed gets materialized into a full contract, pinned, and locked now — against the workspace as it exists today.
