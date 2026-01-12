---
name: apply-code-review
description: Apply code review feedback by consuming completed review reports and tracking progress. Use when processing reviewer feedback after a code review, to read findings, apply fixes, and communicate decisions back to reviewers.
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Apply Code Review

Follow the protocol in `references/code-review-application-protocol.md`.

## Session coordination

You SHALL use `scripts/mpcr` (located in the same directory as this SKILL.md) for all session operations.

The `mpcr` wrapper auto-compiles on first run if needed (requires `cargo`). IF compilation fails THEN you SHALL run `cargo build --release --manifest-path scripts/mpcr-src/Cargo.toml` to diagnose.

BEFORE using any `mpcr` command, you SHALL run `mpcr --help` to see all available commands, required arguments, and example flows.

**Fetch unreviewed reports:**
```
mpcr session reports closed --initiator-status REQUESTING,OBSERVING --include-report-contents --json
```
