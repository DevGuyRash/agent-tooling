---
name: apply-code-review
description: Apply code review feedback by consuming completed review reports and tracking progress. Use when processing reviewer feedback after a code review, to read findings, apply fixes, and communicate decisions back to reviewers.
compatibility: Requires a POSIX shell. If `<skills-file-root>/scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `<skills-file-root>/scripts/mpcr-src`.
---

# Apply Code Review

## Ingestion protocol (once per conversation)

Before applying any code changes, you SHALL read `<skills-file-root>/references/code-review-application-protocol.md`.

- IF you need to ingest it in parts THEN you SHALL read it in **<= 500-line chunks**.
- IF you have already ingested the protocol earlier in this conversation THEN you SHALL NOT re-ingest it; proceed with the workflow below.

## Deliverables

- A disposition (applied/declined/deferred/etc) for every finding, recorded via `mpcr applicator note`
- Code changes for findings you apply
- Updated `initiator_status` reflecting your progress

## Workflow

You SHALL use `mpcr` for all operations and interactions regarding the `_session.json` file and for gathering, viewing, and interacting with review reports. The CLI is located in the same directory as this `SKILL.md` file at `<skills-file-root>/scripts/mpcr`. It auto-compiles on first run (requires `cargo`). Run `mpcr --help` for full command reference.

```
mpcr session reports closed --include-notes --include-report-contents --json   # Fetch reports
mpcr applicator note --reviewer-id ID --session-id ID --note-type applied --content "..."
mpcr applicator set-status --reviewer-id ID --session-id ID --initiator-status APPLYING
```

Tip: IF you are processing one review entry at a time THEN you MAY export `MPCR_SESSION_DIR`, `MPCR_REVIEWER_ID`, and `MPCR_SESSION_ID` for that entry and omit repeated flags in subsequent `mpcr` commands.

Read each report, then read the actual code at the referenced anchors. Verify findings before deciding to fix, decline, or defer.

## Inputs

- A session directory under `.local/reports/code_reviews/YYYY-MM-DD/` containing `_session.json` and reviewer report(s).

## Without session infrastructure

IF `mpcr` is unavailable or session files don't exist THEN work directly from the review content provided to you. Your code changes and stated dispositions are the deliverables.
