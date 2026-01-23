# Depth playbook (adversarial traces + inverse proofs)

**Status:** Canonical baseline  
**Role:** Orchestrator or Reviewer-mode Subagent  
**Goal:** Increase code-coverage depth and counterexample quality when outputs are shallow.

---

## I) When to use this (triggered)

You SHOULD use this playbook when any of the following is true:

- UACRP escalation triggers apply.
- You cannot produce an anchored adversarial trace that feels “real”.
- Residual Risk is large due to missing concrete disproof attempts.
- Findings are generic (“add tests”, “handle errors”) without a break scenario.

---

## II) Depth target selection (WHAT to go deep on)

Select 1–3 **depth targets** using these heuristics (pick the highest-risk):

- crosses a trust boundary (untrusted input → trusted state/effect)
- performs external effects (DB writes, network calls, filesystem, subprocess)
- owns state transitions / invariants (idempotency, dedup, retries, migrations)
- handles authN/authZ/tenancy boundaries
- runs concurrently / async / has cancellation or backpressure semantics
- parses / decodes / deserializes untrusted payloads
- touches contract surfaces (API, schema, CLI output, config)

Each depth target SHALL be anchored (`path:line` + symbol/snippet).

---

## III) Adversarial trace template (HOW to go deep)

For each depth target you analyze, produce at least one end-to-end trace:

- **Entry point (anchor):** ...
- **Assumed caller / threat model:** <who controls inputs; what’s trusted?>
- **Steps (anchored):**
  1. validation/parsing boundary (where it should reject)
  2. transformation boundary (where invariants can be lost)
  3. side-effect boundary (where it commits to the world)
- **Trust boundaries crossed:** ...
- **Invariants that must hold:** <state constraints; authorization; idempotency; ordering>
- **Concrete break attempt:** <specific input / ordering / fault injection>

Your break attempt SHALL be concrete. Examples:

- “Send payload X with field Y missing” (parsing/validation)
- “Replay request with same idempotency key” (idempotency)
- “Two concurrent calls: A races B so invariant Z breaks” (concurrency)
- “Rollback: old code reads new data” (compatibility)
- “Remote returns 200 with malformed body” (integration)

---

## IV) Counterexample menu (choose at least one per high-risk theorem)

When attempting to disprove a theorem, choose one or more:

1) **Input edge cases:** empty/null, huge sizes, invalid encodings, unexpected types, adversarial strings.
2) **State machine faults:** retries, duplicates, partial failures, “fail halfway then retry”, out-of-order events.
3) **Concurrency schedules:** interleavings, cancellation mid-flight, lock ordering inversions, TOCTOU windows.
4) **External faults:** timeouts, 429s, partial responses, flapping dependencies, stale caches.
5) **Compatibility skew:** N-1/N+1 mixed deployments, rollback reading forward-written data.
6) **Resource bounds:** unbounded loops/queues, O(n²), memory growth, hot path amplification.

---

## V) Proof-carrying finding bar (make the inverse proof bite)

For each BLOCKER/MAJOR finding you produce:

- You SHALL include a **minimal reproducer** (input/sequence/schedule).
- You SHALL include a **How to verify** plan that would fail if the bug remains.
- You SHOULD propose the smallest safe fix that breaks the reproducer.

---

## VI) Anti-bloat rule (keep depth, drop noise)

Aim for ≤ 5 findings unless new unique failure modes keep appearing.
Prefer one deep, well-evidenced failure mode over many shallow hints.

