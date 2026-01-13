---
name: perform-code-review
description: Perform adversarial code reviews using the UACRP protocol. Use when reviewing code changes, PRs, or diffs. Produces structured review reports with verdicts (APPROVE/REQUEST_CHANGES/BLOCK), findings by severity, and evidence-backed proofs.
compatibility: Requires a POSIX shell. If `<skills-file-root>/scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `<skills-file-root>/scripts/mpcr-src`.
---

# Perform Code Review

**Ingestion Protocol:** Before reviewing any code, you must read `<skills-file-root>/references/uacrp.md` in **chunks of 500 line** batches. Do not attempt to process the whole file at once. The protocol defines domains, evidence standards, severity rubrics, and the report template you MUST use. Process it in 500-line blocks to ensure every rule is retained and no context is lost.
**Action:** Once—and only once—you have ingested the full protocol using this chunking method, proceed to perform code review following ALL procedures outlined in `<skills-file-root>/references/uacrp.md`.

## Deliverables

- A UACRP report (Sections 0–11) with exactly one verdict: `APPROVE`, `REQUEST_CHANGES`, or `BLOCK`
- Findings anchored to specific code locations with evidence
- Report saved via `mpcr` (or output to chat if unavailable)

## Workflow

You SHALL use `mpcr` for all operations and interactions regarding the `_session.json` file. The CLI is located in the same directory as this `SKILL.md` file at `<skills-file-root>/scripts/mpcr`. It auto-compiles on first run (requires `cargo`). Run `mpcr --help` for full command reference.

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
