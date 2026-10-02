---
name: rust-panic-audit
description: "Use to audit direct panic surfaces (unwrap, expect, panic macros, indexing, arithmetic) in a Rust scope that a request or policy names, such as hostile-input, embedded, FFI, or high-availability boundaries. Compose with rust-development; exclude routine review."
---

# Rust Panic Audit

This skill builds on the [Software Development Foundation](../../foundation.md).

A panic audit assesses the direct panic surfaces of a declared Rust scope and never claims the program is panic-free. Ordinary Rust work stays panic-resistant, not panic-prohibited: operational failures normally use recoverable errors, panics may still represent programmer defects or proven invariants, and tests, prototypes, and justified invariants may use `unwrap` or `expect` under the repository's policy.

The repository's workspace manifest, toolchain files, Cargo configuration, package selection, features, targets, and lint configuration define the audit: audit only the packages, targets, and features the user names or the repository establishes, keep Cargo's repository-native defaults otherwise, and never silently substitute a newer toolchain or `--all-features`.

Choose a profile:

- `core` checks direct `unwrap`/`expect` variants and explicit `panic`, `todo`, `unimplemented`, and `unreachable` constructs.
- `strict-boundary` also requests the supported indexing/slicing, arithmetic, panic-in-result, and unwrap-in-result lints, and reviews production assertion and debug-assert candidates.

When Python 3 is available, run:

```text
python3 <skills-file-root>/scripts/panic_audit.py \
  --manifest-path <Cargo.toml> \
  --profile core|strict-boundary \
  [--workspace] [--package <name> ...] [--all-targets] \
  [--no-default-features] [--all-features | --features <csv>] \
  [--target <triple>] [--timeout-seconds <seconds>] \
  [--max-command-output-bytes <bytes>] [--json]
```

- The runner invokes the repository's Cargo and Clippy, selects restriction lints individually, and runs an independent lexical candidate scan; it keeps a member `--manifest-path` rather than silently auditing workspace defaults.
- It creates and removes an absent `Cargo.lock` only while file identity and content prove runner ownership.
- Each child command has a deadline, an output limit, and process-tree cleanup; exceeding a bound makes the audit incomplete. You SHALL NOT retry a timed-out or output-limited command until you have named and corrected the cause or deliberately changed that bound, and an incomplete run never becomes clean evidence.
- Target selection is Cargo-default or `--all-targets` only. For a narrower selector such as `--lib`, `--bin`, or `--test`, run the exact repository-compatible Cargo and Clippy commands directly and mark the supplemental lexical result incomplete; never broaden the scope and present it as equivalent.
- Even with `--all-targets`, the lexical pass excludes root conventional test and fixture directories and definitely test-only items; report that limit separately from compiler target coverage.
- Cargo and Clippy execute repository build scripts and procedural macros with the caller's authority. The runner does not intentionally edit tracked files and detects tracked changes and non-ignored untracked path-set changes outside Cargo's target directory, but it cannot prevent side effects, observe new ignored paths, or detect edits to an already-untracked file. You SHALL NOT run the runner, or Cargo and Clippy directly, where build code is untrusted or no repository mutation is acceptable until a disposable worktree or stronger external sandbox isolates the run.
- Without Python, run the equivalent repository-compatible Cargo and Clippy commands directly, state that the supplemental lexical pass was unavailable, and keep the result incomplete wherever that gap matters.
- Compiler-supported `#[expect(..., reason = "...")]` is the preferred scoped rationale; never introduce magic suppression comments.

Read [interpretation and residual risk](references/interpretation-and-residual-risk.md) before making a boundary assurance, interpreting an unavailable lint, or deciding whether a candidate is an accepted invariant.

Exit status:

- `0`: the requested checks completed and found no violations or review candidates.
- `1`: compiler violations or lexical review candidates were found.
- `2`: tooling failed, scope resolution failed, or the audit was incomplete.

Compiler diagnostics are authoritative for the supported direct lints; lexical matches are candidates, not parsed proof; intentional expectations are reviewed against the boundary contract, not counted as an automatic pass or failure.

Report the profile and the exact manifest, packages, target mode or triple, default-feature choice, named features, and execution limits; compiler findings; lexical candidates; intentional expectations; unavailable lints; tooling gaps; worktree side-effect evidence; and residual risk. Every requested check needs a recorded result or a named blocker, and every finding a disposition. When the build cannot reach the requested scope, return an incomplete audit with the failing command category and the next repository-native check rather than silently weakening the scope. Conclude at most "no forbidden direct constructs found in the audited scope"; never "panic-free".
