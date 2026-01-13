---
name: perform-code-review
description: Perform adversarial code reviews using the UACRP protocol. Use when reviewing code changes, PRs, or diffs. Produces structured review reports with verdicts (APPROVE/REQUEST_CHANGES/BLOCK), findings by severity, and evidence-backed proofs.
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Perform Code Review

Before reviewing any code, you SHALL read `references/uacrp.md` in **300-line chunks**. After each chunk, you SHALL summarize your understanding before continuing. The protocol defines domains, evidence standards, severity rubrics, and the report template you MUST use.

## Deliverables

- A UACRP report (Sections 0–11) with exactly one verdict: `APPROVE`, `REQUEST_CHANGES`, or `BLOCK`
- Findings anchored to specific code locations with evidence
- Report saved via `mpcr` (or output to chat if unavailable)

## Workflow

You SHALL use `mpcr` for all operations and interactions regarding the `_session.json` file. The CLI is at `scripts/mpcr` relative to this SKILL.md file. It auto-compiles on first run (requires `cargo`). Run `mpcr --help` for full command reference.

```
mpcr reviewer register --target-ref HEAD
mpcr reviewer complete --review-id ID --verdict REQUEST_CHANGES --report-file report.md
mpcr reviewer note --review-id ID --note-type question --content "..."
```

## Inputs

- A diff/patch/PR context (provided by the user and/or repository checkout).
- `mpcr` does NOT fetch diffs; it only coordinates sessions and artifacts.

## Without session infrastructure

IF `mpcr` is unavailable or you lack filesystem write access THEN output the full UACRP report directly in chat. The report itself is the deliverable.
