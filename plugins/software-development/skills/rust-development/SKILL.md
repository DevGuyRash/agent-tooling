---
name: rust-development
description: Use for substantive Rust source, Cargo, or tooling. Covers ownership, APIs/errors, workspaces, MSRV, and verification; compose async-rust, unsafe-rust, or rust-panic-audit as needed; exclude workflow-only work.
---

# Rust Development

This skill builds on the [Software Development Foundation](../../foundation.md).

Rust changes keep ownership and failure behavior visible at their boundaries. They fit the crate's role (library, binary, procedural macro, test support, or workspace tooling) and the edition, minimum supported Rust version, feature policy, targets, `no_std` status, lockfile policy, and public API and serialization compatibility that the nearest `Cargo.toml`, workspace manifest, and CI establish, and they leave those choices, the dependencies, feature defaults, and lockfile as they are unless the request changes them.

- Implement the requested behavior in the language of the code you are changing. Shipped code that runs a program written in another language, through an interpreter, a shell, or a copy embedded in it, keeps that language's runtime as a dependency and makes the requested code a launcher rather than the implementation; port the logic, even when a working version in another language sits in the repository. Running a program the request names, or running another implementation only to compare results in tests, is not this.
- Model invariants with types and ownership before adding runtime checks; borrow for temporary access, and transfer ownership when the callee retains or consumes the value.
- Before cloning to satisfy the borrow checker, decide which component should own the value; a clone is right when it is the clearest correct tradeoff and its cost fits the path.
- Types are concrete by default, and a trait or generic needs a real substitution boundary; conversions stay explicit at trust, precision, and allocation boundaries.
- Use iterators, pattern matching, and standard-library types where they make intent clearer.
- Unexpected panic is an API decision, not a blanket syntax ban: return `Result` or `Option` for recoverable conditions the caller can act on, and reserve assertions and panics for violated invariants, impossible states, or process-level policy explicit in context.
- Use `unwrap` or `expect` only for a local, reviewable invariant, in tests, or in tightly scoped startup code whose stated policy is to abort; prefer an explanatory `expect` message to one that repeats the operation.
- Never discard an error or turn it into a default unless the contract defines that recovery; add context at boundaries where it identifies the failed operation without leaking secrets.
- Visibility stays as narrow as callers require; for public items, weigh semver impact, downstream inference, exhaustiveness, auto traits, feature availability, and documented error behavior, and never expose an implementation dependency through a public signature by accident.
- Platform-specific code stays behind the existing `cfg` and feature structure; the default feature set does not represent every supported build, so compile the meaningful feature combinations.
- Clippy, compiler warnings, and static analysis are evidence, not substitutes for behavior tests.

Read each reference that matches the change:

- [Fallibility](references/fallibility.md): designing a fallible public API, deciding whether a panic is acceptable, or changing error context.
- [Cargo contracts](references/cargo-contracts.md): features, workspace structure, Cargo metadata, MSRV, platform gates, or dependency exposure.
- [Public contracts](references/public-contracts.md): public traits, types, bounds, opaque returns, iterators, or downstream compile behavior.
- [Synchronous concurrency](references/sync-concurrency.md): synchronous threads, channels, shared state, worker shutdown, or atomics.
