---
name: apply-code-review
description: Apply code review feedback by consuming completed review reports and updating coordination state (`initiator_status`, applicator notes) in `.local/reports/code_reviews/{YYYY-MM-DD}/_session.json`, using the bundled `scripts/mpcr` tool for deterministic waiting, session inspection, status updates, and notes.
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Apply Code Review

Follow the protocol in `references/code-review-application-protocol.md`.

## Available commands

Use `scripts/mpcr` for session coordination. Run any command with `--help` for usage.

- `mpcr id` — generate identifiers
- `mpcr applicator wait` — block until reviewers finish
- `mpcr applicator set-status` — update initiator_status
- `mpcr applicator note` — append a note
- `mpcr session show` — inspect session state
- `mpcr session reports` — list open/closed/in-progress reviews (filters incl. status/phase/verdict + optional notes/report files)
- `mpcr lock` — manual lock operations
