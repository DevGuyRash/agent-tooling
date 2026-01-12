---
name: apply-code-review
description: Apply code review feedback by consuming completed review reports and tracking progress. Use when processing reviewer feedback after a code review, to read findings, apply fixes, and communicate decisions back to reviewers.
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Apply Code Review

Follow the protocol in `references/code-review-application-protocol.md`.

## Session coordination

Use `scripts/mpcr` for all session operations. Run any command with `--help` for full usage and available filters.

The `mpcr` wrapper auto-compiles on first run if needed (requires `cargo`). IF compilation fails THEN you SHALL run `cargo build --release --manifest-path scripts/mpcr-src/Cargo.toml` to diagnose.

**Fetch unreviewed reports:**
```
mpcr session reports closed --initiator-status REQUESTING,OBSERVING --include-report-contents --json
```

**Key commands:**
- `mpcr applicator wait` — block until reviewers finish
- `mpcr applicator set-status` — update your progress
- `mpcr applicator note` — record decisions
- `mpcr session show` — view session state
- `mpcr session reports` — list/fetch reviews
