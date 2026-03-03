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
1. Run `mpcr protocol capabilities`
2. Run `mpcr protocol orchestrator`
3. Run `mpcr protocol domains`
4. IF capabilities include `mpcr protocol invocation-aliases`, run it.
5. IF capabilities include `mpcr protocol workflow-selection`, run it.
6. IF capabilities include `mpcr protocol scope-mapping`, run it.
7. IF capabilities include `mpcr protocol convergence-planning`, run it.
8. WHEN full-cycle applies, run `mpcr protocol fullcycle`

## Universal rules
- The orchestrator is coordinator-only. It SHALL NOT emit direct file:line findings; line-level findings come from dispatched reviewer/applicator workers.
- "Single-agent" review still means one dispatched worker, not direct orchestrator diff inspection.
- Do not paste raw diffs unless requested.
- Keep code excerpts <= 12 lines each and <= 3 excerpts total.
- Proof/report artifacts SHALL be TOML-first (`proof_packet.v2`) with JSON fallback only; YAML is forbidden.
- TOML-first applies to proof/report artifacts. CLI operational output may remain JSON (`--json`, `--json-pretty`).
- Use `mpcr fullcycle plan`, `mpcr fullcycle loop-plan`, `mpcr fullcycle checkpoint`, and `mpcr fullcycle state` as the deterministic execution bridge for full-cycle orchestration.
- WHEN user intent requests a fresh start (for example "start fresh", "clear it out", "wipe prior reviews"), you SHALL run `mpcr reviewer register` with `--clear-session-day` (single day) or `--clear-all-session-days` (all date directories). IF no fresh-start intent is present, you SHALL NOT pass cleanup flags.
- Write scratch artifacts only under `.local/tmp/`; delete `.local/tmp/` after workflow completion.
- Refresh guidance at phase transitions via `mpcr protocol ...`.
- Prefer explicit CLI flags (`--session-dir`, `--reviewer-id`, `--session-id`) over environment variables.
- In source-only installs, first-run wrapper commands MAY build `mpcr` and emit cargo compile or package-lock wait output before protocol text.

## Skills debugging: error accumulation log
At the start of each top-level invocation, create one log file for this skill.

- Unix path:
  - `/tmp/skill-errors/code-review/<yyyy-mm-dd>/<HH-MM-SS>_errors.md`
- Windows path:
  - `%TEMP%\\skill-errors\\code-review\\<yyyy-mm-dd>\\<HH-MM-SS>_errors.md`

Log skill-caused friction only (documentation mismatches, bad role names, missing files, protocol contradictions, wrapper/CLI behavior mismatches). Do not log user-project build/test failures.

## Reference index (CLI unavailable fallback)
Use these only when `mpcr protocol ...` cannot run.

| File | When to read |
| --- | --- |
| `<skills-file-root>/references/orchestrator-fallback.md` | Orchestrator mode |
| `<skills-file-root>/references/reviewer-fallback.md` | Reviewer phase guidance |
| `<skills-file-root>/references/applicator-fallback.md` | Applicator phase guidance |
| `<skills-file-root>/references/fullcycle-fallback.md` | Full-cycle convergence guidance |
