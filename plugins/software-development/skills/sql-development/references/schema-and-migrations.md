# SQL Schema and Migrations

Load this reference for tables, keys, constraints, type changes, indexes as integrity mechanisms, migrations, backfills, or rolling deployment compatibility.

## Encode Invariants

- Use primary keys, foreign keys, uniqueness, `NOT NULL`, and `CHECK` when the detected engine supports and enforces the required invariant.
- Verify constraint enforcement and connection settings; some engines can disable or defer checks.
- Keep database and application validation complementary. Database constraints protect all writers; application validation can provide earlier domain feedback.
- Name constraints when repository conventions and operational diagnostics benefit from stable names.
- Treat cascades, deferred constraints, generated columns, exclusion constraints, and partial uniqueness as vendor-specific choices.

## Choose Data Shapes Deliberately

- Select types from required range, precision, comparison, timezone, collation, storage, and interoperability semantics.
- Use exact numeric types where exact decimal behavior is required; do not assume binary floating point represents decimal values exactly.
- Choose natural or surrogate keys from stability, domain identity, distribution, interoperability, and write behavior.
- Normalize when it protects integrity and update consistency. Denormalize only with an explicit source of truth and synchronization mechanism; measure first when performance is the reason.
- Treat soft deletion, audit timestamps, tenant columns, UUIDs, and JSON storage as design choices, not defaults.

## Design Safe Migrations

- Treat a migration in shared history as applied, and prefer a new corrective migration to editing it.
- Follow the repository's migration framework, naming, transaction, checksum, and ordering model.
- Separate schema expansion, data backfill, application cutover, validation, and contraction when old and new application versions coexist.
- Make backfills resumable and bounded when data volume, locks, logs, or replication lag can matter.
- Account for table rewrites, lock duration, constraint validation, index build behavior, and DDL transaction semantics against the established engine/version evidence.
- Define post-migration invariants and verify them independently.

## Consequential Changes

- Before dropping data, narrowing types, replacing values, rebuilding large objects, or applying to a shared environment, establish backup/restore or another tested recovery path where reversal cannot reconstruct lost data.
- Do not promise a down migration when rollback would be unsafe or lossy; state the forward-recovery strategy instead.
- Keep credentials, production identifiers, and connection details out of migration source and logs.

Constraint semantics differ even in familiar constructs. For example, a `CHECK` may pass on TRUE or UNKNOWN, so it does not replace `NOT NULL`: [PostgreSQL constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).
