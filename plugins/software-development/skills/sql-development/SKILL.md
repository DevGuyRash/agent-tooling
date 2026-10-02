---
name: sql-development
description: Use for relational SQL queries, schemas, constraints, transactions, isolation, migrations, or embedded SQL. Compose with host languages; exclude NoSQL and administration without SQL effects.
---

# SQL Development

This skill builds on the [Software Development Foundation](../../foundation.md).

SQL changes keep query meaning, data invariants, and transaction behavior in the repository's engine and version, which its schema, migrations, driver, and CI establish; a `.sql` extension establishes no dialect. When the engine or version is unknown, avoid dialect-sensitive edits and name the missing evidence; for engine-specific behavior, consult that engine and version's primary documentation and name assumptions and unverified semantics.

- Rows are unordered unless an `ORDER BY` orders them, and pagination, limits, windows, and external output need a deterministic tie-breaker.
- Know the multiplicity each join produces; `DISTINCT` does not repair an accidental many-to-many join.
- A predicate on the nullable side of an outer join changes the join's meaning in `WHERE`; place it where the intended rows survive.
- NULL is not empty, zero, false, or an absent row: account for three-valued logic in filters, checks, joins, and nullable `NOT IN` inputs.
- Compare with NULL predicates or a supported null-safe operator, never ordinary equality, and avoid relying on implicit casts, default collation, timezone, precision, identifier folding, NULL ordering, or empty-string behavior.
- Invariants the database should protect use keys, foreign keys, uniqueness, nullability, and checks the engine supports and enforces; types follow domain range, precision, temporal, collation, and storage semantics.
- Destructive DML has a defined scope and an expected affected-row count before it runs; applied migrations stay as they are, and a destructive or irreversible change needs the user's authority and a recovery plan.
- A transaction covers the invariant it protects and no more, with isolation and locking chosen from the anomalies to prevent; account for autocommit, pooled state, savepoints, DDL, deadlocks, and retry safety.
- Values go through the driver's parameters; identifiers and fragments that parameters cannot carry are allowlisted and quoted; parameterization provides no authorization, tenant isolation, or least privilege.
- A canceled caller proves neither that the server stopped nor that a pooled session was reset: statement cancellation, result drainage, transaction outcome, and connection return are each handled.
- Never connect to an unconfirmed database target or mutate an unknown or unauthorized one; checks run against the repository's configured test databases and CI, never an invented runner, and a performance claim keeps result correctness apart from optimizer evidence, resting on representative data volume, distribution, parameter types, and write and storage tradeoffs.

Read each reference that matches what the change touches:

- [Query semantics](references/query-semantics.md): joins, aggregates, subqueries, set operations, windows, ordering, pagination, DML scope.
- [Schema and migrations](references/schema-and-migrations.md): constraints, schema design, backfills, compatibility windows, migration safety.
- [NULLs, types, and portability](references/nulls-types-and-portability.md): NULL, coercion, temporal data, precision, text comparison, identifiers, several engines.
- [Transactions and concurrency](references/transactions-and-concurrency.md): atomicity, isolation, locks, retries, idempotency.
- [Parameters and security](references/parameters-and-security.md): query construction, dynamic identifiers, privileges, tenant boundaries, sensitive data.
- [Plans and indexes](references/plans-and-indexes.md): plans, statistics, parameter types, spills, indexes.
- [Verification](references/verification.md): designing new database checks, applying a migration, validating concurrent behavior, executing consequential DML, claiming behavior across engines or versions.
