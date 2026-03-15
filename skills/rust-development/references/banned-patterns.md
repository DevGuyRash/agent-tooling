# Banned Patterns

You SHALL use this as the authoritative reference for banned patterns.
IF a pattern appears here THEN you SHALL NOT use it in non-test code unless the specified escape hatch is applied.
WHEN a pattern has a specific escape hatch (for example `// INVARIANT:`) THEN you SHALL use that escape hatch.
WHEN no pattern-specific escape hatch exists and the pattern must remain THEN you SHALL add `// ALLOW: <reason>` on the same line.

---

## Table of contents

1. [Panic-inducing](#panic-inducing)
2. [Non-idiomatic](#non-idiomatic)
3. [String and allocation](#string-and-allocation)
4. [Parameter anti-patterns](#parameter-anti-patterns)
5. [Public API anti-patterns](#public-api-anti-patterns)
6. [Import anti-patterns](#import-anti-patterns)
7. [Debug and logging artifacts](#debug-and-logging-artifacts)
8. [Resource safety](#resource-safety)
9. [Unsafe and security](#unsafe-and-security)
10. [Meta](#meta)

---

## Panic-inducing

Clippy does NOT ban `.unwrap_or()`, `.unwrap_or_else()`, or `.unwrap_or_default()`.
The `banned_family.rs` test harness catches bare `.unwrap()` and `.expect()` calls; `.unwrap_or()`, `.unwrap_or_else()`, and `.unwrap_or_default()` are NOT banned.
The `// INVARIANT:` escape hatch applies only when the comment appears on the same line as the banned call.

| Pattern | Reason | Fix |
|---|---|---|
| `.unwrap*()` without same-line `// INVARIANT:` | Silent panic | `?`, `if let`, `match`, or add same-line `// INVARIANT:` comment |
| `.expect*()` without same-line `// INVARIANT:` | Silent panic | `?`, `if let`, `match`, or add same-line `// INVARIANT:` comment |
| `panic!()` in non-test code | Unrecoverable | Return `Result` or `Option` |
| `unimplemented!()` in non-test code | Placeholder | Implement or delete |
| `todo!()` outside tests after Phase 0 | Placeholder | Implement before Phase 2; scan MUST be empty |
| `unreachable!()` without same-line `// INVARIANT:` | Risky assumption | Refactor or add same-line `// INVARIANT:` comment |
| `assert!()` / `assert_eq!()` / `assert_ne!()` outside tests without same-line `// INVARIANT:` | Production panic path | Return `Result` or use `debug_assert!` with an invariant comment |
| `std::process::exit()` outside entrypoints | Hidden control flow | Return `Result`, map exit codes at boundary |

WHEN using `.expect()` with an invariant THEN you SHALL prefer `.expect("descriptive message")` over `.unwrap()`.

## Non-idiomatic

| Pattern | Reason | Fix |
|---|---|---|
| `.map(\|x\| x.clone())` | Non-idiomatic | `.cloned()` |
| `.map(\|x\| x.to_owned())` | Non-idiomatic | `.cloned()` (preferred) or `.map(ToOwned::to_owned)` using a method pointer when types differ |
| `.iter().collect::<Vec<_>>()` then immediately iterate | Unnecessary alloc | Chain iterators directly |
| `.into_iter().collect::<Vec<_>>()` on a `Vec` | Unnecessary alloc | Remove; already a `Vec` |
| `.iter().count()` with no filter/map | O(n) | `.len()` |
| `.iter().next()` on slice/`Vec` without same-line `// ALLOW: non-slice-next` for non-slice collections | Verbose | `.first()`, or annotate a justified non-slice use with same-line `// ALLOW: non-slice-next` |
| `for i in 0..x.len()` | Often non-idiomatic | Iterators/enumerate; add `// ALLOW:` only if indexing required |
| `.len() == 0` / `.len() != 0` | Verbose | `.is_empty()` / `!x.is_empty()` |
| `if x == true` / `if x == false` | Verbose | `if x` / `if !x` |
| `if x != true` / `if x != false` | Verbose | `if !x` / `if x` |

## String and allocation

| Pattern | Reason | Fix |
|---|---|---|
| `format!("{}", x)` when direct use or `.to_string()` suffices | Unnecessary alloc | Use `x` directly or `x.to_string()` |
| `String::from("")` / `"".to_string()` | Unnecessary alloc | `String::new()` |

## Parameter anti-patterns

| Pattern | Reason | Fix |
|---|---|---|
| `&String` in function parameters | Unnecessary indirection | `&str` |
| `&Vec<T>` in function parameters | Unnecessary indirection | `&[T]` |
| `&Box<T>` anywhere | Unnecessary indirection | `&T` |

## Public API anti-patterns

| Pattern | Reason | Fix |
|---|---|---|
| `Box<dyn std::error::Error>` in `pub` APIs | Opaque errors | Structured error enum |
| `anyhow::Result` / `anyhow::Error` in `pub` APIs | Opaque errors | Structured error enum; keep `anyhow` at app boundary |
| `impl Into<X>` with only one concrete type | Over-generic | Use concrete type |
| `impl AsRef<X>` with only one concrete type | Over-generic | Use concrete type |

## Import anti-patterns

| Pattern | Reason | Fix |
|---|---|---|
| `use crate::*;` / `use super::*;` outside tests | Glob hides deps | Import explicitly |
| `use some::path::*;` outside tests (non-prelude) | Glob hides deps | Import explicitly |

## Debug and logging artifacts

| Pattern | Reason | Fix |
|---|---|---|
| `dbg!()` in non-test code | Debug artifact | Remove |
| `println!()` / `eprintln!()` for logging | Unstructured | tracing/log crate or remove |
| `static mut` | Unsound global mutability | `OnceLock`/`LazyLock` + safe sync |

## Resource safety

| Pattern | Reason | Fix |
|---|---|---|
| `mem::forget(...)` without same-line `// ALLOW:` | Easy to leak resources or break drop guarantees | Refactor ownership/lifetime flow or justify the exceptional case explicitly |
| `Box::leak(...)` without same-line `// ALLOW:` | Permanent allocation / lifetime escape | Refactor ownership or justify the exceptional case explicitly |

## Unsafe and security

Unsafe constructs are hard out-of-profile failures for this skill.
`// SAFETY:` and `// ALLOW:` do NOT permit them under this skill's default workflow.

| Pattern | Reason | Fix |
|---|---|---|
| `unsafe { ... }`, `unsafe fn`, `unsafe trait`, or `unsafe impl` in non-test code | Out of profile for this skill | Refactor to safe Rust, or stop and get explicit repo/user direction |
| `unsafe impl Send` / `unsafe impl Sync` in non-test code | Out of profile and easy to get wrong | Refactor to safe Rust, or stop and get explicit repo/user direction |
| `Command::new("sh").arg("-c")` (or `bash`, `cmd /C`) | Shell injection | Build argv explicitly |

## Meta

| Pattern | Reason | Fix |
|---|---|---|
| `// TODO` without issue reference | Orphaned work | Add issue ref or complete the work |
| `#[allow(...)]` without `// Reason:` | Unexplained suppression | Add justification comment |
