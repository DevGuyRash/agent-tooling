---
name: apply-code-review
description: Apply code review feedback by consuming completed review reports and updating coordination state (`initiator_status`, applicator notes) in `.local/reports/code_reviews/{YYYY-MM-DD}/_session.json`, using the bundled `scripts/mpcr` tool for deterministic waiting, session inspection, status updates, and notes.
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Apply Code Review

Use the protocol in `references/code-review-application-protocol.md`.

Use `scripts/mpcr` (bundled; builds `scripts/mpcr-src` on first run) for deterministic coordination file updates.

## Deterministic primitives (`mpcr`)

- Wait until reviewers reach terminal status:
  - `scripts/mpcr applicator wait --session-dir "<dir>"`
- Inspect session and locate reports:
  - `scripts/mpcr session show --session-dir "<dir>"`
- Update `initiator_status` for a given review entry:
  - `scripts/mpcr applicator set-status --session-dir "<dir>" --reviewer-id "<id8>" --session-id "<id8>" --initiator-status RECEIVED`
- Append applicator notes back to reviewers:
  - `scripts/mpcr applicator note --session-dir "<dir>" --reviewer-id "<id8>" --session-id "<id8>" --note-type applied --content "..." `
