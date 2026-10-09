# SQL Transactions and Concurrency

Load this reference for atomicity, isolation, locks, deadlocks, savepoints, retries, idempotency, or coordination with external systems.

## Define the Unit of Work

- State the invariant and all reads and writes that must be atomic.
- Keep transactions no broader or longer than needed; user interaction, remote calls, and large computation can extend lock or snapshot lifetime.
- Identify autocommit and connection-pool behavior. Transaction state belongs to a connection/session, not abstract application code.
- Confirm whether DDL participates in transactions and whether the migration tool adds its own transaction.
- Treat nested transaction APIs as savepoints unless the driver and engine prove independent transactions.

## Choose Concurrency Control from Failure Modes

- Identify relevant anomalies: dirty or non-repeatable reads, phantoms, lost updates, write skew, duplicate creation, and stale decisions.
- Use constraints, conditional writes, locks, optimistic versions, or isolation according to the invariant and engine behavior.
- Do not infer behavior from isolation-level names alone; defaults and implementations differ by engine, version, and settings.
- Establish a consistent lock order when multiple resources are locked.
- Verify lock hints and vendor-specific clauses against the established engine/version evidence and prove their effect under representative concurrency.

## Retry Safely

- Retry only failures documented as transient for the detected engine or driver, such as selected deadlock or serialization failures.
- Retry the whole transaction from a clean state, not only the final statement.
- Bound attempts and time, preserve cancellation, and include jitter/backoff only when the repository's operational model warrants it.
- Ensure database writes and externally visible effects are idempotent or coordinated before retrying.
- Treat constraint violations, syntax errors, authorization failures, and unknown failures as non-transient unless the engine documents the case as retryable.

## External Effects

- A database transaction does not atomically include email, HTTP calls, message brokers, files, or another database by default.
- Use an established outbox, inbox, saga, idempotency-key, or distributed-transaction mechanism when the architecture requires coordination.
- Avoid holding locks while invoking external systems unless a documented protocol requires it.
- Make commit uncertainty explicit: after a connection failure, determine whether retrying could duplicate an effect.

## Host Adapter Lifecycle

- Treat caller cancellation, driver request, server statement termination, cursor/result closure, transaction completion, and connection return as separate boundaries.
- Follow the selected driver and engine contract for cancellation; closing a client-side future or abandoning a row iterator may leave server work or an open transaction alive.
- Drain or close streaming results according to the adapter contract before returning the connection. Do not reuse a pooled session with an unknown transaction, isolation, role, search path, temporary object, prepared-state, or session-setting residue.
- Preserve the primary query, cancellation, or transaction outcome while retaining cleanup failure evidence through the repository's error model.
- Test cancellation while waiting for a connection, executing, streaming rows, and committing when those states are reachable; prove the pool remains usable and no owned work or transaction survives.

PostgreSQL demonstrates why engine/version evidence matters: its Read Uncommitted behaves as Read Committed and its Repeatable Read prevents more anomalies than the standard minimum: [transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
