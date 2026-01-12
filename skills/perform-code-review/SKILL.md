---
name: perform-code-review
description: Perform adversarial code reviews using the UACRP protocol. Use when reviewing code changes, PRs, or diffs. Produces structured review reports with verdicts (APPROVE/REQUEST CHANGES/BLOCK), findings by severity, and evidence-backed proofs.
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Perform Code Review

Follow the UACRP protocol in `references/uacrp.md`.

## Session coordination

You SHALL use `scripts/mpcr` (located in the same directory as this SKILL.md) for all session operations.

The `mpcr` wrapper auto-compiles on first run if needed (requires `cargo`). IF compilation fails THEN you SHALL run `cargo build --release --manifest-path scripts/mpcr-src/Cargo.toml` to diagnose.

BEFORE using any `mpcr` command, you SHALL run `mpcr --help` to see all available commands, required arguments, and example flows.
