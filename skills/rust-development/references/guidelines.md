# Rust Coding Guidelines

## Table of Contents

1. [Compatibility and Precedence](#1-compatibility-and-precedence)
2. [Toolchain and Stability](#2-toolchain-and-stability)
3. [Banned Patterns](#3-banned-patterns)
4. [Required Idioms](#4-required-idioms)
5. [Formatting and Lints](#5-formatting-and-lints)
6. [Modules and File Structure](#6-modules-and-file-structure)
7. [Naming, Visibility, and API Discipline](#7-naming-visibility-and-api-discipline)
8. [Ownership, Borrowing, and Mutability](#8-ownership-borrowing-and-mutability)
9. [Traits, Generics, and Abstraction Budget](#9-traits-generics-and-abstraction-budget)
10. [Design Patterns](#10-design-patterns)
11. [Hermetic Code and Side-Effect Isolation](#11-hermetic-code-and-side-effect-isolation)
12. [Error Handling](#12-error-handling)
13. [Async and I/O Concurrency](#13-async-and-io-concurrency)
14. [CPU Parallelism](#14-cpu-parallelism)
15. [Shared State and Synchronization](#15-shared-state-and-synchronization)
16. [Determinism and Stable Output](#16-determinism-and-stable-output)
17. [Performance and Complexity](#17-performance-and-complexity)
18. [Testing](#18-testing)
19. [Dependencies](#19-dependencies)
20. [Unsafe Code and FFI](#20-unsafe-code-and-ffi)
21. [Security](#21-security)

---

## 1. Compatibility and Precedence

- You SHALL treat existing repository conventions — layout, naming, tooling, lint settings, CI rules, runtime choices — as authoritative.
- WHEN this document conflicts with an explicit repository rule THEN you SHALL follow the repository rule.
- You SHALL keep changes scoped to the task.
- You SHALL NOT perform incidental refactors such as mass renames or formatting churn UNLESS required for correctness or testability.
- WHEN a new pattern is introduced THEN you SHALL apply it consistently within the touched area.
- WHEN an existing local pattern exists in the touched area THEN you SHALL follow the existing local pattern.

## 2. Toolchain and Stability

- WHEN the repository defines a pinned toolchain or MSRV THEN you SHALL use that pinned toolchain and MSRV.
- WHEN no MSRV is defined THEN you SHALL NOT use language or library features newer than 6 months without explicit approval.
- You SHALL target stable Rust by default.
- You SHALL NOT use nightly-only features UNLESS the repository already requires nightly or the change is explicitly approved.

## 3. Banned Patterns

- You SHALL consult `references/banned-patterns.md` for the full banned-patterns table.
- You SHALL NOT use any pattern listed in `references/banned-patterns.md` in non-test code.
- WHEN a banned pattern has a specific escape hatch (for example `// INVARIANT:`) THEN you SHALL use that specific escape hatch.
- WHEN no pattern-specific escape hatch exists and the pattern is intentionally kept THEN you SHALL add `// ALLOW: <reason>` on the same line.

## 4. Required Idioms

- WHEN a function returns `Result` or `Option` THEN you SHALL use `?` for error propagation.
- WHEN only one variant requires handling THEN you SHALL use `if let`.
- WHEN all variants require explicit handling THEN you SHALL use `match`.
- You SHALL use iterators over index-based `for` loops.
- WHEN a value may be absent THEN you SHALL use `Option<T>` — you SHALL NOT use sentinel values.
- WHEN a value is one of N alternatives THEN you SHALL use an enum — you SHALL NOT use magic strings or numbers.
- You SHALL use `.cloned()` — you SHALL NOT use `.map(|x| x.clone())`.
- You SHALL use `.first()` for slices and `Vec` — you SHALL NOT use `.iter().next()` for those collections; for collections without `.first()`, `.iter().next()` is allowed only with same-line `// ALLOW: non-slice-next`.
- WHEN the collection length is needed without filtering THEN you SHALL use `.len()` — you SHALL NOT use `.iter().count()`.
- You SHALL use `if x` or `if !x` — you SHALL NOT use `if x == true` or `if x == false`.

## 5. Formatting and Lints

- You SHALL keep code `rustfmt`-clean per the repository's formatting config.
- You SHALL ensure `cargo clippy` produces no warnings on touched files.
- You SHALL NOT leave debug artifacts in committed code: `dbg!()`, debugging `println!()`, commented-out blocks longer than 3 lines, dead code, unreachable code.
- WHEN using `#[allow(...)]` THEN you SHALL scope it to the narrowest item and add a same-line `// Reason:` comment.
- WHEN the reason for an `#[allow(...)]` suppression no longer applies THEN you SHALL remove the suppression.

## 6. Modules and File Structure

- You SHALL keep binary entrypoints — `src/main.rs`, `src/bin/*.rs` — thin: arg parsing, dependency wiring, library call, exit code mapping.
- WHEN a file grows difficult to navigate or mixes unrelated concerns THEN you SHALL split it.
- You SHALL NOT extract shared helpers UNLESS 2 or more call sites exist.
- You SHALL separate I/O and side effects from pure logic.

## 7. Naming, Visibility, and API Discipline

- You SHALL use `UpperCamelCase` for types, traits, and enum variants.
- You SHALL use `snake_case` for functions, methods, variables, and modules.
- You SHALL use `SCREAMING_SNAKE_CASE` for constants and statics.
- You SHALL keep items private by default.
- WHEN an item is `pub` THEN you SHALL write a doc comment explaining its purpose.
- WHEN an item is `pub` THEN you SHALL add at least one test exercising it.
- WHEN an item is `pub` THEN you SHALL treat it as a contract.
- You SHALL make invalid states unrepresentable — model domain rules with types such as newtypes, enums, and validated structs rather than scattered runtime checks.

## 8. Ownership, Borrowing, and Mutability

- WHEN ownership is not needed THEN you SHALL borrow — accept `&T`, `&str`, `&[T]`, or `&Path`.
- You SHALL NOT clone without justification: the type implements `Copy`, the data is small and cheap to clone, or a comment explains the need.
- You SHALL use `let` immutable bindings by default.
- WHEN `let mut` is required THEN you SHALL keep the mutable scope as small as possible.
- You SHALL NOT pass `&mut` through more than 2 call levels without a justifying comment.
- You SHALL avoid unnecessary heap allocation.
- You SHALL use iterators and slices to avoid creating intermediate vectors.

## 9. Traits, Generics, and Abstraction Budget

- You SHALL keep abstraction proportional to need.
- WHEN only one concrete type is ever passed THEN you SHALL NOT introduce a generic parameter.
- WHEN fewer than 2 concrete implementations exist THEN you SHALL NOT use `dyn Trait`.
- WHEN using `impl Trait` in argument position THEN you SHALL ensure only one concrete type is passed at each call site.
- You SHALL NOT create trait hierarchies without demonstrated need.

## 10. Design Patterns

- WHEN a recurring design problem exists THEN you MAY use a design pattern to solve it.
- You SHALL NOT introduce patterns — Factory, Builder, Strategy, Visitor, or similar — UNLESS the flexibility they provide is actually exercised in the codebase.
- WHEN a design pattern is introduced THEN you SHALL document in a comment why the pattern is warranted and what variation it enables.
- You SHALL prefer straightforward code over pattern-heavy code.
- You SHALL be wary of indirection-adding patterns such as dependency injection frameworks, service locators, and abstract factories WHEN simple constructor arguments suffice.

## 11. Hermetic Code and Side-Effect Isolation

- You SHALL separate pure logic from side effects such as I/O, network, filesystem, time, and randomness.
- You SHALL use pure functions for core business logic.
- You SHALL inject side-effecting dependencies as function arguments — you SHALL NOT hardcode them as globals.
- WHEN a function performs side effects THEN you SHALL make the effects obvious via naming or documentation.
- You SHALL prefer simple function arguments for dependency injection over DI frameworks.
- WHEN global state or singletons exist THEN you SHALL ensure they are resettable for testing.

## 12. Error Handling

- You SHALL use `Result<T, E>` for recoverable failures.
- You SHALL use `Option<T>` for absence.
- You SHALL use `?` for error propagation.
- You SHALL structure error messages as: what failed, why it failed, what to do next.
- WHEN an error is user-facing THEN you SHALL write a single sentence, lowercase, with no debug dumps, no `{:?}`, no secrets, and no PII.
- You SHALL NOT use panics for normal control flow.
- You SHALL NOT use any panic-inducing method in non-test code. This includes `.unwrap()`, `.unwrap_err()`, `.unwrap_unchecked()`, `.expect()`, and `.expect_err()`. The ONLY exception is when an invariant guarantees correctness AND you add `// INVARIANT:` on the same line.
- You SHALL NOT use `assert!()`, `assert_eq!()`, or `assert_ne!()` outside test code. Use `debug_assert!` with `// INVARIANT:` when a runtime check is needed, or return `Result`.
- You SHOULD prefer `.expect("descriptive message")` over `.unwrap()` when `// INVARIANT:` is used.
- WHEN writing a library THEN you SHALL define a structured error enum.
- WHEN writing an application THEN you SHALL map errors to exit codes and print user-friendly messages to stderr.

## 13. Async and I/O Concurrency

### 13.1 When to Use Async

- You SHALL prefer `std`-native async primitives: `async fn`, `std::future::Future`, `std::task::Poll`, `std::task::Waker`.
- You SHALL NOT add an async runtime crate (`tokio`, `async-std`, `smol`) unless the repository already depends on one.
- WHEN the repository has no async runtime THEN you SHALL implement concurrency using `std::thread`, `std::sync::mpsc`, or manual `Future` implementations.
- WHEN fewer than 10 concurrent I/O operations are needed THEN you SHALL use synchronous I/O with `std::thread` for parallelism.
- WHEN writing new async code THEN you SHALL prefer composing `std::future::poll_fn` and `std::pin::Pin` over utility crates like `futures` or `pin-project`.

### 13.2 Blocking Inside Async

- You SHALL NOT block an executor thread.
- WHEN blocking or CPU-heavy work exceeds 1ms THEN you SHALL use `spawn_blocking`.
- You SHALL NOT call `block_on` from within an executor thread.

### 13.3 Structured Concurrency

- You SHALL keep task handles and await or join them.
- WHEN detaching a task THEN you SHALL document why detaching is safe and how the task terminates.
- WHEN multiple tasks are spawned for one operation THEN you SHALL collect all errors, propagate cancellation, and release resources deterministically.

### 13.4 Cancellation and Timeouts

- WHEN an async operation can hang — network calls, external processes — THEN you SHALL apply a timeout.
- WHEN cancellation can leave partial state THEN you SHALL make updates atomic, record enough information to recover, or implement compensating cleanup.

### 13.5 Bounded Concurrency

- You SHALL NOT spawn tasks in an unbounded loop.
- You SHALL cap concurrency using a semaphore, bounded channel, or worker pool.
- WHEN no specific bound is determined THEN you SHALL default to `min(num_cpus, collection_size, 32)`.

### 13.6 Locks Across Await

- You SHALL NOT hold `std::sync::Mutex` or `std::sync::RwLock` across an `.await` point.
- WHEN a lock must be held across `.await` THEN you SHALL use an async-aware lock such as `tokio::sync::Mutex`, add a comment explaining why, and verify no deadlock exists.

## 14. CPU Parallelism

- You SHALL choose parallelism intentionally.
- WHEN overhead dominates the work THEN you SHALL use sequential execution.
- You SHALL keep parallel output deterministic via sorting or ordered iteration.
- You SHALL NOT use shared mutable state across threads — you SHALL prefer per-thread locals with a merge step.
- WHEN sharing immutable data across threads THEN you SHALL use `Arc<T>`.

## 15. Shared State and Synchronization

- You SHALL minimize shared mutable state.
- You SHALL keep critical sections brief.
- WHEN multiple locks exist THEN you SHALL document lock ordering.
- You SHALL NOT hold locks during I/O, `.await`, or heavy CPU work.
- You SHALL use the simplest synchronization primitive: `Mutex` for exclusive access, `RwLock` only when reads dominate at 10:1 or greater, atomics only for single values.
- WHEN using atomics THEN you SHALL default to `SeqCst` — WHEN using a weaker ordering THEN you SHALL add a comment proving correctness.
- WHEN implementing a cache THEN you SHALL define key, value, max size, and eviction policy; you SHALL use immutable entries with `Arc<V>` values; you SHALL make the cache resettable for testing.

## 16. Determinism and Stable Output

- You SHALL keep user-visible outputs stable across runs.
- WHEN iteration order matters THEN you SHALL use `BTreeMap`/`BTreeSet` or sort before output.
- WHEN using `HashMap` or `HashSet` THEN you SHALL sort keys before user-visible output.
- WHEN producing concurrent output THEN you SHALL document the ordering contract.

## 17. Performance and Complexity

- You SHALL reason about algorithmic complexity for non-trivial code paths.
- WHEN a loop processes user-sized input THEN you SHALL add a comment near the loop:

```rust
// O(n) where n = number of items (expected: 10–1000)
```

- You SHALL NOT introduce O(n²) patterns: no `Vec::contains()` in loops, no nested loops over the same collection, no repeated string concatenation — use `String::with_capacity()` — and no repeated parsing inside loops.

## 18. Testing

### 18.1 Red/Green/Refactor discipline

- You SHALL use a red/green/refactor TDD cycle during Phase 1.
- RED: write one failing test that asserts expected behavior, then run `cargo test` and confirm it fails.
- GREEN: write the minimal implementation that makes the failing test pass, then run `cargo test` and confirm all tests pass.
- REFACTOR: improve code quality under green; run `cargo test` after every change to confirm no regressions.
- You SHALL complete one full RED/GREEN/REFACTOR cycle before starting the next test.
- WHEN fixing a bug THEN you SHALL write a failing test reproducing the bug (RED) before writing the fix (GREEN).
- WHEN a new edge case is discovered during implementation THEN you SHALL add a failing test for it before fixing it.

### 18.2 Test quality

- WHEN adding new behavior THEN you SHALL add tests.
- WHEN fixing a bug THEN you SHALL add a regression test.
- You SHALL keep tests hermetic and deterministic: temp dirs, fixed seeds, no timing-sensitive sleeps, no network in default tests.
- You SHALL provide at minimum one happy-path test and one error or edge-case test.
- WHEN output format matters THEN you SHOULD use golden or snapshot tests.

## 19. Dependencies

- You SHALL default to ZERO external dependencies. `std` is your first, second, and third choice.
- You SHALL NOT add an external crate when `std` provides equivalent or composable functionality — even if a crate is more ergonomic.
- WHEN `std` cannot satisfy the requirement AND the implementation would exceed 50 lines of non-trivial code THEN you MAY propose ONE dependency with written justification of what `std` alternative was considered.
- You SHALL NOT add a dependency for functionality that is trivial to implement (< 50 lines).
- You SHALL use `default-features = false` and enable only the features that are required.
- You SHALL NOT use `tokio`, `async-std`, or any async runtime unless the repository already depends on one.
- You SHALL NOT use `serde` for internal serialization when `Display`/`FromStr` or manual parsing suffices.
- You SHALL NOT use `anyhow`/`eyre`/`thiserror` in libraries — define your own error enum.
- WHEN adding a new dependency THEN you SHALL audit `cargo tree --depth 1` and reject any crate that duplicates `std` functionality.

## 20. Unsafe Code and FFI

- You SHALL avoid `unsafe` by default.
- WHEN `unsafe` is required THEN you SHALL add a `// SAFETY:` comment explaining the invariants, keep the `unsafe` block minimal, provide a safe wrapper API, and add tests covering the unsafe behavior.

## 21. Security

- You SHALL treat all external input as untrusted.
- You SHALL validate inputs and fail with actionable error messages.
- You SHALL NOT include secrets in logs, error messages, or debug output.
- You SHALL redact credentials and PII.
- You SHALL exclude sensitive fields from `Debug` implementations.
