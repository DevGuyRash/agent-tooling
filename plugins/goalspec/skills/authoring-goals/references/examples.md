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

## Decompose a large request

Input:

```text
Modernize the whole app: upgrade deps, add tests everywhere, refactor the API, and improve performance.
```

Output: not one contract. A campaign manifest (`.goals/campaign-modernize.md`) splitting the aspiration into finite children with readiness statuses, e.g.:

1. `ready` — Upgrade dependency set S to versions available as of date D; build and test command C exit 0.
2. `conditional` — Add tests for module M once its public API is frozen (needs decision).
3. `not-launchable` — "Refactor the API" has no checkable terminal state; needs a concrete target.

Compile only child 1 into `.goals/current.md`. The campaign parent is never run.

## Greenfield / from spec

Input:

```text
Build a CLI that converts CSV to JSON. No code yet; here is a one-paragraph spec.
```

Output: skip the repo scan, inventory the language/test runner, and compile one small `.goals/current.md`: a minimal `csv2json` plus a smoke test, terminal state "the smoke test command exits 0 on the sample input", verifier = that command, bounded budget. Not "the CLI is done".

## Worked decomposition: dual-intent request → grounded campaign

The verbatim request — two intents, and the second is the one that usually gets dropped:

```text
Ship the guest checkout flow in docs/checkout-prd.md — the PRD is final.
Also our payment webhook tests are flaky and the team has stopped trusting
them; make them reliable.
```

### 1. Intent Inventory

Short verbatim quotes, written down before any GoalSpec vocabulary enters:

1. "Ship the guest checkout flow in docs/checkout-prd.md"
2. "payment webhook tests are flaky … make them reliable"

### 2. Campaign skeleton

`.goals/campaign-guest-checkout.md` (abridged). `## Coverage` maps inventory items — not paraphrases — and the statuses encode the rolling wave:

```markdown
## Coverage

- Inventory 1 "Ship the guest checkout flow" -> G-001, G-002, G-003
- Inventory 2 "make them reliable" (payment webhook tests) -> G-004

## Goal Graph

### G-001: Guest identity and address capture (PRD §2, §4)

- Status: ready
- Depends on: none
- Contract: .goals/children/G-001/current.md
- Terminal state: a guest completes identity and address entry per PRD §2/§4
  and `pytest tests/checkout/test_guest_identity.py -q` exits 0.
- Verifier: that command, plus `git diff --exit-code -- docs/checkout-prd.md`
  (the PRD is final and must not drift).

### G-002: Guest payment step (PRD §5)

- Status: conditional
- Depends on: G-001
- Missing decision: which PSP sandbox account to use.
- Terminal state: a guest completes payment in the PSP sandbox per PRD §5.
- Verifier: `pytest tests/checkout/test_guest_payment.py -q` (sketch).

### G-003: Order confirmation for guests (PRD §6)

- Status: conditional
- Depends on: G-002
- Terminal state: confirmation page and email match PRD §6's content table.
- Verifier: `pytest tests/checkout/test_guest_confirmation.py -q` (sketch).

### G-004: De-flake the payment webhook suite

- Status: ready
- Depends on: none
- Contract: .goals/children/G-004/current.md
- Terminal state: `tests/webhooks` passes 20 consecutive runs with zero skips.
- Verifier: a 20-iteration loop over `pytest tests/webhooks -q` that exits
  non-zero on the first failure or skipped test.
```

Only G-001 and G-004 — the execution horizon — are materialized and locked. G-002/G-003 stay sketched conditionals; each gets its full contract and lock when it is selected, against the workspace as it exists then.

### 3. One source-bound child

`.goals/children/G-001/current.md` (spine excerpts). The Intent quotes the inventory, Context names the exact PRD sections, Terminal State restates *their* requirements, and the oracle is derived from those clauses — not stamped from a sibling:

```markdown
## Intent

Inventory 1: "Ship the guest checkout flow in docs/checkout-prd.md" — this
child delivers the identity and address steps of that flow.

## Context

- docs/checkout-prd.md §2 "Guest identity" (email-only, no account creation)
- docs/checkout-prd.md §4 "Address capture" (single page; validation rules in
  table 4.1)

## Terminal State

This goal is complete when:

- A guest provides an email only (§2) and address entry enforces every rule in
  table 4.1 (§4) on a single page.
- `pytest tests/checkout/test_guest_identity.py -q` exits 0.

## Verifier

Completion must be verified by:

- `pytest tests/checkout/test_guest_identity.py -q`
- `git diff --exit-code -- docs/checkout-prd.md`
- Pinned: scripts/verify_checkout_flow.py sha256 0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9
```

The `Pinned:` line freezes the shared checkout verifier alongside the contract (`sha256sum` of the companion at lock time): `run_verifiers.py` refuses to certify against a mutated companion, and `audit_goal.py` re-checks the pin.

### 4. Decomposition review, recorded in the manifest

The flow: `validate_campaign.py` printed `review anchor: 7c1e0b…` before the
review; applying findings 1 and 2 changed the Goal Graph, so the manifest was
re-validated (new anchor `0a9f44…`), the verdicts re-confirmed against the
edited graph, and the final anchor recorded:

```markdown
## Decomposition Review

Reviewer: decomposition_reviewer (refute bias).

- G-001: confirmed — terminal clauses restate PRD §2/§4 requirements; oracle is its own.
- G-002: confirmed (sketch) — section-bound; materializes at selection.
- G-003: weak — cited only "the PRD" before finding 2; rebound to §6.
- G-004: confirmed — verifier strengthened by finding 1.

1. APPLIED — G-004's verifier was a single `pytest tests/webhooks -q` run: it
   could pass on a lucky run, or by skipping the flaky tests, without making
   them reliable. Strengthened to 20 consecutive runs with zero skips.
2. APPLIED — G-003 cited only "the PRD" while its siblings cited sections;
   rebound to PRD §6 "Order confirmation" with an oracle of its own.
3. DECLINED — reviewer flagged G-002/G-003 as unlocked. Declined: they are the
   sketched tail of the rolling wave; locking now would freeze guesses about a
   PSP decision that has not landed. They materialize at selection.

Anchor: 0a9f44c2e7b15d8a30f6921b4cd07e5f8a36d1c09b274e6f5a801d92c3e4f7ab
```

Every finding either changed the manifest or was declined with a reason, every
child carries a verdict, and the anchor matches the validated manifest — a
review recorded before validation, or left stale after edits, warns on every
later validation. A review that only records findings has not closed.
