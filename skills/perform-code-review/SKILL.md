---
name: perform-code-review
description: Perform adversarial code reviews using the UACRP protocol and report template, writing coordination artifacts under `.local/reports/code_reviews/{YYYY-MM-DD}/` and using the bundled `scripts/mpcr` tool for deterministic reviewer/session operations (ID generation, locking, session JSON updates, report file writing).
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Perform Code Review

## Canonical protocol

Follow the UACRP protocol and report template in `references/uacrp.md`.

## Deterministic primitives (`mpcr`)

- Register yourself as a reviewer (creates/updates `_session.json`):
  - `scripts/mpcr reviewer register --target-ref "<branch|pr|commit>"` (optional: `--repo-root`, `--date`, `--reviewer-id`, `--session-id`, `--parent-id`)
- Update your status/phase during the review:
  - `scripts/mpcr reviewer update --session-dir "<dir>" --reviewer-id "<id8>" --session-id "<id8>" --status IN_PROGRESS --phase INGESTION`
- Append reviewer notes/questions (written into `_session.json`):
  - `scripts/mpcr reviewer note --session-dir "<dir>" --reviewer-id "<id8>" --session-id "<id8>" --note-type question --content "..." `
- Finalize (writes `{HH-MM-SS-mmm}_{ref}_{reviewer_id}.md` and updates `_session.json`):
  - `scripts/mpcr reviewer finalize --session-dir "<dir>" --reviewer-id "<id8>" --session-id "<id8>" --verdict APPROVE --major 1 --minor 0 --nit 0 --blocker 0 --report-file "<path>"`

## Session inspection

- View the full session state:
  - `scripts/mpcr session show --session-dir "<dir>"`
