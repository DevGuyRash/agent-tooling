---
name: rust-development
description: >-
  Idiomatic, production-grade Rust development with phased workflow enforcement,
  banned-pattern scanning, and deterministic verification. Use when the task
  involves: (1) Writing new Rust code, features, or bugfixes, (2) Migrating an
  existing tool or codebase to Rust, (3) Reviewing Rust pull requests or enforcing
  Rust coding standards, (4) Setting up Rust CI/CD pipelines or GitHub Actions for
  Rust projects, (5) Creating or modifying Rust workspace layouts (single-crate or
  monorepo), (6) Scaffolding a new Rust project or crate, (7) Configuring Clippy
  lints, rustfmt, or Rust toolchain settings, (8) Debugging Rust compilation errors
  or borrow-checker issues, or (9) Any task where the primary language is Rust
  (.rs files). Includes scaffolding scripts, Clippy lint configs, banned-family
  test harness, and GitHub Actions CI template.
metadata:
  author: agent-skills
  version: "2.1.0"
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

You SHALL output your observations using the block below. You SHALL NOT skip this block.

> **Required output — Round \u22121**
>
>     ### Round \u22121 \u2014 Observations
>
>     1. <observation>
>     2. <observation>
>     3. ...

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

NOTE: Use `cargo check` (not `cargo clippy`) during Phase 0. The clippy config denies `todo!()`, which is expected in stubs. Clippy runs later in Phase 2.

You SHALL present stubs for review with evidence: requirement summary, complete stub files, `cargo check` output, and an approval request.
WHEN stubs do not compile THEN you SHALL fix them before proceeding.
You SHALL NOT proceed to Phase 1 until stubs compile and are approved.

You SHALL output the block below as evidence. You SHALL NOT skip this block.

> **Required output — Phase 0 Stub Review**
>
>     ### Phase 0 — Stub Review
>
>     **Requirement summary:** <2-5 sentences>
>
>     **Files:** <list of files created or modified>
>
>     **Stub code:** <complete stub files>
>
>     **cargo check output:**
>     <paste cargo check output>
>
>     **Approval request:** Stubs compile. Proceed to Phase 1?

WHEN working in non-interactive mode (approval policy is `never`) THEN you SHALL emit the block and proceed without waiting.
WHEN working in interactive mode THEN you SHALL wait for explicit approval before proceeding.

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

You SHALL output the block below as evidence. You SHALL NOT skip this block.

> **Required output — RED**
>
>     #### RED — `<test_name>`
>     <paste cargo test failure output>

#### Phase 1.2 — GREEN: Write the minimal implementation to pass

You SHALL replace the `todo!()` in the function under test with the simplest code that makes the red test pass.
You SHALL NOT write more code than the current set of passing tests demands.
You SHALL run `cargo test` and confirm the targeted test passes (green).
You SHALL also confirm no previously-passing tests regressed.

```bash
cargo test 2>&1 | tail -5
# Expected: ok. N passed; 0 failed
```

You SHALL output the block below as evidence. You SHALL NOT skip this block.

> **Required output — GREEN**
>
>     #### GREEN — `<test_name>`
>     <paste cargo test passing output>

#### Phase 1.3 — REFACTOR: Improve under green

WHEN the implementation or test can be simplified, deduplicated, or clarified THEN you SHALL refactor now.
You SHALL NOT change observable behavior during refactor -- all tests SHALL remain green.
You SHALL run `cargo test` after every refactor pass and confirm all tests still pass.
WHEN no meaningful refactor is needed THEN you SHALL note "No refactor needed" and proceed.

You SHALL output the block below as evidence. You SHALL NOT skip this block.

> **Required output — REFACTOR**
>
>     #### REFACTOR — `<function_or_unit_name>`
>     <description of changes, or "No refactor needed.">
>     <paste cargo test output confirming all tests still pass>

After completing 1.1-1.2-1.3 for one unit, you SHALL loop back to Phase 1.1 for the next test stub.
You SHALL continue until all `todo!()` bodies in both tests and functions are replaced.

#### Phase 1 rules (apply across all sub-phases)

You SHALL NOT use any pattern listed in `references/banned-patterns.md`.
WHEN a banned pattern has a specific escape hatch (for example `// INVARIANT:`) THEN you SHALL use that escape hatch.
WHEN no pattern-specific escape hatch exists and the pattern must remain THEN you SHALL add `// ALLOW: <reason>` on the same line.

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

#### Phase 1 — Test coverage rule

You SHALL write at minimum one happy-path and one error/edge-case test per public function.
You SHALL exercise every variant of every error enum defined in the module.
WHEN an error variant exists but no test triggers it THEN you SHALL add a test that does before Phase 1 is complete.

### Phase 2 — Verify

You SHALL run the verification script:

```bash
<skills-file-root>/scripts/verify.sh [--dir <path>]
```

WHEN `verify.sh` is unavailable THEN you SHALL run the checks from `references/verify-manual.md`.
You SHALL paste the output of all Phase 2 commands as evidence.

You SHALL output the block below as evidence. You SHALL NOT skip this block.

> **Required output — Phase 2 Verification**
>
>     ### Phase 2 — Verification Evidence
>
>     <paste full verify.sh output or manual check output>

`verify.sh` now includes installation checks (Phase 2.0) that confirm:
- `banned_family.rs` test harness is installed in a crate's `tests/` directory.
- `.github/workflows/ci.yml` and `.github/scripts/detect_rust_workspaces.py` are present.
- Clippy lint config is present in the root `Cargo.toml`.
- All workspace member crates inherit lints via `[lints] workspace = true`.

IF installation checks report missing artifacts THEN you SHALL run `scaffold.sh --all` first.
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
- [ ] You SHALL confirm every error enum variant is exercised by at least one test.
- [ ] You SHALL confirm doc comments are complete on all public items with Examples.

You SHALL output the checklist above with `[x]` marks and supporting evidence as a single block.
You SHALL NOT skip this block or return a null/empty completion message.

> **Required output — Phase 3 Checklist**
>
>     ### Phase 3 — Completion Checklist
>
>     - [x] Phase 0 stubs compiled: `cargo check` output above.
>     - [x] Round -1 observations addressed: <brief note or "see Round -1">.
>     - [x] TDD cycle followed: RED/GREEN/REFACTOR evidence above for each unit.
>     - [x] Banned patterns clean: verify.sh scan above.
>     - [x] No oversized files: verify.sh complexity check above.
>     - [x] `cargo build` passes.
>     - [x] `cargo fmt --check` passes.
>     - [x] `cargo clippy --workspace --all-targets -- -D warnings` passes.
>     - [x] `cargo test` passes.
>     - [x] No `todo!()` remains.
>     - [x] Tests cover happy-path and error-case for all functions.
>     - [x] Every error enum variant exercised by at least one test.
>     - [x] Doc comments complete on all public items with Examples.

### Round 5 — Final sanity check

You SHALL set aside all checklists and evaluate holistically.
You SHALL revisit Round −1 observations and confirm each was addressed or documented.
WHEN something still feels wrong but you cannot pinpoint why THEN you SHALL note it explicitly.
You SHALL include a brief holistic assessment confirming Round −1 observations were revisited.

You SHALL output the block below as evidence. You SHALL NOT skip this block.

> **Required output — Round 5**
>
>     ### Round 5 — Holistic Assessment
>
>     **Round -1 revisit:**
>     - Observation 1: <addressed / accepted / still open>
>     - Observation 2: ...
>
>     **Overall assessment:** <1-3 sentences on code quality, test coverage, residual concerns.>

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
| `assets/detect_rust_workspaces.py` | `scaffold.sh --ci` — CI workspace detector |
