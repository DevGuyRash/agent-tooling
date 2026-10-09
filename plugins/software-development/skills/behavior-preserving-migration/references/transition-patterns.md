# Transition Patterns

Read this reference when selecting a migration shape. A pattern is an option with costs, not a mandatory stage list.

## Offline replacement

Stop writes or service, transform the bounded state, validate it, switch to the target, and resume. Prefer this when allowed downtime is sufficient and parallel operation would add more risk than it removes. Define backup, restore, validation, and forward-recovery behavior before the stop.

## Expand, migrate, contract

First make producers and consumers tolerate both forms. Then move usage or data while compatibility remains. Finally remove the old form after usage evidence and the support window permit it. This is useful for published APIs, schemas, and rolling deployments where old and new versions coexist.

## Adapter or branch by abstraction

Put a stable seam around the changing implementation and route current behavior through it. Add and compare the target behind the seam, switch authority, then remove obsolete implementations and transitional code. Keep translation rules and semantic loss explicit.

## Strangler routing

Route selected capabilities or cohorts through a facade while the remainder use the source. Use this for incrementally replacing a separable system when routing can remain reliable. Account for facade availability, latency, cross-system calls, shared state, and eventual removal.

## Shadowing and comparison

Send copied traffic or replayed inputs to the target without making its result authoritative. Compare semantic results and operational behavior. Prevent shadow execution from duplicating external side effects, mutating production state, or exposing sensitive data beyond its existing boundary.

## Backfill plus change capture

Copy historical state, capture concurrent source changes, apply them in a defined order, and reconcile before cutover. Define snapshot boundaries, duplicate and missing-record detection, idempotent replay, lag limits, deletes, and recovery after interruption.

## Dual reads and writes

Dual reads can compare or fall back while the target matures. Dual writes can support rollback but create partial-success, ordering, conflict, and transaction hazards. Prefer a single authoritative write with change capture when it meets requirements. With dual writes, specify repair and reconciliation; do not treat two local transactions as one atomic operation.

## Staged traffic

Move a bounded tenant, cohort, shard, region, or percentage, observe declared guardrails, then expand. Select cohorts that expose representative behavior and avoid a routing scheme whose skew invalidates the comparison. Define automatic stop conditions on those guardrails and a manual halt.

## Select and retire

Choose from downtime tolerance, consumer independence, data mutability, state volume, reversibility, consistency, and operational capacity. Combining patterns is reasonable when each handles a named risk. Remove transitional components after target authority, consumer migration, reconciliation, and rollback-window closure are demonstrated.
