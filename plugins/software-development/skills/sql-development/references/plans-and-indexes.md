# SQL Plans and Indexes

Load this reference when choosing, changing, or reviewing indexes, or when a relational performance claim depends on execution plans, estimates, statistics, casts, parameters, spills, or access paths.

## Preserve semantics first

Establish result cardinality, ordering, duplicates, NULL behavior, affected rows, and transaction semantics before comparing performance. A faster query with different rows or consistency is a behavior change, not an optimization.

## Use representative optimizer evidence

Identify the engine/version, relevant settings, schema, indexes, table and partition sizes, data distribution, skew, correlation, and statistics state. Compare estimated with actual rows and work where a safe environment permits execution. Large estimate errors, spills, repeated loops, unexpected sorts, remote calls, or lost partition/index access can matter more than the plan node names.

Capture the actual bound parameter types and representative values or value classes. Implicit casts, generic plans, parameter sniffing, collation, and prepared-statement behavior can select different access paths than a literal entered in an interactive client.

Know whether the plan command executes the statement. Never run execution analysis for destructive or expensive work against a target not known to be safe; use a disposable representative database or a safe rollback wrapper only when the engine contract makes that evidence valid.

## Evaluate indexes as system changes

Choose key order, included/covering data, uniqueness, predicates, expression support, and clustering from the queries the code runs and its write workload, accounting for build time, locks, storage, cache pressure, write amplification, maintenance, vacuum/compaction, replication, and migration compatibility. Claim index performance only from measured reads and plans.

Do not add an index solely because a plan uses a scan, remove one solely because a sampled plan did not use it, or compare estimated costs across unrelated statements as elapsed time. Recheck after representative statistics and data are present, and preserve a rollback or forward-recovery path for consequential index changes.

## Report the evidence horizon

Report the workload, data shape, parameter profile, plan/measurement commands, before/after results, estimates versus actuals, spills or resource ceilings, and write/storage tradeoffs. Limit the conclusion to the exercised engine, version, configuration, and distribution.
