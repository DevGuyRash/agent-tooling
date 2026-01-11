---
name: perform-code-review
description: Perform adversarial code reviews using the UACRP protocol and report template, writing coordination artifacts under `.local/reports/code_reviews/{YYYY-MM-DD}/` and using the bundled `scripts/mpcr` tool for deterministic reviewer/session operations (ID generation, locking, session JSON updates, report file writing).
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Perform Code Review

Follow the UACRP protocol in `references/uacrp.md`.

## Available commands

Use `scripts/mpcr` for session coordination. Run any command with `--help` for usage.

- `mpcr id` — generate identifiers
- `mpcr reviewer register` — register as a reviewer
- `mpcr reviewer update` — update status/phase
- `mpcr reviewer note` — append a note
- `mpcr reviewer finalize` — write report and mark finished
- `mpcr session show` — inspect session state
- `mpcr session reports` — list open/closed/in-progress reviews (filters incl. status/phase/verdict + optional notes/report files)
- `mpcr lock` — manual lock operations
