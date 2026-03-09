---
name: code-review
description: >-
  Run machine-first code review, review application, and full-cycle convergence
  workflows with the `mpcr` v2 CLI. Use when reviewing diffs or PRs, applying
  structured findings, validating canonical review artifacts, rendering reports
  from machine artifacts, or driving severity-bounded review→apply→verify loops.
compatibility: >-
  Cross-platform. Primary entrypoint: `<skills-file-root>/scripts/mpcr` (POSIX)
  or `<skills-file-root>/scripts/mpcr.cmd` (Windows; falls back to
  `<skills-file-root>/scripts/mpcr.ps1`).
---

# Code Review

## Scope root
All skill-local paths resolve from `<skills-file-root>` (the directory containing this file).

## Invocation aliases
Recognize these as triggers (case-insensitive):
- `code-review reviewer [ctx]` or `code-review review [ctx]`
- `code-review applicator [ctx]` or `code-review apply [ctx]`
- `code-review full-cycle [ctx]`, `code-review full [ctx]`, or `code-review auto [ctx]`
- `code-review [ctx]` (infer reviewer/applicator/full-cycle from the task)

## Bootstrap
WHEN this skill triggers THEN you SHALL infer the mode from the user request.
WHEN the mode is known THEN you SHALL run `mpcr route --mode <reviewer|applicator|full-cycle> --target-ref <ref> --execution-capability <single_process|bounded_helpers|parallel_subagents> --max-worker-count <n> --orchestrator-read-budget-lines <n> --orchestrator-read-budget-snippets <n> [--changed-file <path>]... [--public-interface <path>]... [--behavior-facing-artifact <path>]...` first.
WHEN the route exists THEN you SHALL run `mpcr protocol mode --mode <reviewer|applicator|full-cycle> --view checklist` second.
WHEN `route_decision.worker_plan` identifies workers THEN you SHALL load only the matching `mpcr protocol worker --kind <worker-kind> --view checklist` packs.
WHEN `route_decision.selected_modules` identifies modules THEN you SHALL load only the matching `mpcr protocol module --id <module-id> --view checklist` packs.
WHEN `route_decision.heldback_escalations` or runtime triggers require escalation policy THEN you SHALL load only the matching `mpcr protocol escalation --id <escalation-id> --view checklist` packs.
WHEN confidence is low, output is malformed, a retry is in progress, or the user explicitly asks for examples THEN you SHALL use `--view examples`.
WHEN you need static discovery outside the routed flow THEN you MAY run `mpcr protocol list`.

## Wrapper behavior
`<skills-file-root>/scripts/mpcr` auto-builds the Rust binary in `<skills-file-root>/scripts/mpcr-src/target/release/mpcr`.

IF the release binary is missing or stale THEN the wrapper SHALL run `cargo build --manifest-path <skills-file-root>/scripts/mpcr-src/Cargo.toml --locked --release`.
IF `cargo` is unavailable and the binary is missing THEN the wrapper SHALL fail with a concise Rust-toolchain error.

## Universal rules
You SHALL treat the machine artifact as canonical truth, not prose.
You SHALL write canonical artifacts under `.local/reports/code_reviews/YYYY-MM-DD/artifacts/...`.
You SHALL render human markdown only with `mpcr render --artifact-file <path> --format markdown`.
You SHALL run `mpcr validate --artifact-file <path> --kind <artifact_kind> --layer hard` before any finalize or checkpoint step.
You SHALL treat hard validation as blocking and soft validation as warning-only.
You SHALL keep `_session.toml` compact and reference-only.
You SHALL treat `.local/tmp/code-review/` as scratch only.
You SHALL reject any v1 session, report, packet, or protocol assumption and you SHALL start a fresh v2 session instead.
You SHOULD prefer explicit CLI flags such as `--session-dir`, `--reviewer-id`, and `--artifact-file`.

## Mode guidance
WHEN reviewer work needs session-visible routing THEN you SHOULD use `mpcr route --persist ...` before `mpcr reviewer register --target-ref <ref>`.
WHEN running reviewer mode THEN you SHALL finalize child work with `mpcr reviewer complete-child --artifact-file <child_findings>` and you SHALL finalize synthesis with `mpcr reviewer finalize --artifact-file <parent_review>`.
WHEN running applicator mode THEN you SHALL track state with `mpcr applicator set-status`, you SHALL finalize application with `mpcr applicator finalize --artifact-file <application_result>`, and you SHALL finalize verification with `mpcr applicator verify --artifact-file <verification_result>`.
WHEN running full-cycle mode THEN you SHALL build the next convergence artifact with `mpcr fullcycle plan`, you SHALL persist it with `mpcr fullcycle checkpoint --artifact-file <convergence_state>`, and you SHALL inspect the current checkpoint with `mpcr fullcycle state`.
WHEN grouped precision data is needed THEN you SHALL use `mpcr session metrics`.

## Skills debugging: error accumulation log
At the start of each top-level invocation, create one log file for this skill.

- Unix path:
  - `/tmp/skill-errors/code-review/<yyyy-mm-dd>/<HH-MM-SS>_errors.md`
- Windows path:
  - `%TEMP%\\skill-errors\\code-review\\<yyyy-mm-dd>\\<HH-MM-SS>_errors.md`

Log skill-caused friction only: documentation drift, policy lookup mismatches, wrapper issues, missing generated fallback docs, or CLI behavior that contradicts the v2 policy surface. Do not log user-project build or test failures.

## Reference index (CLI unavailable fallback)
Use these only when `mpcr protocol ...` cannot run.

| File | When to read |
| --- | --- |
| `<skills-file-root>/references/reviewer-fallback.md` | Reviewer mode fallback |
| `<skills-file-root>/references/applicator-fallback.md` | Applicator mode fallback |
| `<skills-file-root>/references/fullcycle-fallback.md` | Full-cycle fallback |
| `<skills-file-root>/references/orchestrator-fallback.md` | Routing and policy-load fallback |
