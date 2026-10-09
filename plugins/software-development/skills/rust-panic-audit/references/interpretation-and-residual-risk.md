# Interpretation and Residual Risk

## Evidence classes

Compiler findings come from individually selected Clippy lints supported by the repository toolchain. They are authoritative for the construct and compiled configuration that produced the diagnostic. A configured deny level may make Cargo exit nonzero; when all errors are requested policy lints, that is a completed audit with findings rather than a tooling failure.

Lexical findings are review candidates. The scanner removes comments, normal and raw strings, nested block comments, root conventional test/fixture paths, `#[test]` items, and definitely test-only `#[cfg(test)]` items before matching unwrap/expect calls, panic-family macros, `std::panic::panic_any`, `std::panic::resume_unwind`, and profile-specific assertions. A production module remains in scope even when a nested directory is named `test` or `tests`. The scanner is not a Rust parser: aliases, shadowing, macros, unusual attributes, generated source layouts, and conditional compilation can change meaning.

An unavailable lint means the requested compiler evidence could not be obtained from the repository toolchain. The lexical pass may cover direct unwrap, expect, panic-family, and assertion syntax, but it does not replace semantic indexing, arithmetic, or result-return analysis.

## Panic and unwind boundaries

Rust panics either unwind or abort according to the compiled panic strategy and target support. `catch_unwind` catches only unwinding Rust panics, is not a general exception mechanism, and does not establish that the called code cannot panic. The panic hook runs before a panic is caught; dropping the caught payload can itself panic; behavior for caught foreign exceptions is unspecified. Tests require unwinding on stable Rust, while build scripts and procedural macros ignore profile panic settings. At FFI boundaries, use the correct ABI and treat an unwind that crosses an ABI which does not permit it as a correctness and safety defect rather than evidence supplied by this direct-construct audit.

## Execution effects and bounds

Cargo and Clippy may compile and execute `build.rs` and procedural macros. Run the audit in a disposable worktree or externally enforced sandbox when those programs are untrusted or mutation prevention is required. The runner's before/after checks detect tracked-content changes and changes to the set of non-ignored untracked paths outside Cargo's target directory; they do not prevent execution, roll back side effects, observe newly ignored paths, or detect content changes to a path that was already untracked.

A command deadline, output limit, surviving descendant, worktree mutation, or uncertain temporary-lockfile ownership makes the result incomplete. A retry is comparable evidence only when it preserves the declared scope; if a bound changes, record the new bound. Compact JSON changes representation, not evidence completeness.

## Expectations and invariants

Review each `#[expect(..., reason = "...")]` in context. A useful reason names the invariant or boundary that makes the construct intentional and remains true when the code changes. An expectation is scoped evidence of intent, not proof that the invariant holds.

Preserve repository lint configuration and use the compiler-supported expectation mechanism when the repository's minimum Rust version supports it. Otherwise follow the repository's existing scoped lint policy and report the compatibility limit.

## Required residual-risk statement

Every report retains the applicable limits:

- dependencies may panic internally
- indexing and custom trait behavior outside the selected coverage may panic
- allocation failure may abort or panic depending on environment
- omitted features, targets, and `cfg` branches were not compiled
- build scripts and procedural macros can execute outside the scanned source
- destructors may panic, including during unwinding
- poisoned locks and runtime configuration can expose panic paths
- FFI unwind behavior depends on ABI and boundary handling
- unexercised runtime paths are not disproved by static checks

Add concrete repository-specific risks discovered during the audit. Remove a generic item only when the evidence actually excludes it from the declared scope.

## Disposition

Classify each finding as a recoverable operational failure, programmer defect, proven invariant, test/prototype-only use, generated or excluded scope, or unresolved risk. A correction should preserve public error behavior and repository compatibility; do not replace a panic with a swallowed error or a fabricated default.

Re-run the same profile and scope after corrections. A clean direct scan plus passing repository verification supports only the bounded conclusion stated in the skill, never a whole-program guarantee.
