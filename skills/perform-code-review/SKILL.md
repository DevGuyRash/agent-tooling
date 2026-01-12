---
name: perform-code-review
description: Perform adversarial code reviews using the UACRP protocol. Use when reviewing code changes, PRs, or diffs. Produces structured review reports with verdicts (APPROVE/REQUEST CHANGES/BLOCK), findings by severity, and evidence-backed proofs.
compatibility: Requires a POSIX shell. If `scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `scripts/mpcr-src`.
---

# Perform Code Review

Follow the UACRP protocol in `references/uacrp.md`.

## Session coordination

You SHALL use `scripts/mpcr` (located in the same directory as this SKILL.md) for all session operations. Run any command with `--help` for full usage and available options.

The `mpcr` wrapper auto-compiles on first run if needed (requires `cargo`). IF compilation fails THEN you SHALL run `cargo build --release --manifest-path scripts/mpcr-src/Cargo.toml` to diagnose.

**Key commands:**
- `mpcr reviewer register` — register and get your reviewer_id
- `mpcr reviewer update` — update status/phase as you work
- `mpcr reviewer note` — append observations
- `mpcr reviewer finalize` — complete with verdict and report
- `mpcr session show` — view session state
- `mpcr session reports` — list/fetch reviews
