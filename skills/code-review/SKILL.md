---
name: code-review
description: >-
  Perform adversarial code review workflows and review-application workflows via
  the `mpcr` protocol CLI. Use when reviewing diffs/PRs, synthesizing structured
  review findings, applying review feedback, running full-cycle review→apply→re-review,
  or coordinating specialist subagents for security, correctness, complexity, and
  release readiness decisions.
compatibility: >-
  Cross-platform. Primary entrypoint: `<skills-file-root>/scripts/mpcr` (POSIX) or
  `<skills-file-root>/scripts/mpcr.cmd` (Windows; falls back to
  `<skills-file-root>/scripts/mpcr.ps1`). Practical AGENTS compliance note: this skill
  currently ships source + wrappers but no committed prebuilt `mpcr` binary, so first-run
  may require a Rust toolchain to build `<skills-file-root>/scripts/mpcr-src`.
---

# Code Review

## Scope root
All skill-local paths resolve from `<skills-file-root>` (the directory containing this file).

## Invocation aliases
Recognize these as triggers (case-insensitive):
- `code-review reviewer [ctx]` or `code-review review [ctx]`
- `code-review applicator [ctx]` or `code-review apply [ctx]`
- `code-review full-cycle [ctx]`, `code-review full [ctx]`, or `code-review auto [ctx]`
- `code-review [ctx]` (infer via workflow selection guidance)

## Worker detection (highest precedence)
IF the prompt includes `## Proof Packet:`, `MPCR_DISPATCH_ROLE=`, or `MPCR_APPLICATOR_ROLE=`, you are a worker.
- STOP reading this file.
- Follow the dispatch prompt only.
- You MAY run `mpcr protocol <subcommand>` for phase guidance.

## Orchestrator bootstrap
When not in worker mode:
1. Run `mpcr protocol orchestrator`
2. Run `mpcr protocol domains`
3. Run `mpcr protocol invocation-aliases`
4. Run `mpcr protocol workflow-selection`
5. Run `mpcr protocol scope-mapping`
6. Run `mpcr protocol convergence-planning`
7. WHEN full-cycle applies, run `mpcr protocol fullcycle`

## Universal rules
- Do not paste raw diffs unless requested.
- Keep code excerpts <= 12 lines each and <= 3 excerpts total.
- Proof/report artifacts SHALL be TOML-first (`proof_packet.v2`) with JSON fallback only; YAML is forbidden.
- Write scratch artifacts only under `.local/tmp/`; delete `.local/tmp/` after workflow completion.
- Refresh guidance at phase transitions via `mpcr protocol ...`.
- Prefer explicit CLI flags (`--session-dir`, `--reviewer-id`, `--session-id`) over environment variables.

## Skills debugging: error accumulation log
At the start of each top-level invocation, create one log file for this skill.

- Unix path:
  - `/tmp/skill-errors/<yyyy-mm-dd>/<HH-MM-SS>_code-review_errors.md`
- Windows path:
  - `%TEMP%\\skill-errors\\<yyyy-mm-dd>\\<HH-MM-SS>_code-review_errors.md`

Log skill-caused friction only (documentation mismatches, bad role names, missing files, protocol contradictions, wrapper/CLI behavior mismatches). Do not log user-project build/test failures.

## Reference index (CLI unavailable fallback)
Use these only when `mpcr protocol ...` cannot run.

| File | When to read |
| --- | --- |
| `<skills-file-root>/references/orchestrator-fallback.md` | Orchestrator mode |
| `<skills-file-root>/references/reviewer-fallback.md` | Reviewer phase guidance |
| `<skills-file-root>/references/applicator-fallback.md` | Applicator phase guidance |
| `<skills-file-root>/references/fullcycle-fallback.md` | Full-cycle convergence guidance |
