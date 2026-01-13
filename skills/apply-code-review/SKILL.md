---
name: apply-code-review
description: Apply code review feedback by consuming completed review reports and tracking progress. Use when processing reviewer feedback after a code review, to read findings, apply fixes, and communicate decisions back to reviewers.
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Apply Code Review

Before reviewing any code, you SHALL read `references/code-review-application-protocol.md` in **300-line chunks**. After each chunk, you SHALL summarize your understanding before continuing. It defines status values, note types, and disposition formats you MUST use.

## Deliverables

- A disposition (applied/declined/deferred/etc) for every finding, recorded via `mpcr applicator note`
- Code changes for findings you apply
- Updated `initiator_status` reflecting your progress

## Workflow

You SHALL use `mpcr` for all operations and interactions regarding the `_session.json` file and and for gathering, viewing, and interacting with review reports. The CLI is at `scripts/mpcr` relative to this SKILL.md file. It auto-compiles on first run (requires `cargo`). Run `mpcr --help` for full command reference.

```
mpcr session reports closed --include-report-contents --json   # Fetch reports
mpcr applicator note --session-id ID --review-id ID --note-type applied --content "..."
mpcr applicator set-status --status APPLYING
```

Read each report, then read the actual code at the referenced anchors. Verify findings before deciding to fix, decline, or defer.

## Inputs

- A session directory under `.local/reports/code_reviews/YYYY-MM-DD/` containing `_session.json` and reviewer report(s).

## Without session infrastructure

IF `mpcr` is unavailable or session files don't exist THEN work directly from the review content provided to you. Your code changes and stated dispositions are the deliverables.
