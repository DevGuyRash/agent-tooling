# Outer Loop Policy

GoalSpec improves on persistent Ralph-style loops by splitting the system into two loops:

- Outer loop: open-world discovery and goal formation.
- Inner loop: closed-world execution of one frozen contract.

Default: the outer loop is human-stepped.

Lifecycle:

1. Inventory capabilities.
2. Scan requested context within an exploration budget.
3. Extract candidate goals with evidence.
4. Lint for launchability.
5. Select one ready goal, or report why none is launchable.
6. Compile `.goals/current.md`.
7. Validate and lock the contract hash.
8. Render the `/goal` objective.
9. Run `/goal` against the single contract.
10. Capture verifier evidence and final report.
11. Audit against `current.md` and hash lock.
12. Close status in `GOALS.md` and `graph.json`.
13. Stop. Do not launch the next goal without a new user instruction unless an explicit outer-loop budget exists.

Open-world done is not "there is no more work." It is "no additional launchable candidate was found within the stated frontier and budget."

## Autonomous chain variant

The campaign chain is the sanctioned autonomous outer loop: the loop's budget and
stop condition live in the frozen manifest (`## Chain Budget`, `## Chain Failure
Policy`), so autonomy never means unbounded.

1. Decompose into a campaign; give every ready child a full contract at
   `.goals/children/G-00N/current.md`.
2. Validate and lock each child, then lock the campaign aggregate
   (`validate_campaign.py --write-hash`).
3. Render ONE chain `/goal` with `render_goal.py --campaign` (refuses anything unlocked).
4. The executor loops: `campaign_status.py` names the next child → execute that
   child's frozen contract → verifiers → report → repeat, until the status helper
   reports `chain_should_stop`.
5. Close with `audit_campaign.py` (recomputes everything from evidence), then update
   ledger/graph per child. Mid-run discoveries surface as harvested follow-up
   candidates — the input to the next campaign, never an extension of this one.

The child set is frozen at launch; status checkmarks are a derived view of verifier
evidence, never something the executor asserts.
