# Examples

## Clear task

Input:

```text
Fix the checkout total rounding bug.
```

Output: one `.goals/current.md` with terminal state, verifier, scope, budget, give-up, completeness, and paste-ready `/goal`.

## Vague aspiration

Input:

```text
Make onboarding better.
```

Output: not launchable as written. Suggested finite replacements:

1. Fix all current onboarding form validation errors reproduced by tests.
2. Update onboarding copy to match glossary G and pass human review checklist R.
3. Reduce onboarding completion time under benchmark B after identifying the top three measured friction points.

## Existing GOALS.md

Input: a registry with mixed vague and ready items.

Output: lint report with statuses: ready, conditional, blocked, maintenance-loop, too broad, duplicate.

## Existing run report

Input: `.goals/current.md` and `.goals/reports/latest.md`.

Output: audit result based on evidence, not confidence.

## Greenfield / from spec

Input:

```text
Build a CLI that converts CSV to JSON. No code yet; here is a one-paragraph spec.
```

Output: skip the repo scan, inventory the language/test runner, and compile one small `.goals/current.md`: a minimal `csv2json` plus a smoke test, terminal state "the smoke test command exits 0 on the sample input", verifier = that command, bounded budget. Not "the CLI is done".

## Worked decomposition: the artifacts, as files

The verbatim request — three intents, two of them easy to lose:

```text
Ship the guest checkout flow in docs/checkout-prd.md — the PRD is final.
Also our payment webhook tests are flaky and the team has stopped trusting
them; make them reliable. Keep it simple for now — we don't need saved
cards or wallets yet.
```

Nuance that must survive: "the PRD is final" is a *constraint* (the docs are
not editable to make execution easier — it becomes a scope fence AND a
verifier clause); "the team has stopped trusting them" is the *why* behind
intent 2 (reliability the team believes, not a lucky green run); "for now …
yet" is a *deferral signal* (saved cards/wallets belong on the far map, not
in the wave, and not silently dropped).

What follows are the actual artifacts a good authoring pass produces, shown
as complete files. Every child is materialized as a full contract — depth is
always maximal; only locking is horizon-scoped (G-001 and G-004 locked,
G-002/G-003 written but unlocked until selected).

`.goals/campaign-guest-checkout.md:`

````markdown
# Campaign: Guest Checkout Ships And Webhook Tests Become Trustworthy

## Provenance

- Artifact: .goals/provenance/campaign-guest-checkout.md
- Request hash: 8c41f2a90be6d3571f04c8a2e95d617b3a2c4f08d9e1b6a57c30d2f4e8a91b65
- Reference only; not execution scope. The verbatim original request lives in
  the artifact and must not be executed or re-derived. Execute only the frozen
  child contract selected by this manifest.

## Intent

Intent Inventory:

1. "Ship the guest checkout flow in docs/checkout-prd.md — the PRD is final."
2. "our payment webhook tests are flaky and the team has stopped trusting
   them; make them reliable"
3. "Keep it simple for now — we don't need saved cards or wallets yet."

Inventory 3 is a deferral nuance, not a goal: it fences the wave (no payment-
method persistence anywhere in G-001 through G-004) and routes saved cards /
wallets to the far map in GOALS.md, gated on guest checkout reaching GA.

## Completeness Dimensions

- Guest checkout behavior matches PRD sections 2 through 6 without weakening
  the PRD to make execution easier (it is final).
- Webhook test reliability is demonstrated by repetition the team can see,
  not asserted from one green run.
- The simplicity fence holds: no saved-card or wallet surface ships in this
  campaign.
- Every child carries its own oracle; human gates appear only where the PRD
  requires owner sign-off.

## Chain Budget

- Max children attempted: 4

## Chain Failure Policy

- halt-on-failure

## Coverage

- Inventory 1 "Ship the guest checkout flow" -> G-001, G-002, G-003
- Inventory 1 nuance "the PRD is final" -> every child's scope fence + the
  `git diff --exit-code -- docs/checkout-prd.md` verifier clause
- Inventory 2 "make them reliable" (webhook tests) -> G-004
- Inventory 3 "for now … yet" (saved cards / wallets) -> deferred: GOALS.md
  far map, opens when guest checkout reaches GA per PRD §7 metrics

## Goal Graph

### G-001: Guest identity and address capture (PRD §2, §4)

- Status: ready
- Risk: medium
- Depends on: none
- Blocks: G-002
- Contract: .goals/children/G-001/current.md
- Terminal state: a guest completes identity and address entry per PRD §2/§4
  and `pytest tests/checkout/test_guest_identity.py -q` exits 0.
- Verifier: that command, plus `git diff --exit-code -- docs/checkout-prd.md`.

### G-002: Guest payment step (PRD §5)

- Status: conditional
- Risk: high
- Depends on: G-001
- Blocks: G-003
- Contract: .goals/children/G-002/current.md
- Missing decision: Owner decision required: which PSP sandbox account and
  test-card set the payment step develops against.
- Terminal state: a guest completes a sandbox payment per PRD §5 with no
  payment-method persistence.
- Verifier: `pytest tests/checkout/test_guest_payment.py -q` plus the PRD
  no-drift check.

### G-003: Order confirmation for guests (PRD §6)

- Status: conditional
- Risk: medium
- Depends on: G-002
- Blocks: none
- Contract: .goals/children/G-003/current.md
- Missing decision: Owner decision required: transactional-email provider for
  the confirmation message (PRD §6 names the content, not the carrier).
- Terminal state: confirmation page and email match the PRD §6 content table.
- Verifier: `pytest tests/checkout/test_guest_confirmation.py -q` plus the PRD
  no-drift check.

### G-004: The payment webhook suite is reliable and trusted

- Status: ready
- Risk: medium
- Depends on: none
- Blocks: none
- Contract: .goals/children/G-004/current.md
- Terminal state: `tests/webhooks` passes 20 consecutive runs with zero skips
  and the flake sources are fixed, not retried away.
- Verifier: a 20-iteration loop over `pytest tests/webhooks -q` that exits
  non-zero on the first failure or skipped test.

## Selection Recommendation

Execution order is derived, never asserted: `campaign_status.py` names the
next unblocked child each time, so the handoff stays correct in every new
thread. Nothing blocks G-001 or G-004, so the chain interleaves them first;
G-002/G-003 promote to ready when their owner decisions land (re-validate,
update, lock, re-lock the aggregate). If no child is ready, stop here and
report what blocks the most promising child.

## Decomposition Review

Reviewer: decomposition-reviewer (refute bias).

- G-001: confirmed — terminal clauses restate PRD §2/§4 requirements; tasks
  enumerate table 4.1; oracle is its own.
- G-002: confirmed — fully materialized though unlocked; the PSP decision
  lives in its give-up conditions, not as a reason to stay shallow.
- G-003: confirmed — section-bound (§6 content table) with its own oracle.
- G-004: confirmed — verifier strengthened by finding 1; the "team has
  stopped trusting them" nuance is carried as a repetition oracle.

1. APPLIED — G-004's verifier was a single `pytest tests/webhooks -q` run: it
   could pass on a lucky run, or by skipping the flaky tests, without making
   them reliable. Strengthened to 20 consecutive runs with zero skips.
2. APPLIED — G-003 cited only "the PRD" while its siblings cited sections;
   rebound to PRD §6 with an oracle of its own.
3. DECLINED — reviewer suggested locking G-002/G-003 now. Declined: their
   contracts are fully written; locking waits for the PSP and email-provider
   decisions so pins and anchors reflect lock-time reality.

Anchor: 0a9f44c2e7b15d8a30f6921b4cd07e5f8a36d1c09b274e6f5a801d92c3e4f7ab
````

`.goals/children/G-001/current.md:` (the flagship — ready, locked)

````markdown
# Goal Contract: G-001 Guest Identity And Address Capture

## Status

- State: active
- Created: 2026-06-12
- Source: user prompt + docs/checkout-prd.md
- Contract hash: pending
- Blocks: G-002
- Blocked by: none

## Provenance

- Artifact: .goals/provenance/campaign-guest-checkout.md
- Request hash: 8c41f2a90be6d3571f04c8a2e95d617b3a2c4f08d9e1b6a57c30d2f4e8a91b65
- Reference only; not execution scope. Execute only this frozen contract.

## Objective

A guest can complete the identity and address steps of checkout exactly as
PRD §2 and §4 specify, verified by the suite this goal creates, without any
account creation and without the PRD changing to fit the implementation.

## Intent

Inventory 1: "Ship the guest checkout flow in docs/checkout-prd.md — the PRD
is final." This child delivers the identity and address steps of that flow.
The "PRD is final" nuance binds here twice: the docs are out of scope to
edit, and the verifier fails if they drift. Inventory 3's simplicity fence
also applies: no identity persistence beyond the checkout session.

## Context

Source anchors (line-level — this goal executes now; re-verify during your
discovery pass before acting, the tree may have drifted since authoring):

- docs/checkout-prd.md:41 §2 "Guest identity" — email-only, no account
  creation, no marketing opt-in by default.
- docs/checkout-prd.md:88 §4 "Address capture" — single page; validation
  rules in table 4.1 (required fields, postal-code formats, country list).
- src/checkout/ holds the existing signed-in flow this guest path must not
  regress.

## Available Capabilities

- Skills: authoring-goals
- Plugins: goalspec
- MCP servers: none discovered
- Hooks: GoalSpec scope/evidence/stop hooks
- Subagents/custom agents: none required
- Project commands: `pytest -q` (suite), `npm run lint` (static checks)

## Completeness Dimensions

This goal must cover:

- Functional behavior: email-only identity and single-page address entry per
  PRD §2/§4.
- Verification: a guest-identity suite exists and passes; the PRD is
  demonstrably unchanged.
- Regression safety: the signed-in checkout flow keeps passing its suite.
- Simplicity fence: nothing persists payment or identity data beyond the
  checkout session.

## Terminal State

This goal is complete when:

- A guest provides an email only (§2): no password field, no account record,
  no default marketing opt-in.
- Address entry is a single page enforcing every rule in table 4.1 (§4).
- `pytest tests/checkout/test_guest_identity.py -q` exits 0.
- `pytest tests/checkout -q` (the existing signed-in suite) still exits 0.
- `git diff --exit-code -- docs/checkout-prd.md` exits 0 — the PRD is final.

## Tasks

- [ ] Guest identity step matches PRD §2
  - [ ] Email-only entry: no password field renders on the guest path
    - [ ] Email format errors surface inline, per the §2 copy table
    - [ ] No account row is written for a guest session
  - [ ] Marketing opt-in is absent by default (§2 forbids pre-checked boxes)
- [ ] Address capture matches PRD §4
  - [ ] All table 4.1 required fields enforce presence
    - [ ] Postal-code format validates per country (table 4.1 formats)
    - [ ] The country list matches table 4.1 exactly
  - [ ] Identity and address render as one page (§4 "single page" clause)
- [ ] The guest-identity suite proves the above
  - [ ] tests/checkout/test_guest_identity.py covers each §2/§4 rule
  - [ ] The signed-in checkout suite still passes unchanged
- [ ] Nothing persists beyond the checkout session (simplicity fence)

## Verifier

Completion must be verified by:

- `pytest tests/checkout/test_guest_identity.py -q`
- `pytest tests/checkout -q`
- `git diff --exit-code -- docs/checkout-prd.md`
- Pinned: scripts/verify_checkout_flow.py sha256 0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9

## Scope

In scope:

- src/checkout/ guest-path modules, their tests, and fixtures.
- tests/checkout/test_guest_identity.py (new).

Out of scope:

- Editing docs/checkout-prd.md for any reason — the PRD is final.
- Payment, confirmation, saved cards, wallets, or any payment-method
  persistence ("for now … yet" defers them).
- The signed-in checkout flow beyond keeping its tests green.

## Budget

- Max implementation iterations: 4
- Max changed files: 12
- Max new dependencies: 0
- Max exploration files/directories: 40
- Stop when the budget is exhausted even if incomplete.

## Give-Up Conditions

Stop and report blocked/incomplete if:

- Table 4.1 conflicts with existing address storage in a way only a product
  decision can resolve.
- Satisfying §2/§4 requires editing the PRD or the signed-in flow's behavior.
- The verifier suite cannot run in the available environment.

## Priority Order

1. PRD fidelity
2. Regression safety
3. Test completeness
4. Minimal scope

## Follow-Up Policy

Discovered adjacent work must be recorded as candidate goals, not performed,
unless required for the terminal state. Begin with open-world discovery:
re-verify the anchors above against the current tree. Execute closed-world:
any approach satisfying this contract within scope and budget is valid.

## Evidence Required

Final report must include:

- Files changed
- Commands run
- Raw pass/fail results or artifact paths
- Budget used
- Remaining risks
- Follow-up candidates
````

`.goals/children/G-002/current.md:` (conditional — fully materialized, UNLOCKED; abridged here only where it repeats G-001's shape verbatim)

````markdown
# Goal Contract: G-002 Guest Payment Step

## Status

- State: candidate
- Created: 2026-06-12
- Source: user prompt + docs/checkout-prd.md
- Contract hash: pending — unlocked by design; this contract locks at
  selection, after re-validation against the tree as it exists then
- Blocks: G-003
- Blocked by: G-001

## Provenance

- Artifact: .goals/provenance/campaign-guest-checkout.md
- Request hash: 8c41f2a90be6d3571f04c8a2e95d617b3a2c4f08d9e1b6a57c30d2f4e8a91b65
- Reference only; not execution scope. Execute only this frozen contract.

## Objective

A guest completes a sandbox payment exactly as PRD §5 specifies, with no
payment-method persistence of any kind.

## Intent

Inventory 1: "Ship the guest checkout flow…" — the payment step. Inventory
3's fence is hardest here: "we don't need saved cards or wallets yet" means
no tokenization-for-reuse, no wallet buttons, no "remember this card".

## Context

Section/outcome anchors (this goal runs later — files will have changed, so
no line numbers; re-verify these sections during your discovery pass):

- docs/checkout-prd.md §5 "Payment" — accepted methods, error taxonomy,
  3DS handling expectations.
- The PSP integration G-001's session shape feeds into (interface, not
  implementation, is the dependency).

## Available Capabilities

- Skills: authoring-goals
- Plugins: goalspec
- MCP servers: none discovered
- Hooks: GoalSpec scope/evidence/stop hooks
- Subagents/custom agents: none required
- Project commands: `pytest -q`

## Completeness Dimensions

This goal must cover:

- Functional behavior: sandbox payment per PRD §5, including its error
  taxonomy.
- Verification: a guest-payment suite exists and passes; the PRD is
  demonstrably unchanged.
- Simplicity fence: no payment-method persistence ships.

## Terminal State

This goal is complete when:

- A guest completes a sandbox payment per PRD §5 for each accepted method.
- Every §5 error class renders its specified message and recovery path.
- No card, token, or wallet handle outlives the checkout session.
- `pytest tests/checkout/test_guest_payment.py -q` exits 0.
- `git diff --exit-code -- docs/checkout-prd.md` exits 0.

## Tasks

- [ ] Sandbox payment succeeds per PRD §5
  - [ ] Each accepted method completes against the chosen PSP sandbox
  - [ ] 3DS challenge flow completes where §5 requires it
- [ ] The §5 error taxonomy is fully represented
  - [ ] Declines render the §5 message and recovery path
  - [ ] Timeouts and PSP errors fail safe without double-charging
- [ ] The simplicity fence holds
  - [ ] No persistence of card data, tokens, or wallet handles
- [ ] tests/checkout/test_guest_payment.py proves the above

## Verifier

Completion must be verified by:

- `pytest tests/checkout/test_guest_payment.py -q`
- `git diff --exit-code -- docs/checkout-prd.md`

## Scope

In scope:

- src/checkout/payment guest path and its tests.

Out of scope:

- Editing docs/checkout-prd.md — the PRD is final.
- Saved cards, wallets, tokenization-for-reuse ("for now … yet").
- The PSP's signed-in configuration.

## Budget

- Max implementation iterations: 4
- Max changed files: 14
- Max new dependencies: 1
- Max exploration files/directories: 40
- Stop when the budget is exhausted even if incomplete.

## Give-Up Conditions

Stop and report blocked/incomplete if:

- Owner decision required: the PSP sandbox account and test-card set are not
  yet chosen — this is the decision that unlocks the goal.
- §5 requires a capability the chosen PSP sandbox cannot exercise.
- Satisfying §5 would require persisting payment methods.

## Priority Order

1. PRD fidelity
2. Payment safety (no double-charge, fail safe)
3. Simplicity fence
4. Minimal scope

## Follow-Up Policy

Discovered adjacent work must be recorded as candidate goals, not performed,
unless required for the terminal state.

## Evidence Required

Final report must include:

- Files changed
- Commands run
- Raw pass/fail results or artifact paths
- Budget used
- Remaining risks
- Follow-up candidates
````

`GOALS.md:` (the registry — wave plus the far map; nothing the request named is invisible)

````markdown
# GOALS.md

This file is a registry, not an execution target. Do not run Codex `/goal`
against this entire file. Execute only a locked contract or rendered campaign
pointer.

## Active

### C-001: Guest checkout + webhook reliability campaign

- Status: ready
- Type: campaign
- Campaign: .goals/campaign-guest-checkout.md
- Rendered launch pointer: .goals/rendered-campaign.md

## Ready

- G-001, G-004 (locked horizon — full contracts under .goals/children/)

## Conditional

- G-002 (awaits the PSP sandbox decision), G-003 (awaits the email-provider
  decision) — both fully materialized at .goals/children/, unlocked; they
  re-validate and lock at selection.

## Deferred (far map)

### Saved payment methods and wallets

- Status: deferred
- Opens when: guest checkout reaches GA per PRD §7 metrics
- Source: the request's own nuance — "we don't need saved cards or wallets
  yet" — and PRD §8 (phase 2 sketch)

## Blocked / Not Launchable

_None recorded._

## Follow-Up Candidates

_None recorded during authoring._
````

`.goals/focus.md:` (the executor's first read — regenerated by focus.py; shown mid-G-001 with one outcome already marked)

````markdown
# Focus (derived view — never authoritative)

> Regenerated by focus.py. The locked contract is the source of truth and
> the verifier is the oracle; task marks are a progress cursor, never
> achievement. Do not edit this file by hand — move the cursor with the
> commands at the bottom.

- Goal: G-001 — Guest identity and address capture (PRD §2, §4)
- Contract: .goals/children/G-001/current.md (sha256 24bb29d01c6e41d3… — locked)
- Campaign: .goals/campaign-guest-checkout.md — 0/2 goals achieved (pending audit) in this wave

## Objective

A guest can complete the identity and address steps of checkout exactly as
PRD §2 and §4 specify, verified by the suite this goal creates, without any
account creation and without the PRD changing to fit the implementation.

## Tasks (declarative outcomes — cursor state)

- [ ] 1 Guest identity step matches PRD §2
  - [x] 1.1 Email-only entry: no password field renders on the guest path
    - [ ] 1.1.1 Email format errors surface inline, per the §2 copy table
    - [ ] 1.1.2 No account row is written for a guest session
  - [ ] 1.2 Marketing opt-in is absent by default (§2 forbids pre-checked boxes)
- [ ] 2 Address capture matches PRD §4
  - [ ] 2.1 All table 4.1 required fields enforce presence
- [ ] 3 The guest-identity suite proves the above
- [ ] 4 Nothing persists beyond the checkout session (simplicity fence)

11 of 12 outcomes open.

## Working this goal

Open-world discovery first: re-verify the workspace's current state against the
contract's assumptions and anchors — context may have drifted since authoring.
Closed-world execution: any approach satisfying the contract within scope and
budget is valid; discoveries beyond scope become Follow-Up Candidates in the
report, never new work.

- Mark an outcome satisfied: `python3 .goals/bin/focus.py done <id>` (e.g. `done 1.2 1.3`; `undo <id>` reverses; marking outcomes is bookkeeping, not achievement)
- When every outcome is satisfied: run `python3 .goals/bin/run_verifiers.py .goals/children/G-001/current.md --run --evidence-dir .goals/evidence/children/G-001/verifiers`, write the report at .goals/reports/G-001-report.md with the required headings, then run `python3 .goals/bin/focus.py` — it will surface what is next.
````

What the example set demonstrates, in one place: every named child is a full
contract (depth always maximal; only G-001/G-004 locked); each `## Tasks` tree
is declarative at every level — states to make true, never steps; the "PRD is
final" nuance became a fence plus a verifier clause; "for now … yet" became a
gated far-map entry instead of silent loss; the review carries per-child
verdicts, applied AND declined findings, and the anchor; and the focus file is
what a fresh thread reads first, with the exact commands that move the cursor.
