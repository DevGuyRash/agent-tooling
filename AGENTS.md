# MANDATORY Rust Coding Guidelines

You SHALL prioritize idiomatic Rust, memory safety, clarity, and maintainability without imposing a new architecture if an existing one is already in use.

---

## ROUND −1: Fresh Eyes (BEFORE Any Structured Analysis)

Before applying any checklists or structured analysis, read through the entire change and record your unfiltered observations. This phase captures intuitive signals that mechanical passes often miss. Do not consult the checklists in this document during this round. Simply read the code and write down whatever you notice.

---

## PHASE 0: Planning and Stubs (BEFORE Writing Implementation)

You SHALL complete Phase 0 before writing any implementation code. Phase 0 produces **compilable stub files** that define the API contract.

### 0.1 Requirement capture

- [ ] You SHALL write a brief summary (2–5 sentences) of what you are implementing and why.
- [ ] You SHALL list the files you expect to create or modify.
- [ ] You SHALL list any new dependencies you expect to add (with justification).

### 0.2 Write stub files with doc comments

You SHALL create actual `.rs` files containing:

- [ ] **Module-level documentation** (`//!`) explaining the module's purpose.
- [ ] **Type definitions** (structs, enums) with `///` doc comments and fields, but no method implementations yet.
- [ ] **Function signatures** with `///` doc comments and `todo!()` bodies.
- [ ] **Error types** if the module returns `Result`.

Each doc comment SHALL include:

- **Purpose**: One-line description.
- **Arguments**: Each parameter's meaning and constraints.
- **Returns**: What the function returns, including error conditions.
- **Panics**: Document if `todo!()` will be replaced with panic-possible code (should be rare).
- **Examples**: At least one usage example for public APIs.

**Stub template**:

```rust
//! Brief module description.
//!
//! # Overview
//! Longer explanation of what this module does and why.

use std::path::Path;

/// Represents a validated configuration.
///
/// # Invariants
/// - `timeout_ms` is always > 0.
/// - `name` is non-empty.
#[derive(Debug, Clone)]
pub struct Config {
    /// The operation timeout in milliseconds. Must be > 0.
    pub timeout_ms: u64,
    /// The configuration name. Must be non-empty.
    pub name: String,
}

/// Errors that can occur when loading configuration.
#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    /// The configuration file was not found.
    #[error("configuration file not found: {path}")]
    NotFound { path: String },
    /// The configuration file contained invalid TOML.
    #[error("invalid configuration syntax: {reason}")]
    InvalidSyntax { reason: String },
}

/// Loads configuration from a file.
///
/// # Arguments
/// * `path` - Path to the configuration file. Must exist and be readable.
///
/// # Returns
/// * `Ok(Config)` - The parsed configuration.
/// * `Err(ConfigError::NotFound)` - If the file does not exist.
/// * `Err(ConfigError::InvalidSyntax)` - If the file is not valid TOML.
///
/// # Examples
/// ```no_run
/// # use std::path::Path;
/// # #[derive(Debug)]
/// # struct Config { timeout_ms: u64, name: String }
/// # #[derive(Debug)]
/// # struct ConfigError;
/// # fn load_config(_path: &Path) -> Result<Config, ConfigError> {
/// #     Ok(Config { timeout_ms: 1, name: "example".to_string() })
/// # }
/// let config = load_config(Path::new("config.toml"))?;
/// assert!(config.timeout_ms > 0);
/// # Ok::<(), ConfigError>(())
/// ```
pub fn load_config(path: &Path) -> Result<Config, ConfigError> {
    todo!("Phase 1: implement load_config")
}
```

### 0.3 Write test stubs

You SHALL create test functions with descriptive names and `todo!()` bodies:

- [ ] At least one happy-path test.
- [ ] At least one error/edge-case test.
- [ ] Each test name SHALL describe what it verifies.

**Test stub template**:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn load_config_returns_valid_config_for_well_formed_file() {
        todo!("Phase 1: create temp file with valid TOML, call load_config, assert fields")
    }

    #[test]
    fn load_config_returns_not_found_error_for_missing_file() {
        todo!("Phase 1: call load_config with nonexistent path, assert NotFound error")
    }

    #[test]
    fn load_config_returns_invalid_syntax_error_for_malformed_toml() {
        todo!("Phase 1: create temp file with invalid TOML, assert InvalidSyntax error")
    }
}
```

### 0.4 Verify stubs compile

- [ ] You SHALL run `cargo check` and confirm the stubs compile (with `todo!()` warnings acceptable).
- [ ] You SHALL NOT proceed to Phase 0.5 until stubs compile.

**Verification command**:

```bash
cargo check && echo "✓ Stubs compile" || echo "BLOCKED: Fix compilation errors before Phase 0.5"
```

### 0.5 Stub review checkpoint (MANDATORY)

Before writing Phase 1 implementation code:

- [ ] You SHALL present the stubs and doc comments for review.
- [ ] You SHALL list any assumptions made in stubs (types, error variants, module boundaries).
- [ ] IF any uncertainty remains, THEN you SHALL ask targeted questions and WAIT for answers.
- [ ] You SHALL NOT proceed to Phase 1 until the stub review is approved.

**Evidence required**: You SHALL paste:

1. The requirement summary.
2. The complete stub files (or diffs if modifying existing files).
3. The `cargo check` output showing successful compilation.
4. The stub review questions (if any) and the approval decision.

---

## PHASE 1: Implementation

You SHALL implement code only after Phase 0 is complete.

---

## 1) Compatibility and precedence

- You SHALL treat existing repository conventions (layout, naming, tooling, lint settings, CI rules, runtime choices) as authoritative.
- IF this document conflicts with an explicit repository rule, THEN you SHALL follow the repository rule.
- IF no explicit repository rule exists, THEN you SHALL follow this document.
- You SHALL keep changes scoped to the task.
- You SHALL NOT perform incidental refactors (mass renames, reorganizations, formatting churn) unless they are required to implement or safely test the change.
- IF you introduce a new pattern (error type, async runtime usage pattern, module layout pattern), THEN you SHALL apply it consistently within the touched area.
- IF an existing local pattern exists, THEN you SHALL follow the existing local pattern.

---

## 2) Toolchain, edition, and stability

- You SHALL use the repository's pinned toolchain and MSRV (if defined).
- IF the repository does not define an MSRV, THEN you SHALL NOT use language/library features newer than 6 months without explicit approval.
- You SHALL target stable Rust by default.
- You SHALL NOT introduce nightly-only features unless the repository already requires nightly or the change is explicitly approved and documented.
- IF you add a crate/package, THEN you SHALL match the repository's edition and common `Cargo.toml` conventions.

---

## 3) Idiomatic Rust (with specific rules)

### 3.1 Banned patterns

The following patterns are BANNED in non-test code. IF you write any of these, THEN you SHALL refactor before proceeding.

- IF you intentionally keep a banned pattern, THEN you SHALL add a same-line comment `// ALLOW: <reason>`.

| Pattern                                                                    | Reason                         | Fix                                                                   |
| -------------------------------------------------------------------------- | ------------------------------ | --------------------------------------------------------------------- |
| `.unwrap*()` without invariant comment                                     | Silent panic                   | Use `?`, `if let`, `match`, or add `// INVARIANT: ...` comment        |
| `.expect*()` without invariant comment                                     | Silent panic                   | Use `?`, `if let`, `match`, or add `// INVARIANT: ...` comment        |
| `panic!()` in non-test code                                                | Unrecoverable                  | Return `Result` or `Option`                                           |
| `unimplemented!()` in non-test code                                        | Placeholder                    | Implement or delete                                                   |
| `todo!()` outside tests after Phase 0                                      | Placeholder                    | Implement before Phase 2; Phase 2 scan MUST be empty                  |
| `unreachable!()` without invariant comment                                 | Risky assumption               | Refactor or add `// INVARIANT: ...` comment                           |
| `std::process::exit(...)` outside entrypoints                              | Hidden control flow            | Return `Result` and map exit codes at boundary                        |
| `.map(\|x\| x.clone())`                                                    | Non-idiomatic                  | Use `.cloned()`                                                       |
| `.map(\|x\| x.to_owned())`                                                 | Non-idiomatic                  | Use `.cloned()` or `.map(ToOwned::to_owned)` only when types differ   |
| `.iter().map(...).collect::<Vec<_>>()` when result is immediately iterated | Unnecessary allocation         | Chain iterators directly                                              |
| `.into_iter().collect::<Vec<_>>()` on a `Vec`                              | Unnecessary allocation         | Remove; already a `Vec`                                               |
| `.iter().count()` with no filter/map                                       | O(n)                           | Use `.len()`                                                          |
| `.iter().next()` on a slice/`Vec`                                          | Verbose                        | Use `.first()`                                                        |
| `for i in 0..x.len()` (index loop)                                         | Often non-idiomatic            | Use iterators/enumerate; add `// ALLOW:` only if indexing is required |
| `if x == true` / `if x == false`                                           | Verbose                        | Use `if x` / `if !x`                                                  |
| `if x != true` / `if x != false`                                           | Verbose                        | Use `if !x` / `if x`                                                  |
| `format!("{}", x)` when `x` is `&str` or `String`                          | Unnecessary allocation         | Use `x` or `x.to_string()`                                            |
| `String::from("")` or `"".to_string()`                                     | Unnecessary allocation         | Use `String::new()`                                                   |
| `&String` in function parameters                                           | Unnecessary indirection        | Use `&str`                                                            |
| `&Vec<T>` in function parameters                                           | Unnecessary indirection        | Use `&[T]`                                                            |
| `&Box<T>` anywhere                                                         | Unnecessary indirection        | Use `&T`                                                              |
| `use crate::*;` / `use super::*;` outside tests                            | Glob import hides dependencies | Import explicitly; allow only with `// ALLOW:`                        |
| `use some::path::*;` outside tests                                         | Glob import hides dependencies | Import explicitly; allow only with `// ALLOW:`                        |
| `Box<dyn std::error::Error>` in `pub` APIs                                 | Opaque errors                  | Use a structured error enum                                           |
| `anyhow::Result` / `anyhow::Error` in `pub` APIs                           | Opaque errors                  | Use a structured error enum; keep `anyhow` at app boundary            |
| `impl Into<X>` when only one concrete type is passed                       | Over-generic                   | Use concrete type                                                     |
| `impl AsRef<X>` when only one concrete type is passed                      | Over-generic                   | Use concrete type                                                     |
| `dbg!()` in non-test code                                                  | Debug artifact                 | Remove                                                                |
| `println!()` or `eprintln!()` for logging                                  | Unstructured logging           | Use tracing/log crate OR remove                                       |
| `static mut`                                                               | Unsound global mutability      | Use `OnceLock`/`LazyLock` and safe synchronization                    |
| `unsafe impl Send` / `unsafe impl Sync`                                    | Easy to get wrong              | Avoid; if required, add `// SAFETY:` and tests                        |
| `Command::new("sh").arg("-c")` (or `bash`, `cmd /C`)                       | Shell injection risk           | Build argv explicitly; avoid shells                                   |
| `// TODO` without issue reference                                          | Orphaned work                  | Add issue reference or complete the work                              |
| `#[allow(...)]` without justification comment                              | Unexplained suppression        | Add `// Reason: ...` comment                                          |

### 3.2 Required idioms

- You SHALL use `?` for error propagation when the function returns `Result` or `Option`.
- You SHALL use `if let` when only one variant is handled and the other is ignored.
- You SHALL use `match` when all variants require explicit handling.
- You SHALL use iterators instead of index-based for loops unless index access is required.
- You SHALL use `Option<T>` for "may be absent" values instead of sentinel values (empty strings, -1, null pointers).
- You SHALL use enums for "one of N" values instead of strings or magic numbers.

---

## 4) Formatting and lint posture

- You SHALL keep code `rustfmt`-clean according to the repository's formatting configuration.
- IF the repository has a Clippy/lint policy, THEN you SHALL follow it.
- IF there is no explicit lint policy, THEN you SHALL ensure `cargo clippy` produces no warnings on touched files.
- You SHALL NOT leave debug artifacts in production code:
  - `dbg!()` calls
  - `println!()` or `eprintln!()` for debugging
  - Commented-out code blocks longer than 3 lines
  - Dead/unreachable code
- IF you suppress a lint with `#[allow(...)]`, THEN you SHALL:
  - Scope it to the narrowest item (not the whole crate)
  - Add a same-line comment `// Reason: ...` on the `#[allow(...)]` line
  - Remove the suppression when the underlying reason no longer applies

---

## 5) Modules, files, and structure

- You SHALL structure code to support testing and reuse.
- IF a crate has binaries (`src/main.rs` or `src/bin/*.rs`), THEN those entrypoints SHALL contain only:
  - Argument parsing
  - Dependency wiring
  - A call into library code
  - Error handling/exit code mapping
- You SHALL avoid monolithic files:
  - IF a file grows large enough that navigating or understanding it becomes difficult, THEN you SHALL split it into focused modules unless doing so reduces clarity.
  - IF a file mixes unrelated concerns (e.g., CLI parsing + business logic + I/O), THEN you SHALL split by concern.
- You SHALL separate I/O and side effects from pure logic when the file is complex enough that testability or readability would benefit from separation.
- IF you create shared helpers, THEN you SHALL only do so when reuse is real (2+ call sites exist).

---

## 6) Naming, visibility, and API discipline

- You SHALL follow Rust naming conventions:
  - `UpperCamelCase` for types, traits, enum variants
  - `snake_case` for functions, methods, variables, modules
  - `SCREAMING_SNAKE_CASE` for constants and statics
- You SHALL NOT make items `pub` by default.
- IF an item is `pub`, THEN you SHALL:
  - Write a doc comment explaining its purpose
  - Add at least one test exercising it
  - Treat it as a contract (avoid breaking changes)
- You SHALL prefer "make invalid states unrepresentable":
  - IF a value has domain rules, THEN you SHALL model it with a type (newtype, enum, validated struct) rather than scattered runtime checks.

---

## 7) Ownership, borrowing, lifetimes, and mutability

- You SHALL make ownership explicit at boundaries (function signatures and struct fields).
- You SHALL prefer borrowing over cloning:
  - IF you do not need ownership, THEN you SHALL accept references (`&T`, `&str`, `&[T]`, `&Path`).
  - IF you need ownership, THEN you SHALL take ownership (`T`, `String`, `Vec<T>`, `PathBuf`) and document why in a comment.
- IF you clone, THEN you SHALL ensure it meets one of:
  - The type is `Copy`, OR
  - The type is small and cheap to clone (< 64 bytes, no heap allocation), OR
  - You add a comment explaining why cloning is necessary.
- You SHALL minimize mutability:
  - You SHALL declare variables with `let` (immutable) by default.
  - IF mutation is required, THEN you SHALL:
    - Use `let mut` and keep the mutable scope as small as possible.
    - Not pass `&mut` through more than 2 function call levels without justification.
- You SHALL avoid unnecessary heap allocation:
  - IF a value can live on the stack and remain simple, THEN you SHALL keep it on the stack.
- You SHALL use iterators/slices to avoid allocating intermediate vectors.

---

## 8) Traits, generics, abstraction budget, and design patterns

- You SHALL keep abstraction proportional to need.
- You SHALL NOT use generic parameters when only one concrete type is ever passed.
- You SHALL NOT introduce trait objects (`dyn Trait`) unless there are 2+ concrete implementations.
- You SHALL NOT introduce trait hierarchies unless there is demonstrated need.
- IF you use generics, THEN:
  - The generic parameter SHALL appear in at least 2 instantiations in the codebase, OR
  - The function is implementing a standard trait (e.g., `Iterator`, `From`).
- IF you use `impl Trait` in argument position, THEN only one concrete type SHALL be passed at each call site; otherwise use a generic parameter.

### 8.1 Design patterns: when they help vs. add ceremony

- Design patterns exist to solve recurring problems — use them when the problem exists, not preemptively.
- You SHALL NOT introduce patterns (Factory, Builder, Strategy, Visitor, etc.) unless the flexibility they provide is actually exercised in the codebase.
- IF you introduce a pattern, THEN you SHALL document in a comment why the pattern is warranted and what variation it enables.
- Prefer straightforward code over pattern-heavy code. A direct function call is clearer than a strategy pattern with one implementation.
- Be especially wary of patterns that add indirection (dependency injection frameworks, service locators, abstract factories) when simple constructor arguments would suffice.

---

## 9) Hermetic code and side-effect isolation

- You SHALL structure code to be testable in isolation.
- You SHALL separate pure logic from side effects (I/O, network, file system, time, randomness).
- Pure functions (those with no side effects and deterministic outputs for given inputs) are preferred for core business logic.
- IF a function performs I/O or has side effects, THEN:
  - The side-effecting operations SHALL be injected as dependencies (function arguments, trait implementations) rather than hardcoded.
  - The function name or documentation SHALL make the side effects obvious.
- You SHALL use dependency injection to enable testing with mocks/fakes, but prefer simple function arguments over frameworks.
- IF you use global state or singletons, THEN you SHALL ensure they are resettable for testing.

---

## 10) Error handling, panics, and diagnostics

- You SHALL use `Result<T, E>` for recoverable failures.
- You SHALL use `Option<T>` for "may be absent" values.
- You SHALL propagate errors with `?` when appropriate.
- You SHALL provide actionable context at module boundaries.
- Error messages SHALL follow this structure (in this order):
  1. What operation failed
  2. Why it failed (the condition)
  3. What the user can do next (action)
- IF an error is user-facing, THEN the message SHALL be:
  - a single sentence,
  - lower-case (except proper nouns),
  - free of debug dumps,
  - free of `{:?}`/`{:#?}` output.
- Error messages SHALL NOT leak secrets, credentials, or PII.
- You SHALL NOT use panics for normal control flow.
- You SHALL NOT use `.unwrap*()` or `.expect*()` in non-test code except when ALL of the following are true:
  - An invariant guarantees the value exists.
  - You add a same-line comment: `// INVARIANT: <explanation>`.
  - You use `.expect("descriptive message")` rather than `.unwrap()`.
- IF you are writing a library, THEN you SHALL expose a structured error type.
- IF you are writing an application/CLI, THEN you SHALL:
  - Map errors to appropriate exit codes.
  - Print user-friendly error messages to stderr.

---

## 11) Async and I/O concurrency

### 11.1 When to use async

- You SHALL choose async intentionally.
- IF the workload involves fewer than 10 concurrent I/O operations, THEN you SHALL use synchronous code.
- IF the workload involves 10+ concurrent I/O operations, THEN you MAY use async.
- IF the repository already uses an async runtime, THEN you SHALL use that runtime.
- IF the repository does not use an async runtime, THEN you SHALL NOT introduce one without explicit approval.

### 11.2 Blocking inside async

- You SHALL NOT block an async executor thread.
- IF you need to perform blocking I/O or CPU-heavy work (> 1ms) from async code, THEN you SHALL use `spawn_blocking` or equivalent.
- You SHALL NOT call `block_on` from within an executor thread.

### 11.3 Structured concurrency

- You SHALL keep task handles and await/join them.
- IF you spawn a detached task, THEN you SHALL:
  - Add a comment explaining why detaching is safe.
  - Document how the task terminates.
- IF multiple tasks are spawned for one operation, THEN you SHALL:
  - Collect and surface all errors.
  - Propagate cancellation to all tasks.
  - Release resources deterministically.

### 11.4 Cancellation and timeouts

- IF an async operation can hang (network calls, external processes), THEN you SHALL apply a timeout.
- IF cancellation can leave partial state, THEN you SHALL:
  - Make updates atomic (commit at end), OR
  - Record/return enough information to recover, OR
  - Implement compensating cleanup.

### 11.5 Bounded concurrency

- You SHALL NOT spawn tasks in an unbounded loop.
- IF you process a collection with concurrent tasks, THEN you SHALL cap concurrency with a semaphore, bounded channel, or worker pool.
- The default concurrency cap SHALL be min(num_cpus, collection_size, 32) unless the repository specifies otherwise.

### 11.6 Locks across await

- You SHALL NOT hold `std::sync::Mutex` or `std::sync::RwLock` across `.await`.
- IF you must hold a lock across `.await`, THEN you SHALL:
  - Use an async-aware lock (`tokio::sync::Mutex`, etc.).
  - Add a comment explaining why.
  - Verify no deadlock is possible.

---

## 12) CPU parallelism, threads, and data-parallel patterns

- You SHALL choose parallelism intentionally.
- IF the workload is CPU-bound AND processes a substantial number of items AND each item requires meaningful computation, THEN you MAY consider parallelism.
- IF the workload is small enough that the overhead of parallelism would dominate, THEN you SHALL use sequential code.
- You SHALL keep parallel code deterministic:
  - IF output ordering matters, THEN you SHALL sort results or use ordered parallel iteration.
- You SHALL avoid shared mutable state in parallel code:
  - Prefer per-thread locals + reduction/merge.
  - Prefer immutable shared data (`Arc<T>`).

---

## 13) Shared state, synchronization, and caches

- You SHALL minimize shared mutable state.
- IF shared state is required, THEN you SHALL:
  - Keep critical sections brief and focused.
  - Document lock ordering if multiple locks exist.
  - Not hold locks during I/O, `.await`, or heavy CPU work.
- You SHALL choose the simplest synchronization primitive:
  - `Mutex` for exclusive access.
  - `RwLock` only when reads dominate (10:1 ratio or higher).
  - Atomics only for single values with well-defined semantics.
- IF you use atomics, THEN you SHALL:
  - Use `Ordering::SeqCst` unless you can prove a weaker ordering is correct.
  - Add a comment explaining the ordering choice.
- IF you introduce caching, THEN you SHALL:
  - Define: cache key, value type, max size, eviction policy.
  - Ensure cache entries are immutable once stored.
  - Prefer `Arc<V>` for shared cached values.
  - Ensure the cache is resettable for testing.

---

## 14) Determinism and stable behavior

- You SHALL ensure user-visible outputs are stable.
- IF iteration order affects output, THEN you SHALL use `BTreeMap`/`BTreeSet` or sort before output.
- IF you use `HashMap`/`HashSet`, THEN you SHALL sort keys before any user-visible output.
- IF concurrency affects output order, THEN you SHALL:
  - Document the ordering contract (input order vs. completion order).
  - Implement the ordering explicitly.

---

## 15) Testing and regression coverage

- You SHALL add tests for new behavior and bug fixes.
- Tests SHALL be hermetic and deterministic:
  - Use temp dirs for file operations.
  - Use fixed seeds for random values.
  - Avoid timing-sensitive sleeps.
- You SHALL cover at least:
  - One happy-path test.
  - One error/edge-case test.
- IF output formats matter (CLI output, file generation, serialization), THEN you SHALL add golden/snapshot tests.

---

## 16) Performance and complexity

- You SHALL reason about algorithmic complexity for non-trivial code paths.
- IF a loop processes user-sized input, THEN you SHALL add a comment near the loop:

  ```rust
  // O(n) where n = number of items (expected: 10–1000)
  ```

- You SHALL avoid accidental O(n²) patterns:
  - No `Vec::contains()` inside loops (use `HashSet`).
  - No nested loops over the same collection (use indices or maps).
  - No repeated string concatenation (use `String::with_capacity()` or `format!()`).
  - No repeated parsing/compilation (hoist outside loops).

---

## 17) Dependencies and feature discipline

- You SHALL keep dependencies minimal.
- IF you add a dependency, THEN you SHALL:
  - Justify why it is needed (not just convenience).
  - Use `default-features = false` when possible.
  - Enable only required features.
- You SHALL NOT add a dependency for functionality that is trivial to implement (< 20 lines).

---

## 18) Unsafe code, FFI, and soundness

- You SHALL avoid `unsafe` by default.
- IF `unsafe` is required, THEN you SHALL:
  - Add a `// SAFETY: ...` comment immediately before the `unsafe` block.
  - Keep the unsafe block minimal and focused.
  - Provide a safe wrapper API.
  - Add tests exercising the unsafe boundary.

---

## 19) Security and robustness baseline

- You SHALL treat all external input as untrusted.
- You SHALL validate inputs and fail with actionable errors.
- You SHALL NOT leak secrets via logs, error strings, or debug output.
- IF you handle credentials, tokens, or PII, THEN you SHALL:
  - Redact values in logs/errors.
  - Exclude sensitive fields from `Debug` implementations.

---

## PHASE 2: Post-Write Verification

After completing implementation, you SHALL run the following verification checks and report results.

### 2.1 Banned pattern scan

Run the following commands and report the output. IF any patterns are found, THEN you SHALL fix them before proceeding.

```bash
# Panic-inducing patterns (excluding tests)
rg '\.unwrap(_|\()' --type rust -g '!*test*' | rg -v '// INVARIANT:' || echo "✓ No bare unwrap*()"
rg '\.expect(_|\()' --type rust -g '!*test*' | rg -v '// INVARIANT:' || echo "✓ No bare expect*()"
rg 'panic!\(' --type rust -g '!*test*' || echo "✓ No panic!()"
rg 'unimplemented!\(' --type rust -g '!*test*' && echo "ERROR: unimplemented!() found" || echo "✓ No unimplemented!() remaining"
rg 'unreachable!\(' --type rust -g '!*test*' | rg -v '// INVARIANT:' || echo "✓ No bare unreachable!()"

# Process control flow (should be at entrypoints only)
rg 'std::process::exit\(' --type rust -g '!*test*' -g '!**/src/main.rs' -g '!**/src/bin/*.rs' || echo "✓ No std::process::exit() outside entrypoints"

# Placeholder scans
rg 'todo!\(' --type rust && echo "ERROR: Unimplemented todo!() found" || echo "✓ No todo!() remaining"

# Non-idiomatic patterns
rg '\.map\(\|.*\|.*\.clone\(\)\)' --type rust || echo "✓ No .map(|x| x.clone())"
rg '\.map\(\|.*\|.*\.to_owned\(\)\)' --type rust || echo "✓ No .map(|x| x.to_owned())"
rg '\.iter\(\)\.count\(\)' --type rust || echo "✓ No .iter().count()"
rg '\.iter\(\)\.next\(\)' --type rust || echo "✓ No .iter().next()"
rg 'for\s+\w+\s+in\s+0\.\.[^\n]*\.len\(\)' --type rust || echo "✓ No index loops"
rg '==\s*true|==\s*false|!=\s*true|!=\s*false' --type rust || echo "✓ No verbose bool comparisons"

# Formatting/debug artifacts
rg 'dbg!\(' --type rust -g '!*test*' || echo "✓ No dbg!()"
rg 'println!\(' --type rust -g '!*test*' -g '!**/src/main.rs' -g '!**/src/bin/*.rs' || echo "✓ No println!() outside entrypoints"
rg 'eprintln!\(' --type rust -g '!*test*' -g '!**/src/main.rs' -g '!**/src/bin/*.rs' || echo "✓ No eprintln!() outside entrypoints"
# If ripgrep is unavailable, fallback (fixed-string search; excludes entrypoints by path):
# find . -name '*.rs' -not -path '*/src/main.rs' -not -path '*/src/bin/*' -not -path '*test*' -exec grep -nF 'println!(' {} + || echo "✓ No println!() outside entrypoints"
# find . -name '*.rs' -not -path '*/src/main.rs' -not -path '*/src/bin/*' -not -path '*test*' -exec grep -nF 'eprintln!(' {} + || echo "✓ No eprintln!() outside entrypoints"

# Imports (glob imports banned outside tests)
rg '^\s*use\s+(crate|super)::\*;' --type rust -g '!*test*' || echo "✓ No use crate::* or use super::*"
rg '^\s*use\s+[^;]+::\*;' --type rust -g '!*test*' | rg -v 'prelude' || echo "✓ No glob imports outside tests"
# If ripgrep is unavailable, fallback:
# find . \( -path '*/.git' -o -path '*/target' -o -path '*/node_modules' \) -prune -o -name '*.rs' -not -path '*test*' -exec grep -nE '^[[:space:]]*use[[:space:]]+(crate|super)::\*;' {} + || echo "✓ No use crate::* or use super::*"
# find . \( -path '*/.git' -o -path '*/target' -o -path '*/node_modules' \) -prune -o -name '*.rs' -not -path '*test*' -exec grep -nE '^[[:space:]]*use[[:space:]]+[^;]+::\*;' {} + | grep -v 'prelude' || echo "✓ No glob imports outside tests"

# Parameter anti-patterns
rg 'fn.*\(&String' --type rust || echo "✓ No &String parameters"
rg 'fn.*\(&Vec<' --type rust || echo "✓ No &Vec<T> parameters"
rg 'fn.*\(&Box<' --type rust || echo "✓ No &Box<T> parameters"

# Opaque errors in public APIs
rg 'pub\s+fn[^\n]*->\s*anyhow::Result' --type rust || echo "✓ No anyhow::Result in pub API"
rg 'pub\s+fn[^\n]*->\s*Result<[^>]*,\s*anyhow::Error\s*>' --type rust || echo "✓ No anyhow::Error in pub API"
rg 'pub\s+fn[^\n]*->\s*Result<[^>]*,\s*Box<dyn\s+std::error::Error' --type rust || echo "✓ No Box<dyn Error> in pub API"

# Shell injection risk
rg 'Command::new\(\s*"(sh|bash|cmd)"\s*\)\s*\.arg\(\s*"(-c|/C)"\s*\)' --type rust || echo "✓ No shell invocation via Command"

# Empty string allocation
rg 'String::from\(""\)' --type rust || echo "✓ No String::from(\"\")"
rg '"".to_string\(\)' --type rust || echo "✓ No \"\".to_string()"

# Untracked TODOs
rg 'TODO' --type rust | rg -v '#[0-9]+' | rg -v 'https?://' || echo "✓ No orphan TODOs"
# If ripgrep is unavailable, fallback:
# find . \( -path '*/.git' -o -path '*/target' -o -path '*/node_modules' \) -prune -o -name '*.rs' -exec grep -n 'TODO' {} + | grep -E -v '#[0-9]+' | grep -E -v 'https?://' || echo "✓ No orphan TODOs"

# Unjustified allows
rg '#\[allow\(' --type rust | rg -v '// Reason:' || echo "✓ All #[allow] have justification"
# If ripgrep is unavailable, fallback:
# find . \( -path '*/.git' -o -path '*/target' -o -path '*/node_modules' \) -prune -o -name '*.rs' -exec grep -nE '#\[allow\(' {} + | grep -v '// Reason:' || echo "✓ All #[allow] have justification"
```

### 2.2 Complexity check

Run the following and report any issues. Adjust the line threshold based on project conventions — the default of 300 is a starting point, not a hard rule:

```bash
# Files that may be disproportionately large (adjust threshold as appropriate for your project)
FILE_SIZE_THRESHOLD=${FILE_SIZE_THRESHOLD:-300}
find . -name '*.rs' -exec wc -l {} \; | awk -v threshold="$FILE_SIZE_THRESHOLD" '$1 > threshold {print}' | tee /dev/stderr | rg -q '.' && echo "WARN: Large files found — review for splitting" || echo "No notably large files"
# If ripgrep is unavailable, fallback:
# find . -name '*.rs' -exec wc -l {} \; | awk -v threshold="$FILE_SIZE_THRESHOLD" '$1 > threshold {print}' | tee /dev/stderr | grep -q . && echo "WARN: Large files found — review for splitting" || echo "No notably large files"

# Functions that may benefit from extraction (use judgment, not rigid thresholds)
rg -n '^(\s*)fn ' --type rust | head -50
# NOTE: This is a sample-only list. Use clippy/lints and review diffs to identify functions that warrant splitting.
```

### 2.3 Build, lint, and dependency verification

```bash
if command -v rustfmt >/dev/null 2>&1; then
  cargo fmt --check
else
  echo "SKIP: rustfmt not installed (rustup component add rustfmt)"
fi
if command -v cargo-clippy >/dev/null 2>&1; then
  cargo clippy -- -D warnings
else
  echo "SKIP: clippy not installed (rustup component add clippy)"
fi
cargo test

# Verify no todo!() remaining
rg 'todo!\(' --type rust && echo "ERROR: Unimplemented todo!() found" || echo "✓ No todo!() remaining"
rg 'unimplemented!\(' --type rust -g '!*test*' && echo "ERROR: unimplemented!() found" || echo "✓ No unimplemented!() remaining"

# Dependency audit (requires cargo-tree)
if cargo tree --version >/dev/null 2>&1; then
  cargo tree -d
  cargo tree --depth 1 | wc -l
else
  echo "SKIP: cargo-tree not installed (cargo install cargo-tree)"
fi
```

**Evidence required**: You SHALL paste the output of all Phase 2 commands. IF any checks fail, THEN you SHALL fix the issues and re-run verification.

---

## PHASE 3: Completion Checklist

Before marking the task complete, you SHALL verify each item and provide evidence:

- [ ] **Phase 0 completed**: Stubs with doc comments were written and compiled BEFORE implementation.
- [ ] **Round −1 observations addressed**: All intuitive concerns from Fresh Eyes phase were either resolved or documented as acceptable.
- [ ] **All banned patterns fixed**: Phase 2.1 scan shows no violations.
- [ ] **No oversized files**: Phase 2.2 shows files do not exceed reasonable size thresholds (or justification provided).
- [ ] **Build passes**: `cargo build` succeeds.
- [ ] **Format clean**: `cargo fmt --check` succeeds.
- [ ] **Clippy clean**: `cargo clippy -- -D warnings` succeeds.
- [ ] **Tests pass**: `cargo test` succeeds.
- [ ] **No todo!() remaining**: `rg 'todo!\(' --type rust` returns no matches.
- [ ] **New tests added**: At least one happy-path and one error-case test exist for new functionality.
- [ ] **Doc comments complete**: All public items have `///` doc comments with Examples section.

**Evidence required**: You SHALL paste the completion checklist with [x] marks and command outputs.

---

## ROUND 5: Final Sanity Check (AFTER All Mechanical Rounds)

After completing all structured rounds, set aside the checklists and evaluate the change holistically. This round exists because mechanical analysis can miss the forest for the trees.

- Revisit your Round −1 observations. Were all concerns addressed, or did any intuitive signals get lost in the shuffle of checklist compliance?
- Step back and ask: Does this change make the codebase better? Is the approach sound? Would a future maintainer understand and appreciate these changes?
- Capture any unexplained discomfort as a signal worth preserving — gut feelings often encode experience that resists articulation.
- If something still feels wrong but you cannot pinpoint why, note it explicitly rather than dismissing it.

**Evidence required**: You SHALL include a brief holistic assessment and confirm that Round −1 observations were revisited.

# GitOps Workflow

## Applicability

- WHEN you start work (branching) THEN you SHALL strictly follow all workflows set in this GitOps Workflow section.
- WHEN you draft, open, update, or merge a PR THEN you SHALL strictly follow all workflows set in this GitOps Workflow section.
- WHEN you write commits or a squash-merge message THEN you SHALL strictly follow all workflows set in this GitOps Workflow section.
- WHEN you draft release notes THEN you SHALL strictly follow all workflows set in this GitOps Workflow section.

## 1) Git branching workflow

- WHEN you start any work THEN you SHALL create a new branch:

  1. You SHALL branch from `main` (or the designated base branch for the task).
  2. You SHALL use descriptive branch names following the pattern:
     - `feat/<short-description>` for new features
     - `fix/<short-description>` for bug fixes
     - `docs/<short-description>` for documentation changes
     - `refactor/<short-description>` for refactoring
     - `test/<short-description>` for test additions/changes
  3. You SHALL NOT commit directly to `main`.
  4. WHEN you are about to make changes THEN you SHALL verify you are on the correct branch:

     ```bash
     git checkout main && git pull && git checkout -b <branch-name>
     ```

## 2) Pull request workflow

### 2.1 Link related issues

- WHEN you are about to create a PR THEN you SHALL check for related issues and link them:

  1. You SHALL search for relevant issues:

     ```bash
     gh issue list --search "keyword"
     gh issue list --label "bug"
     ```

  2. WHEN you link issues in the PR body THEN you SHALL use closing keywords (GitHub will auto-close the issue when the PR merges):
     - `Closes #123` — general completion
     - `Fixes #123` — bug fixes
     - `Resolves #123` — alternative syntax
  3. WHEN an issue is related but not fully resolved THEN you SHALL reference it without closing keywords:
     - `Related to #123`
     - `Part of #123`

### 2.2 PR description and reviewers

- IF your repo uses automated reviewers/bots THEN you SHALL list them in the PR body (separate lines; at the end of the PR description) so they reliably trigger.
- WHEN you script PR bodies/comments THEN you SHALL ensure newlines render as real line breaks (not literal `\n`): prefer `gh pr create --body-file ...` or `gh pr view --template '{{.body}}'` (or `--json body --jq '.body'`) when reading.
- WHEN you intend multi-line bodies THEN you SHALL ensure they render as real line breaks (you SHALL avoid literal `\n` in the rendered text).

### 2.3 Updating an existing PR

- WHEN you are about to push updates to an existing PR THEN you SHALL:

  1. You SHALL read top-level comments using `gh pr view <number> --comments` (or view on GitHub); you SHALL NOT skip these.
  2. You SHALL read inline review threads (these are not included in `gh pr view --comments`); to list unresolved inline threads via CLI, you SHALL use:

     ```bash
     gh api graphql -F owner=<owner> -F repo=<repo> -F number=<pr> -f query='
       query($owner:String!, $repo:String!, $number:Int!) {
         repository(owner:$owner, name:$repo) {
           pullRequest(number:$number) {
             reviewThreads(first:100) {
               nodes { isResolved comments(first:10) { nodes { author { login } body path line } } }
             }
           }
         }
       }' --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)'
     ```

  3. **Viewing raw diffs**: You MAY append `.diff` or `.patch` to any PR URL to retrieve plain-text output:

     - `https://github.com/<owner>/<repo>/pull/<number>.diff` — unified diff format
     - `https://github.com/<owner>/<repo>/pull/<number>.patch` — git patch format (includes commit metadata)

     This is useful for piping into tools, reviewing large PRs, or when the web UI is slow/unavailable.

  4. You SHALL identify unresolved feedback in BOTH top-level comments AND inline threads.
  5. You SHALL check CI/CD status (review failing checks and logs via `gh pr checks <number> --watch` or GitHub UI) and you SHALL plan fixes before pushing updates.
  6. You SHALL address or respond to each item before you push new commits.
  7. WHEN you address feedback THEN you SHALL reply in the original thread (you SHALL NOT create a new top-level comment):

     - IF permissions/tooling prevent inline replies THEN you SHALL leave a top-level PR comment that references the specific thread(s) and explains why inline reply was not possible.
     - To reply inline via CLI, you SHALL use the review comment reply endpoint:

       ```bash
       gh api -X POST /repos/<owner>/<repo>/pulls/<pr_number>/comments/<comment_id>/replies \
         -f body="reply text"
       ```

     - GraphQL note: `addPullRequestReviewComment` is deprecated; you SHOULD use `addPullRequestReviewThreadReply` with the thread ID if you need GraphQL-based replies.

  8. IF you implemented an automated reviewer/bot suggestion OR you are asking for clarification/further input THEN you SHALL re-tag the bot; IF you rejected the feedback THEN you SHALL NOT re-tag and you SHALL explain why in the thread.

### Treating automated reviewer feedback

- WHEN you receive automated reviewer feedback THEN you SHALL treat it as non-authoritative.
- You SHALL treat automated comments like reviews from a helpful but inexperienced junior developer:
  1. You SHALL verify claims before acting; suggestions may be incorrect, outdated, or miss repo-specific context.
  2. You SHALL NOT blindly apply changes; IF a suggestion conflicts with project invariants or conventions THEN it is wrong regardless of confidence.
  3. IF a claim is inaccurate THEN you SHALL NOT proceed; you SHALL respond directly in the PR thread explaining why.
  4. IF a suggestion is valid and you make changes THEN you SHALL reply in the same thread to keep context together; you SHOULD re-tag the bot so it can verify the fix.
  5. You MAY use automated reviews for catching typos, obvious bugs, missing tests, and style drift; you SHOULD treat them as less reliable for architectural decisions, invariant enforcement, and security boundaries.

### 2.4 Merging PRs

- WHEN you merge a PR THEN you SHALL ensure all of the following are satisfied:
  1. You SHALL ensure all review conversations are resolved (no unaddressed threads, top-level or inline).
  2. You SHALL ensure all CI/CD checks pass (green status).
  3. You SHALL ensure at least one approving review exists (from a qualified reviewer; MAY be bypassed with explicit permission).
  4. You SHALL ensure the author confirms the PR is ready to merge.
  5. You SHALL ensure the PR is rebased on the target branch (no merge conflicts).

**Merge strategy**:

- You SHALL use **squash and merge** as the default and preferred strategy.
- WHEN you squash and merge THEN you SHALL write the squash commit message using the format in section 3.4.
- You MAY use fast-forward or rebase merges for trivial single-commit PRs WHERE the original commit already conforms to section 3 (Commit conventions).

**Commit receipts**:

- AFTER push or merge operations, you SHALL include a receipt in user-visible output:

  ```markdown
  - **branch `<branch-name>`**
    - `<SHA>` `<type>[(<scope>)]:` _<description>_
    - `<SHA>` `<type>[(<scope>)]:` _<description>_
  ```

- You SHALL list branches in execution order (e.g., `test → fix → feat → refactor`).
- You SHALL include PR URL/ID if pushed.

## 3) Commit conventions

- You SHALL use **Conventional Commits** format for all commits.

### 3.1 Message format

```markdown
<type>(<scope>): <description>

[optional body]

[optional footer]
```

- You SHALL use one of the following commit types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`, `style`, `deps`, `security`, `revert`, `hotfix`.
- You SHOULD include a scope when it adds clarity (e.g., `feat(cli): add --json flag`, `fix(daemon): handle connection timeout`).
- You SHALL write the description in imperative mood ("Add feature" not "Added feature"); you SHALL use lowercase; you SHALL NOT end with a period.

### 3.2 Atomic commits

- You SHOULD ensure each commit represents **one logical change**.
- You SHOULD batch related file changes into a single commit (e.g., code + tests + docs for one feature).
- You SHOULD avoid mixing unrelated changes in one commit.

### 3.3 Examples

```markdown
feat(cli): add workspace init command
fix(daemon): prevent duplicate event emission on retry
docs: update kernel contract with error codes
refactor(storage): extract projection rebuild logic
test(protocol): add characterization test for unknown fields
chore: update dependencies
```

### 3.4 Squash commit body and release notes

- WHEN you squash-merge a PR (or draft the PR description) THEN you SHALL write the commit body using this structure.
- WHEN you draft or publish release notes (e.g., GitHub Release notes or a changelog entry) THEN you SHALL write the release body using this structure.

```markdown
<type>[(<scope>)]: <short imperative summary>

## Overview

<2–4 lines on context, intent, impact; reference key issues/PRs>

## New Features

- <new feature> (Refs: #123)

## What's Changed

- <enhancement/refactor/perf/docs/ci/build/style/deps> (Refs: #234)

## Bug Fixes

- <concise bug fix> (Fixes #345)

## Breaking Changes

- <impact one-liner>; migration: <concise steps>

## Commits

- `<SHA>` <original commit message>
- `<SHA>` <original commit message>

## Refs

- #123
- https://example.com/issue/456
```

**Section rules**:

- You SHALL emit sections in the order shown above: Overview, New Features, What's Changed, Bug Fixes, Breaking Changes, Commits, Refs.
- You SHALL omit empty sections EXCEPT `Overview` (always required).
- WHEN you write a squash-merge commit body THEN you SHALL include `Commits` for multi-commit PRs; you MAY omit it if the PR contains exactly one commit.
- WHEN you write release notes THEN you MAY omit `Commits`.
- You SHALL treat `## Refs` as the canonical location for all related issues/PRs/URLs.
- WHEN a bullet relates to a different issue than others THEN you MAY use inline `Fixes #id` or `Refs: #id`; OTHERWISE you SHOULD omit inline refs and rely on `## Refs`.
- IF the header contains `!` (breaking change) THEN you SHALL include a `Breaking Changes` section.

**Type-to-section mapping**:

| Commit type(s)                                                                                    | Section        |
| ------------------------------------------------------------------------------------------------- | -------------- |
| `feat`                                                                                            | New Features   |
| `fix`, `hotfix`                                                                                   | Bug Fixes      |
| `perf`, `refactor`, `docs`, `chore`, `ci`, `build`, `style`, `deps`, `revert`, `test`, `security` | What's Changed |

**Formatting rules**:

- You SHALL write the header in imperative mood with no trailing period; subject (after colon) SHOULD be ≤72 chars.
- You SHALL write bullets with `- ` prefix and they SHOULD be single-line (≤72 chars recommended).
- You SHALL write `Overview` as 2–4 lines of prose explaining why and impact; you SHALL NOT include refs in `Overview`.
- You SHALL NOT duplicate refs across bullets and `## Refs`.
- You SHALL ensure each ref item is a valid issue ref (`#123`), cross-repo ref (`owner/repo#123`), or URL.