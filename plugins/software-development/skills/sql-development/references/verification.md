# SQL Verification

Load this reference before choosing SQL checks, applying a migration, validating concurrent behavior, or reporting completion.

## Choose the Right Environment

- Confirm engine, version, extensions, compatibility mode, session settings, schema/migration state, and seed data.
- Prefer a disposable or repository-provided test database for schema changes and destructive cases.
- Do not connect to or mutate a shared, staging, or production environment unless the task and host authorization explicitly permit it.
- Use the repository's migration runner, driver, container, fixtures, and CI commands rather than inventing a parallel harness.
- Keep connection details and credentials out of output.

## Prove Query Behavior

- Assert result shape, cardinality, duplicates, ordering, NULL cases, empty input, boundary values, and expected errors.
- Include fixtures that expose join multiplication, missing related rows, nullable anti-matches, and tied sort keys when relevant.
- Verify affected-row behavior and resulting state for inserts, updates, deletes, and upserts.
- Compare behavior on every claimed database/version target.
- Use property or randomized tests only when the repository supports them and they improve coverage of relational invariants.

## Prove Schema and Transactions

- Apply migrations from the supported prior state to an empty and representative populated database when practical.
- Verify constraints independently by attempting relevant invalid states.
- Check backfill completeness, defaults, generated values, and old/new application compatibility required by deployment.
- Exercise concurrent transactions when correctness depends on isolation, locking, uniqueness, retry, or idempotency.
- Verify failure and retry paths, including external-effect coordination.

## Treat Performance Tools Safely

- Route tuning to `performance-engineering` and apply the established engine/version evidence when interpreting plans.
- Know whether the selected plan command executes the statement. PostgreSQL `EXPLAIN ANALYZE`, for example, executes it: [`EXPLAIN`](https://www.postgresql.org/docs/current/sql-explain.html).
- Run execution plans for destructive statements or expensive workloads only on a disposable or rolled-back target.
- Do not claim improvement from aesthetics, estimated cost alone, or a non-representative fixture.

## Completion Evidence

Report engine/version and consequential settings, schema state, commands run, fixtures and edge cases exercised, observed results, and skipped targets. Distinguish syntax validation, behavior verification, migration verification, concurrency evidence, and performance evidence.
