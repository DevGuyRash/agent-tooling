# Rust Fallibility

Read this reference when choosing, changing, or reviewing a failure contract.

## Classify the condition

| Condition | Default representation |
| --- | --- |
| Expected absence with no diagnostic payload | `Option<T>` |
| Recoverable failure the caller can distinguish or report | `Result<T, E>` |
| Broken internal invariant | Assertion, `unreachable!`, or panic with a reviewable invariant |
| Process cannot provide its stated service after initialization fails | Propagate to the binary boundary, then render and choose an exit policy |
| Test fixture or example whose precondition is the point of the test | A scoped `expect` may be clearer than plumbing an irrelevant error |

Do not encode environmental failure as impossibility. Files, networks, clocks, user input, configuration, decoding, locking, and external services can fail even when the happy path appears guaranteed.

## Design the error boundary

- Give libraries typed errors that support the distinctions callers need; avoid exposing private dependencies solely for convenience.
- Let applications add operation and resource context near the boundary that knows it.
- Preserve the original source when it remains useful for diagnosis.
- Keep secrets, credentials, personal data, and oversized payloads out of error text and debug output.
- Avoid both catch-all strings that erase structure and taxonomies callers cannot use.
- Treat changing public error variants, exhaustiveness, conversions, and trait bounds as compatibility work.

Use `?` when propagation preserves the contract. Map an error when crossing an abstraction boundary, translating representation, or adding actionable context.

## Complete fallible work

A successful write, send, enqueue, or staged mutation may report partial progress or acceptance rather than completed work. Follow the API's completion contract: loop over partial progress where required, perform fallible `flush`, `finish`, `commit`, or close operations explicitly, and return their failures. Resource ownership and RAII structure cleanup, but `Drop` cannot report a cleanup error and may not run after abort, process termination, or deliberate leakage; do not use destruction as proof of durable settlement.

When both the primary operation and cleanup fail, apply the surrounding contract deliberately. Preserve the primary error, the cleanup error, or both in a form callers can act on; do not let incidental cleanup overwrite the more consequential failure without policy.

## Decide whether panic is acceptable

A panic can be correct when continuing would contradict an invariant and the failure policy is explicit. Before accepting it, ask:

1. Can caller-controlled or environmental input reach the condition?
2. Is the invariant established locally and kept true across future mutation?
3. Does unwinding cross FFI or another boundary with stricter rules?
4. Would a service lose more work or availability than the contract permits?
5. Does the repository build with `panic = "abort"` anywhere relevant?

Indexing, integer arithmetic, slicing, poisoned locks, conversions, and convenience macros may panic without spelling `panic!`. Review behavior, not only syntax.

Do not replace a meaningful failure with an empty collection, zero value, log-only path, or retry loop unless that recovery belongs to the API contract.

## Verification

Test each observable failure category and the information callers rely on. Include malformed or boundary inputs, partial progress, and explicit completion failure where applicable. If panic is intentional, test the invariant at the narrowest useful layer; do not turn every panic into a global audit.

Primary anchors: [Rust error handling](https://doc.rust-lang.org/book/ch09-00-error-handling.html), [`std::result`](https://doc.rust-lang.org/std/result/), and [API Guidelines: dependability](https://rust-lang.github.io/api-guidelines/dependability.html).
