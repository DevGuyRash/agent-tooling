# Preservation Surfaces

Read this reference when “no behavior change” spans more than ordinary function results. Select only the surfaces relevant to the requested refactor.

## Published interfaces

Check names, signatures, overload resolution, generic constraints, visibility, defaults, exceptions or error values, and documented side effects. Source, binary, and wire compatibility are different promises; identify which one the repository actually supports.

Dynamic lookup, reflection, dependency injection, plugin discovery, templates, and configuration can turn a private-looking name or path into observable behavior. Search these seams before automated renames or moves.

## Data and serialization

Preserve field names, omission and default rules, ordering when contractual, numeric and time representations, enum values, unknown-field behavior, and round-trip semantics. Snapshot bytes only when byte identity is the contract; otherwise compare decoded meaning and required metadata.

Generated code and lockfiles may be consequences of a source change. Regenerate them through the repository's normal mechanism and separate unrelated churn.

## Errors and diagnostics

Callers may depend on error types, codes, exit status, retry classification, or structured fields even when human-readable wording is flexible. Preserve the declared machine contract. Avoid freezing incidental stack layout or internal message phrasing unless it is explicitly consumed.

## Ordering, side effects, and state

Observable behavior can include callback order, filesystem changes, emitted events, database transactions, cache invalidation, idempotency, and when partial state becomes visible. Compare both successful and failure paths when moving these responsibilities.

## Concurrency and timing

Do not accidentally weaken thread safety, cancellation, fairness, atomicity, or backpressure. Exact timing is rarely a refactoring contract, but deadlines, blocking versus nonblocking behavior, and bounded resource use may be.

Use deterministic synchronization evidence where possible; passing stress runs alone cannot prove equivalence.

## Consumers outside the repository

Repository tests cannot establish behavior for unknown external consumers. Consult published documentation, compatibility policy, schemas, and release history. If the requested structural change cannot preserve the supported contract, treat it as a migration or behavior change, name the consumers it affects, and carry it out as that rather than calling it a refactor.

## Evidence choices

Prefer semantic comparisons over raw snapshots, focused contract tests over private implementation assertions, and before-and-after observations under the same environment. State unresolved surfaces instead of interpreting missing evidence as equivalence.

## Authority and process-wide instances

Prefer one authoritative representation when multiple copies can drift and one source can safely serve every consumer. Do not turn “single source of truth” into a demand to abstract coincidentally similar values that have independent lifecycles or change reasons.

Use a singleton only when one process-wide instance is an actual invariant. Make initialization and shutdown ownership, concurrency behavior, failure handling, and test isolation explicit; a globally reachable object is not a substitute for a real lifecycle boundary.
