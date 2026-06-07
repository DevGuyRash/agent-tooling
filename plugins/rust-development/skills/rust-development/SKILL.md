---
name: Rust Development
description: >-
  REQUIRED when any part of the task touches Rust code or Rust tooling — do not
  write, review, debug, or scaffold Rust without this skill active.
  Covers: (1) Writing new Rust code, features, or bugfixes, (2) Migrating an
  existing tool or codebase to Rust, (3) Reviewing Rust pull requests or
  enforcing Rust coding standards, (4) Setting up Rust CI/CD pipelines or
  GitHub Actions, (5) Creating or modifying Rust workspace layouts (single-crate
  or monorepo), (6) Scaffolding a new Rust project or crate, (7) Configuring
  Clippy lints, rustfmt, or Rust toolchain settings, (8) Debugging Rust
  compilation errors or borrow-checker issues, or (9) Any task where the primary
  language is Rust (.rs files). If the task involves Rust, use this skill.
metadata:
  author: agent-tooling
  version: "2.2.0"
---

# Rust Development

You SHALL follow a phased workflow to produce idiomatic, production-grade Rust.
You SHALL support both single-crate and workspace/monorepo layouts.
You SHALL minimize external dependencies and prefer Rust-native `std` solutions.

---

## Workflow preflight

For every workflow except Verify-only, you SHALL begin with the preflight below.

You SHALL apply this precedence order before choosing a workflow:
1. Existing repository conventions and direct user instructions.
2. Hard safety/correctness gates from this skill.
3. House-style defaults from this skill.

You SHALL resolve repository compatibility before applying house defaults.
You SHALL treat the compatibility map below as mandatory evidence.

WHEN the task requires new or expanded unsafe code, FFI, raw-pointer work, or
reasoning about existing unsafe invariants THEN this skill is out of profile by
default. You SHALL NOT treat that as a Fast Path or Standard task unless the
repository already establishes the unsafe boundary and the user explicitly wants
that work under this skill.

You SHALL output the block below for every non-review workflow. You SHALL NOT
skip this block.

> **Required output — Repo Compatibility Map**
>
>     ### Repo Compatibility Map
>
>     **Runtime/executor already in use:** <tokio / sync std / none / other>
>     **Error handling style already in use:** <custom enums / anyhow / thiserror / other>
>     **Serialization/config stack already in use:** <serde / manual / none / other>
>     **Lint/test/CI tooling already in use:** <cargo fmt / clippy / nextest / custom / other>
>     **Workspace/toolchain/MSRV status:** <single crate / workspace / pinned toolchain / MSRV / unknown>
>     **Unsafe posture in touched area:** <no unsafe present / existing unsafe nearby / unsafe required / unknown>
>     **Workflow decision:** <Fast Path / Standard / Monorepo / Migration / Bootstrap> — <why>

---

## Workflow selection

You SHALL select the workflow matching the task from the table below.
WHEN the task does not clearly match a row THEN you SHALL default to Standard.

| Task | Workflow |
|---|---|
| Localized behavior fix or narrow behavior adjustment inside one existing crate that fully satisfies Fast Path qualification | **Fast Path** — Round −1 → Fast Path Qualification → Phase 1 (TDD) → 2 → 3 → Round 5 |
| New Rust code, feature, structural bugfix, or any task that does not fully satisfy Fast Path qualification | **Standard** — Round −1 → Phase 0 → Phase 1 (TDD) → 2 → 3 → Round 5 |
| Monorepo: new crate or cross-crate change | **Monorepo** — Standard + `references/monorepo.md` |
| Migrate existing tool to Rust | **Migration** — Standard + `references/migration.md` |
| Set up CI/CD, lint config, workspace | **Bootstrap** — see Bootstrap section |
| Code review of Rust changes | **Verify-only** — run `scripts/verify.sh` for Phase 2 checks; if `verify.sh` is unavailable, run all Phase 2 checks from `references/verify-manual.md`. For deeper semantic review, combine with `$code-review`. |

---

## Shared entry point

### Round −1 — Fresh eyes

You SHALL read through existing code or the change request before any structured work.
You SHALL record unfiltered observations — smells, risks, unclear intent, potential simplifications.
You SHALL NOT consult checklists or rules during this round.

You SHALL output your observations using the block below. You SHALL NOT skip this block.

> **Required output — Round −1**
>
>     ### Round −1 — Observations
>
>     1. <observation>
>     2. <observation>
>     3. ...

---

## Fast Path workflow

You SHALL use Fast Path only when every qualification item below is true before implementation.
WHEN any item is false or unknown THEN you SHALL NOT use Fast Path.

Fast Path is for localized behavior changes to existing production code. It skips
Phase 0 stubs but still requires Round −1, RED/GREEN/REFACTOR, full verification,
the completion checklist, and the final holistic review.

Fast Path SHALL qualify only when all of the following are true:
- The change is confined to one existing crate.
- The requested outcome is a localized behavior fix or narrow behavior adjustment to existing production code.
- No new public API item, public type, public trait, public module, public error enum, public error variant, command, crate, or cross-crate contract is introduced.
- No `Cargo.toml`, toolchain file, workspace layout, `.github` file, bootstrap asset, CI asset, dependency choice, runtime choice, or serialization/config stack is changed.
- No unsafe, FFI, raw-pointer work, or unsafe concurrency contract is required.
- The agent can name the existing production symbol(s) or behavior area being changed before implementation.
- The agent can write at least one targeted failing regression or behavior test against existing code before implementation.

Fast Path MAY include:
- Modifying existing production files inside that crate.
- Adding or modifying tests in that crate.
- Adding local private helpers inside existing production files when needed to complete the localized fix.

Fast Path SHALL NOT include:
- New production modules or new production files.
- New public surface area.
- New dependencies or structural/bootstrap/configuration work.
- Any case where the task boundary cannot be confidently stated during preflight.

You SHALL output the block below as evidence before entering Phase 1. You SHALL NOT skip this block.

> **Required output — Fast Path Qualification**
>
>     ### Fast Path Qualification
>
>     **Requirement summary:** <2-5 sentences>
>
>     **Existing symbols / behavior area:** <named existing symbols or exact behavior area>
>
>     **Planned files:** <existing production files and test files only>
>
>     **Repo compatibility map:** see above
>
>     **Qualification checklist:**
>     - [x] One existing crate only.
>     - [x] Localized behavior change to existing production code.
>     - [x] No new public / cross-crate surface.
>     - [x] No Cargo.toml / toolchain / workspace / .github / CI / dependency / runtime / serialization changes.
>     - [x] No unsafe / FFI / raw-pointer work.
>     - [x] Existing symbol(s) or behavior area identified.
>     - [x] Targeted RED test(s) identified.
>
>     **Planned RED test(s):** <test names>

---

## Standard workflow

### Phase 0 — Plan and stub

You SHALL complete Phase 0 before any Standard, Monorepo, or Migration implementation.

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

Phase 0 remains required for Standard because compilable skeletons and explicit
surface checkpoints reduce drift when new structure or API shape is being defined.

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

---

## Phase 1 — Implement (Red/Green/Refactor)

You SHALL implement code using a red/green/refactor TDD cycle.
You SHALL follow the rules in `references/guidelines.md`.

WHEN following Standard, Monorepo, or Migration THEN Phase 0 stubs are your starting point.
WHEN following Fast Path THEN existing production code and targeted regression tests are your starting point.

You SHALL work through one function or logical unit at a time.
For each unit, you SHALL complete all three sub-phases before moving to the next unit.

### Phase 1.1 — RED: Write a failing test

WHEN following Standard THEN you SHALL replace the `todo!()` body in one test stub with real assertions and setup.
WHEN following Fast Path THEN you SHALL add or update one targeted regression or behavior test in an existing test module or existing test file within the crate.

The test SHALL call the function or behavior under test and assert the expected behavior.
You SHALL run `cargo test` and confirm the test fails (red).
WHEN the test fails for the wrong reason (compilation error, wrong assertion, panic in unrelated code) THEN you SHALL fix the test before proceeding.

You SHALL target one test per cycle — do not fill in multiple tests at once.

```bash
cargo test <test_name> 2>&1 | tail -20
# Expected: FAILED (the implementation is still incomplete or wrong)
```

You SHALL output the block below as evidence. You SHALL NOT skip this block.

> **Required output — RED**
>
>     #### RED — `<test_name>`
>     <paste cargo test failure output>

### Phase 1.2 — GREEN: Write the minimal implementation to pass

WHEN following Standard THEN you SHALL replace the `todo!()` in the function under test with the simplest code that makes the red test pass.
WHEN following Fast Path THEN you SHALL modify the existing implementation — and only add local private helpers inside existing production files when needed — with the simplest code that makes the red test pass.

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

### Phase 1.3 — REFACTOR: Improve under green

WHEN the implementation or test can be simplified, deduplicated, or clarified THEN you SHALL refactor now.
You SHALL NOT change observable behavior during refactor — all tests SHALL remain green.
You SHALL run `cargo test` after every refactor pass and confirm all tests still pass.
WHEN no meaningful refactor is needed THEN you SHALL note "No refactor needed" and proceed.

You SHALL output the block below as evidence. You SHALL NOT skip this block.

> **Required output — REFACTOR**
>
>     #### REFACTOR — `<function_or_unit_name>`
>     <description of changes, or "No refactor needed.">
>     <paste cargo test output confirming all tests still pass>

After completing 1.1 → 1.2 → 1.3 for one unit, you SHALL loop back to Phase 1.1 for the next unit.
WHEN following Standard, Monorepo, or Migration THEN you SHALL continue until all `todo!()` bodies in both tests and functions are replaced.
WHEN following Fast Path THEN you SHALL continue until the targeted behavior and any newly-discovered edge cases in scope are covered and passing.

### Phase 1 rules (apply across all sub-phases)

You SHALL NOT use any pattern listed in `references/banned-patterns.md`.
WHEN a banned pattern has a specific escape hatch (for example `// INVARIANT:`) THEN you SHALL use that escape hatch.
WHEN no pattern-specific escape hatch exists and the pattern must remain THEN you SHALL add `// ALLOW: <reason>` on the same line.

Unsafe constructs are NOT eligible for `// ALLOW:` or `// SAFETY:` escape hatches under this skill.

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

### Phase 1 — Test coverage rule

You SHALL write at minimum one happy-path and one error/edge-case test per new or touched public function in task scope.
You SHALL exercise every error variant introduced or touched in task scope.
WHEN an introduced or touched error variant exists but no test triggers it THEN you SHALL add a test that does before Phase 1 is complete.

### Phase 2 — Verify

You SHALL run the verification script:

```bash
<skills-file-root>/scripts/verify.sh [--dir <path>]
```

You SHOULD have `python3` installed before Phase 2 so the parser-aware banned-family checks can run with full coverage.
WHEN `verify.sh` is unavailable THEN you SHALL run the checks from `references/verify-manual.md`.
The scripted and manual paths SHALL enforce the same documented banned-pattern inventory plus installation, build, lint, and test checks.
You SHALL paste the output of all Phase 2 commands as evidence.

You SHALL output the block below as evidence. You SHALL NOT skip this block.

> **Required output — Phase 2 Verification**
>
>     ### Phase 2 — Verification Evidence
>
>     <paste full verify.sh output or manual check output>

`verify.sh` now includes installation checks (Phase 2.0) that confirm:
- `banned_family.rs` test harness is installed in a crate's `tests/` directory.
- `.github/workflows/ci.yml` is present.
- `.github/scripts/detect_rust_workspaces.py`, `.github/scripts/verify.sh`, and `.github/scripts/workspace-members.sh` are present.
- Clippy lint config is present in the root `Cargo.toml`.
- All workspace member crates inherit lints via `[lints] workspace = true`.

IF `python3` is unavailable THEN the parser-aware subset of banned-family checks is not fully verifiable; `verify.sh` SHALL warn and skip those checks rather than using brittle regex-based approximations.
WHEN `rg` or `git` is available THEN the verifier uses them to honor ignored Rust paths during file discovery; otherwise it falls back to a best-effort recursive walk.

IF installation checks report missing artifacts THEN you SHALL run `scaffold.sh --all` first.
IF any checks fail THEN you SHALL fix the issues and re-run verification.

### Phase 3 — Completion checklist

You SHALL confirm every item below and paste the checklist with `[x]` marks and command outputs as evidence.

- [ ] You SHALL confirm workflow-entry evidence exists: Phase 0 Stub Review or Fast Path Qualification.
- [ ] You SHALL confirm Round −1 observations were addressed or documented as acceptable.
- [ ] You SHALL confirm TDD cycle was followed: each unit has RED (failing test) → GREEN (minimal pass) → REFACTOR evidence.
- [ ] You SHALL confirm all banned patterns are fixed — scan clean.
- [ ] You SHALL confirm no oversized files exist, or justification is provided.
- [ ] You SHALL confirm `cargo build` passes.
- [ ] You SHALL confirm `cargo fmt --check` passes.
- [ ] You SHALL confirm `cargo clippy --workspace --all-targets -- -D warnings` passes.
- [ ] You SHALL confirm `cargo test` passes.
- [ ] You SHALL confirm no `todo!()` remains.
- [ ] You SHALL confirm new or touched functions in task scope have happy-path and error/edge-case coverage.
- [ ] You SHALL confirm every introduced or touched error variant in task scope is exercised by at least one test.
- [ ] You SHALL confirm doc comments are complete on all new or touched public items with Examples.

You SHALL output the checklist above with `[x]` marks and supporting evidence as a single block.
You SHALL NOT skip this block or return a null/empty completion message.

> **Required output — Phase 3 Checklist**
>
>     ### Phase 3 — Completion Checklist
>
>     - [x] Workflow-entry evidence recorded: <Phase 0 Stub Review above / Fast Path Qualification above>.
>     - [x] Round −1 observations addressed: <brief note or "see Round −1">.
>     - [x] TDD cycle followed: RED/GREEN/REFACTOR evidence above for each unit.
>     - [x] Banned patterns clean: verify.sh scan above.
>     - [x] No oversized files: verify.sh complexity check above.
>     - [x] `cargo build` passes.
>     - [x] `cargo fmt --check` passes.
>     - [x] `cargo clippy --workspace --all-targets -- -D warnings` passes.
>     - [x] `cargo test` passes.
>     - [x] No `todo!()` remains.
>     - [x] New or touched functions in scope have happy-path and error/edge-case coverage.
>     - [x] Every introduced or touched error variant in scope is exercised by at least one test.
>     - [x] Doc comments complete on all new or touched public items with Examples.

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
>     **Round −1 revisit:**
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
| `--ci` | Copy `.github/workflows/ci.yml`, `.github/scripts/detect_rust_workspaces.py`, `.github/scripts/verify.sh`, and `.github/scripts/workspace-members.sh` |
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
| `scripts/verify.sh` | Run all Phase 2 checks: installation checks, banned scan, fmt, clippy, test |
| `scripts/scaffold.sh` | Bootstrap lint config, test harness, and CI/verifier stack into a workspace |
| `scripts/workspace-members.sh` | Shared helper used by `verify.sh`, `scaffold.sh`, and scaffolded CI verifier |

## Asset index

| Asset | Used by |
|---|---|
| `assets/clippy-lints.toml` | `scaffold.sh --clippy` — workspace lint snippet |
| `assets/banned_family.rs` | `scaffold.sh --banned-test` — test harness |
| `assets/ci.yml` | `scaffold.sh --ci` — GitHub Actions workflow |
| `assets/detect_rust_workspaces.py` | `scaffold.sh --ci` — CI workspace detector |
