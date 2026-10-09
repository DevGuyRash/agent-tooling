---
name: behavior-preserving-migration
description: "Use when an API, schema, data store, dependency, runtime, implementation language, service, or architecture moves to a new form while its consumers keep working: compatibility windows, backfills, cutover, and rollback. Excludes local refactors."
---

# Behavior-Preserving Migration

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

A migration moves a source implementation or representation to a target while the declared compatibility envelope holds through transition and cutover. The envelope covers intentional contracts, not every undocumented quirk; a known bug stays only when it is an explicit compatibility requirement.

Name the envelope's consumers and invariants: APIs, protocols, schemas, serialized data, and supported version combinations; results, errors, ordering, side effects, and idempotency; data completeness, uniqueness, consistency, and authorization boundaries; availability, latency, capacity, and operational objectives; intended behavior changes and the consumers that must coordinate.

- Keep facts, assumptions, proposed safeguards, and intended deltas apart; verify an intentional behavior change as a change, never as preservation.
- The plan inventories ownership, readers and writers, dependency direction, data volume, deployment order, rollback feasibility, and irreversible steps, and records current-contract or characterization evidence from the source as it stands.
- Tests alone do not prove equivalence; name the external consumers that repository tests cannot prove.
- Choose the simplest path that meets the real availability and rollback needs; a small offline migration can be safer than permanent dual operation, and a high-risk published interface may need coexistence and staged traffic.
- Each intermediate state lets supported old and new participants coexist for the required window, with one authority per mutable fact where possible; unavoidable replication or dual writes need defined transaction ordering, idempotency, conflict handling, reconciliation, lag, and partial-failure recovery.
- Separate writes to source and target are not atomic: a first write that succeeds before the second fails leaves a state the plan must detect and repair.
- Stage the move: add compatibility capacity before depending on it; move a bounded cohort, consumer, or data segment; compare semantic outputs, state, and operational signals at the declared boundary, with checksums or counts only where they prove the needed invariant; repair or roll back a stage whose guardrail fails; expand only when the current stage's evidence supports it.
- Keep enough source state and compatibility to execute the promised rollback.
- You SHALL NOT commit an irreversible transformation until backup or reconstruction evidence exists and it meets stronger preconditions than a reversible stage.
- Cutover names readiness evidence, point of no return, rollback or forward-recovery path, and monitoring window; afterwards, confirm that traffic, consumers, and data use the target as intended.
- You SHALL NOT remove the source path, adapters, flags, backfill machinery, or excess telemetry until their dependents are gone and the rollback window has closed.
- Transitional architecture has an owner, taken from the code's CODEOWNERS or the change's author, and a cleanup condition, so it does not become the permanent system by accident.
- The migration is complete only when the target is authoritative, required consumers have moved, invariants hold, and cleanup is done or waits only on its release condition.

Read [transition patterns](references/transition-patterns.md) when choosing expand-and-contract, an adapter, strangler routing, shadow comparison, backfill, dual reads or writes, staged traffic, or an offline cutover.
