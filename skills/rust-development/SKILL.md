---
name: rust-development
description: >-
  Idiomatic, production-grade Rust development with phased workflow enforcement,
  banned-pattern scanning, and deterministic verification. Use when writing new
  Rust code, migrating tools to Rust, reviewing Rust PRs, setting up Rust CI/CD,
  creating Rust workspace layouts, or enforcing Rust coding standards. Covers
  single-crate and workspace/monorepo projects. Includes scaffolding scripts,
  Clippy lint configs, banned-family test harness, and GitHub Actions CI template.
metadata:
  author: agent-skills
  version: "2.0.0"
---

# Rust Development

You SHALL follow a phased workflow to produce idiomatic, production-grade Rust.
You SHALL support both single-crate and workspace/monorepo layouts.
You SHALL minimize external dependencies and prefer Rust-native `std` solutions.

---

## Workflow selection

You SHALL select the workflow matching the task from the table below.
WHEN the task does not clearly match a row THEN you SHALL default to Standard.

| Task | Workflow |
|---|---|
| New Rust code, feature, bugfix | **Standard** — Round −1 → Phase 0→1 (TDD)→2→3 → Round 5 |
| Monorepo: new crate or cross-crate change | **Monorepo** — Standard + `references/monorepo.md` |
| Migrate existing tool to Rust | **Migration** — `references/migration.md` |
| Set up CI/CD, lint config, workspace | **Bootstrap** — see Bootstrap section |
| Code review of Rust changes | **Verify-only** — run `scripts/verify.sh` for Phase 2 checks; if `verify.sh` is unavailable, run all Phase 2 checks from `references/verify-manual.md`. For deeper semantic review, combine with `$code-review`. |

---

## Standard workflow

### Round −1 — Fresh eyes

You SHALL read through existing code or the change request before any structured work.
You SHALL record unfiltered observations — smells, risks, unclear intent, potential simplifications.
You SHALL NOT consult checklists or rules during this round.

### Phase 0 — Plan and stub

You SHALL complete Phase 0 before any implementation.

You SHALL write a 2–5 sentence requirement summary listing files to create or modify.
WHEN a new dependency is needed THEN you SHALL state its justification.

You SHALL write stub `.rs` files containing:
- You SHALL include module-level documentation via `//!`.
- You SHALL include type definitions with `///` doc comments.
- You SHALL include function signatures with `todo!()` bodies.
- You SHALL include error types when the module returns `Result`.

You SHALL include Purpose, Arguments, Returns, Panics, and Examples in every public doc comment.

```rust
/// Purpose: Compute the checksum of `data`.
///
/// # Arguments
/// * `data` - byte slice to hash
///
/// # Returns
/// A 32-byte digest.
///
/// # Panics
/// None.
///
/// # Examples
/// ```
/// let digest = checksum(b"hello");
/// assert_eq!(digest.len(), 32);
/// ```
pub fn checksum(data: &[u8]) -> [u8; 32] {
    todo!()
}
```

You SHALL write test stubs under `#[cfg(test)]` with `todo!()` bodies.
You SHALL create at minimum one happy-path and one error/edge-case test stub.

You SHALL verify stubs compile:

```bash
if cargo check; then
  echo "✓ Stubs compile"
else
  echo "BLOCKED: Stubs must compile before proceeding."
  exit 1
fi
```

You SHALL present stubs for review with evidence: requirement summary, complete stub files, `cargo check` output, and an approval request.
WHEN stubs do not compile THEN you SHALL fix them before proceeding.
You SHALL NOT proceed to Phase 1 until stubs compile and are approved.

### Phase 1 — Implement (Red/Green/Refactor)

You SHALL implement code using a red/green/refactor TDD cycle.
You SHALL follow the rules in `references/guidelines.md`.
Phase 0 produces compilable stubs with `todo!()` bodies and test stubs -- these are your starting point.

You SHALL work through one function or logical unit at a time.
For each unit, you SHALL complete all three sub-phases before moving to the next unit.

#### Phase 1.1 — RED: Write a failing test

You SHALL replace the `todo!()` body in one test stub with real assertions and setup.
The test SHALL call the function under test and assert the expected behavior.
You SHALL run `cargo test` and confirm the test fails (red).
WHEN the test fails for the wrong reason (compilation error, wrong assertion, panic in unrelated code) THEN you SHALL fix the test before proceeding.

You SHALL target one test per cycle -- do not fill in multiple test stubs at once.

```bash
cargo test <test_name> 2>&1 | tail -20
# Expected: FAILED (the function body is still todo!() or returns a wrong value)
```

Evidence: you SHALL record the test name and the failure output.

#### Phase 1.2 — GREEN: Write the minimal implementation to pass

You SHALL replace the `todo!()` in the function under test with the simplest code that makes the red test pass.
You SHALL NOT write more code than the current set of passing tests demands.
You SHALL run `cargo test` and confirm the targeted test passes (green).
You SHALL also confirm no previously-passing tests regressed.

```bash
cargo test 2>&1 | tail -5
# Expected: ok. N passed; 0 failed
```

Evidence: you SHALL record the passing test output.

#### Phase 1.3 — REFACTOR: Improve under green

WHEN the implementation or test can be simplified, deduplicated, or clarified THEN you SHALL refactor now.
You SHALL NOT change observable behavior during refactor -- all tests SHALL remain green.
You SHALL run `cargo test` after every refactor pass and confirm all tests still pass.
WHEN no meaningful refactor is needed THEN you SHALL note "No refactor needed" and proceed.

After completing 1.1-1.2-1.3 for one unit, you SHALL loop back to Phase 1.1 for the next test stub.
You SHALL continue until all `todo!()` bodies in both tests and functions are replaced.

#### Phase 1 rules (apply across all sub-phases)

You SHALL NOT use these patterns in non-test code:
- You SHALL NOT use `.unwrap()` / `.expect()` without a same-line `// INVARIANT:` comment.
- You SHALL NOT use `panic!()`, `todo!()`, `unimplemented!()`, or `dbg!()`.
- You SHALL NOT use `unreachable!()` without a same-line `// INVARIANT:` comment.
- You SHALL NOT use `println!()` / `eprintln!()` outside entrypoints.
- You SHALL NOT use glob imports outside tests.
- You SHALL NOT use `&String` / `&Vec<T>` / `&Box<T>` parameters.
- You SHALL NOT use `.iter().next()` on slices/`Vec`; for collections without `.first()`, you MAY use `.iter().next()` only with same-line `// ALLOW: non-slice-next`.

You SHALL use these idioms:
- You SHALL use `?` for error propagation.
- You SHALL use `if let` for single-variant matching.
- You SHALL use iterators over index loops.
- You SHALL use `Option<T>` for absence.
- You SHALL use structured error enums for public APIs.

You SHALL prefer borrowing over cloning and `let` over `let mut`.
You SHALL format error messages as: what failed → why → what to do next, lowercase, no debug dumps, no secrets.

You SHALL default to ZERO external dependencies — `std` is your first, second, and third choice.
You SHALL NOT add an external crate when `std` provides equivalent functionality, even if a crate is more ergonomic.
IF a dependency is trivial to implement in fewer than 50 lines THEN you SHALL NOT add it.
You SHALL NOT introduce async runtime crates (`tokio`, `async-std`) unless the repository already uses one — prefer `std::future`, `std::task`, and `std::thread`.
You SHALL NOT use `serde`, `anyhow`, or `thiserror` in libraries — use `std` traits and custom error enums.

### Phase 2 — Verify

You SHALL run the verification script:

```bash
<skills-file-root>/scripts/verify.sh [--dir <path>]
```

WHEN `verify.sh` is unavailable THEN you SHALL run the checks from `references/verify-manual.md`.
You SHALL paste the output of all Phase 2 commands as evidence.
IF any checks fail THEN you SHALL fix the issues and re-run verification.

### Phase 3 — Completion checklist

You SHALL confirm every item below and paste the checklist with `[x]` marks and command outputs as evidence.

- [ ] You SHALL confirm Phase 0 stubs compiled before implementation.
- [ ] You SHALL confirm Round −1 observations were addressed or documented as acceptable.
- [ ] You SHALL confirm TDD cycle was followed: each function has RED (failing test) → GREEN (minimal pass) → REFACTOR evidence.
- [ ] You SHALL confirm all banned patterns are fixed — scan clean.
- [ ] You SHALL confirm no oversized files exist, or justification is provided.
- [ ] You SHALL confirm `cargo build` passes.
- [ ] You SHALL confirm `cargo fmt --check` passes.
- [ ] You SHALL confirm `cargo clippy --workspace --all-targets -- -D warnings` passes.
- [ ] You SHALL confirm `cargo test` passes.
- [ ] You SHALL confirm no `todo!()` remains.
- [ ] You SHALL confirm new tests cover happy-path and error-case.
- [ ] You SHALL confirm doc comments are complete on all public items with Examples.

### Round 5 — Final sanity check

You SHALL set aside all checklists and evaluate holistically.
You SHALL revisit Round −1 observations and confirm each was addressed or documented.
WHEN something still feels wrong but you cannot pinpoint why THEN you SHALL note it explicitly.
You SHALL include a brief holistic assessment confirming Round −1 observations were revisited.

---

## Bootstrap workflow

You SHALL use the scaffolding script to set up workspace tooling:

```bash
<skills-file-root>/scripts/scaffold.sh <workspace-root> [--clippy] [--banned-test] [--ci] [--all] [--force]
```

| Flag | Effect |
|---|---|
| `--clippy` | Append workspace lint config to `Cargo.toml` |
| `--banned-test` | Copy `banned_family.rs` into a runnable crate `tests/` directory |
| `--ci` | Copy `.github/workflows/ci.yml` and `.github/scripts/detect_rust_workspaces.py` |
| `--all` | All of the above |
| `--force` | Overwrite existing files and replace prior config |

WHEN re-running scaffold THEN you MAY omit `--force` to preserve existing config.

---

## Migration workflow

WHEN converting an existing non-Rust tool THEN you SHALL read `references/migration.md` before Phase 0.
You SHALL follow the Standard workflow extended with migration-specific additions:
- WHEN in Phase 0 THEN you SHALL also perform behavior capture, golden-file extraction, and invocation-wrapper planning.
- WHEN in Phase 1 THEN you SHALL also produce the behavior-preservation table and create wrapper shims.
- WHEN in Phase 2 THEN you SHALL also diff original-vs-Rust outputs and confirm all diffs are empty.

---

## Monorepo rules

WHEN working in a Rust workspace or monorepo THEN you SHALL read `references/monorepo.md` before Phase 0.
You SHALL place all `Cargo.toml` files under one Rust root.
You SHALL maintain one `Cargo.lock` and one `target/`.
You SHALL keep binary entrypoints thin: arg parsing, wiring, and library call only.
WHEN a shared module is needed THEN you SHALL create it only if two or more crates use it.

---

## Reference index

You SHALL load only the reference needed for the current task.

| File | When to read |
|---|---|
| `references/guidelines.md` | Phase 1 of any workflow — full coding rules |
| `references/monorepo.md` | Working in a Rust workspace or monorepo |
| `references/migration.md` | Converting a non-Rust tool to Rust |
| `references/verify-manual.md` | `verify.sh` is unavailable |
| `references/banned-patterns.md` | Quick-reference table of all banned patterns |

## Script index

| Script | Purpose |
|---|---|
| `scripts/verify.sh` | Run all Phase 2 checks: banned scan, fmt, clippy, test |
| `scripts/scaffold.sh` | Bootstrap lint config, test harness, CI into a workspace |

## Asset index

| Asset | Used by |
|---|---|
| `assets/clippy-lints.toml` | `scaffold.sh --clippy` — workspace lint snippet |
| `assets/banned_family.rs` | `scaffold.sh --banned-test` — test harness |
| `assets/ci.yml` | `scaffold.sh --ci` — GitHub Actions workflow |
