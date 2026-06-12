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

### G-002: Blocked child

- Status: blocked
- Depends on: G-001
- Missing decision: [the single owner decision that unblocks this child]
- Terminal state: [sketch it even while blocked — a child with no sketch is a stub, not a goal]
- Verifier: [sketch the check; "TBD" is not a verifier]

### G-003: Not-launchable child

- Status: not-launchable
- Reason: [no checkable terminal state / no verifier / unbounded scope]
- Needed to launch: [the missing spine field or decision]

## Selection Recommendation

Run G-001 first because [reason]. For an autonomous chain, after each child run
`campaign_status.py` and execute the child it names next. If no child is ready,
stop here and report what blocks the most promising child.
