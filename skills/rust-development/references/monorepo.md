# Rust Monorepo Guidelines

WHEN working in a Rust workspace or monorepo THEN you SHALL read this file before Phase 0.

---

## Table of contents

1. [Workspace layout](#1-workspace-layout)
2. [Crate boundaries and dependencies](#2-crate-boundaries-and-dependencies)
3. [Binary entrypoints](#3-binary-entrypoints)
4. [File structure](#4-file-structure)
5. [Async considerations](#5-async-considerations)
6. [Verification additions](#6-verification-additions)

---

## 1. Workspace layout

You SHALL keep all Rust code inside the repository's existing Rust root.
WHEN no Rust root exists THEN you SHALL create one Rust workspace under `tools/rust/` or another repo-approved location.
You SHALL NOT create `Cargo.toml` files outside the Rust root.
You SHALL use a Rust workspace so crates share one `Cargo.lock` and one `target/` directory.
You SHALL NOT create multiple lockfiles unless the repository already requires them.
You SHALL use stable Rust by default.
You SHALL match the repository's edition and common `Cargo.toml` conventions.

You SHALL verify placement:

```bash
find . -name 'Cargo.toml' -type f
```

## 2. Crate boundaries and dependencies

You SHALL keep dependencies minimal and justified.
WHEN a tool requires heavy dependencies — more than 50 transitive crates, native libs, or complex runtimes — THEN you SHALL isolate that tool in its own crate.
WHEN a tool requires fewer than 50 transitive crates THEN you SHALL prefer a single crate with multiple binaries.
You SHALL NOT split crates without demonstrated benefit.
You SHALL use `default-features = false` when possible.
You SHALL enable only the features needed for the task.
WHEN non-default features are enabled THEN you SHALL add a comment explaining why.
WHEN the repository uses workspace dependencies THEN you SHALL use them.

You SHALL verify transitive dependency count:

```bash
cargo tree -p <crate> | wc -l
```

## 3. Binary entrypoints

You SHALL keep binary entrypoints — `src/main.rs`, `src/bin/*.rs` — thin.
You SHALL limit them to: argument parsing, dependency wiring, a call into library/module code, error handling, and exit code mapping.
You SHALL place core logic in library modules, not in binary entrypoints.

You SHALL verify entrypoint sizes:

```bash
find . \( -path '*/src/main.rs' -o -path '*/src/bin/*.rs' \) -print | while IFS= read -r f; do
  lines=$(wc -l < "$f")
  if [ "$lines" -gt 100 ]; then echo "WARN: $f has $lines lines"; fi
done
```

## 4. File structure

WHEN a file grows difficult to navigate or mixes unrelated concerns THEN you SHALL split it into focused modules.
You SHALL extract shared modules only when two or more crates use them with a stable interface.
WHEN only one crate uses logic THEN you SHALL keep it local to that crate.

## 5. Async considerations

You SHALL choose async intentionally.
WHEN the repository already uses an async runtime THEN you SHALL use that runtime.
You SHALL NOT introduce a new async runtime without explicit approval.
WHEN fewer than 10 concurrent I/O operations are needed THEN you SHALL use synchronous code.
You SHALL cap concurrency with semaphores or bounded queues.
You SHALL NOT hold `std::sync::Mutex` across `.await`.

## 6. Verification additions

WHEN running `verify.sh` in a workspace THEN you SHALL pass the workspace root:

```bash
<skills-file-root>/scripts/verify.sh --dir <workspace-root>
```

You SHALL verify:
- All `Cargo.toml` files are under the Rust root.
- Binary entrypoints are within the line-count threshold.
- No file is disproportionately large without justification.
