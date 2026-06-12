# Campaign: Replace With Name

> **Never a single goal.** A campaign parent is never compiled into one
> `/goal` and has no single-goal contract hash. Two supported paths:
> (1) human-stepped — compile **at most one ready child** into
> `.goals/current.md`, validate, lock, run; or (2) autonomous chain — give
> every ready child a full locked contract at `.goals/children/G-00N/current.md`,
> lock the campaign with `validate_campaign.py --write-hash`, then render the
> chain with `render_goal.py --campaign`. If no child is ready, stop here and
> report what blocks the most promising child.

## Intent

[The parent aspiration anchored in the user's own words. Open with the Intent
Inventory — each distinct ask as a short verbatim quote:]

1. "[verbatim quote]"
2. "[verbatim quote — a second intent in the same request is the one that
   usually gets dropped]"

## Completeness Dimensions

- [dimension]

## Chain Budget

- Max children attempted: [N] — the chain stops once N distinct children have attempt evidence, regardless of remaining children. (Retries of one child count once; the wall clock bounds retry grinding.)

## Chain Failure Policy

- halt-on-failure

[Exactly one of: halt-on-failure | skip-dependents-and-continue]

## Coverage

[Map each Intent Inventory item — not a paraphrase — to a child id, or mark it
`deferred: <reason>`. Anything the request asks for that appears nowhere here is
a coverage gap.]

- Inventory 1 "[quote]" -> G-001
- Inventory 2 "[quote]" -> deferred: [reason]

## Goal Graph

### G-001: First launchable child

- Status: ready
- Depends on: none
- Blocks: [ids]
- Contract: .goals/children/G-001/current.md
- Terminal state: [one sentence: the checkable state of the workspace when this child is done]
- Verifier: [runnable command / metric / named gate that checks it]

### G-002: Conditional child (materialized, unlocked)

- Status: conditional
- Depends on: G-001
- Contract: .goals/children/G-002/current.md
- Missing decision: Owner decision required: [the single owner decision that unblocks this child]
- Terminal state: [one sentence; the full contract carries the rest]
- Verifier: [sketch the check; "TBD" is not a verifier]

[Materialize everything, lock the horizon: every named child gets a FULL
contract written with its sources open — conditional and blocked children
included, just unlocked, with the owner decision in their give-up conditions.
At selection the tail contract is re-validated against current reality,
updated, then locked. A manifest sketch is a skeleton, never an end state.]

### G-003: Not-launchable child

- Status: not-launchable
- Reason: [no checkable terminal state / no verifier / unbounded scope]
- Needed to launch: [the missing spine field or decision]

## Selection Recommendation

Execution order is derived, never asserted: `campaign_status.py` names the next
unblocked child each time, so the handoff stays correct in every new thread.
[State why the dependency graph starts where it does — e.g. nothing blocks
G-001 — not "run G-001 first" as an instruction.] If no child is ready, stop
here and report what blocks the most promising child.

## Decomposition Review

[Closed by the adversarial review: one verdict per child, each finding applied
or explicitly declined, and the anchor from validate_campaign.py output.]

- G-001: [confirmed | weak | theater] — [one line of evidence]
- [finding] — APPLIED: [what changed] / DECLINED: [why]

Anchor: [copy the `review anchor:` value from validate_campaign.py output]
