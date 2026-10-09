# SQL Query Semantics

Load this reference for query design or review involving cardinality, joins, aggregates, subqueries, set operations, windows, ordering, pagination, or DML scope.

## Define the Result Contract

- State whether the query should return exactly one, zero-or-one, or many rows and whether duplicate rows are meaningful.
- Identify the key or grain of each input and output row before joining or aggregating.
- Name the required columns and their nullability; avoid depending on positional or implicit shapes across boundaries.
- Treat row order as unspecified without `ORDER BY`. Include a unique or otherwise deterministic tie-breaker when stable pagination or output matters.
- Treat `LIMIT`, `TOP`, or `FETCH` without deterministic ordering as an arbitrary subset when the engine permits it.

## Joins and Multiplicity

- Verify each join predicate against keys and expected one-to-one, one-to-many, or many-to-many relationships.
- Check unmatched rows and duplicate keys explicitly, not only the happy-path fixture.
- Remember that a `WHERE` predicate rejecting NULLs from the nullable side of an outer join can make it behave like an inner join.
- Qualify ambiguous columns and aliases where schema evolution could change resolution.
- Use `DISTINCT` only when set-like output is the contract, not as a repair for unexplained multiplication.

## Aggregates, Subqueries, and Sets

- Check grouping grain, empty-input behavior, and which aggregates ignore NULL.
- Use `HAVING` for group predicates and `WHERE` for input-row predicates according to intended meaning.
- Choose correlated subqueries, joins, CTEs, and windows for clarity and semantics; optimization behavior varies by engine and version.
- Select `EXISTS`, `IN`, `NOT EXISTS`, and `NOT IN` with NULL and duplicate behavior in mind.
- Choose `UNION ALL` when duplicates must be retained or deduplication is unnecessary; choose `UNION` when set semantics are required.
- Define window partitioning, ordering, and frame explicitly where defaults would change results.

## Data Modification

- Establish the intended target key, predicate, and expected affected-row count for `UPDATE`, `DELETE`, and merge/upsert operations.
- Account for duplicate source matches and concurrent changes in merge/upsert semantics.
- Preview target rows or counts through a read path when risk warrants it, but do not assume a preview remains current without transaction protection.
- Treat `RETURNING`, generated keys, triggers, cascades, and affected-row reporting as dialect-specific observable behavior.

PostgreSQL's documentation illustrates two portable hazards: ordinary `SELECT` retains duplicates by default and output order is unspecified without `ORDER BY`: [SELECT](https://www.postgresql.org/docs/current/sql-select.html).
