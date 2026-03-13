---
name: code-review
description: >-
  Run recursive, machine-first code review, review application, and full-cycle
  convergence workflows with the `mpcr` CLI. Use when reviewing diffs or PRs,
  applying structured findings, validating canonical review artifacts, or
  driving review→apply→verify loops with per-agent report trees.
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
Infer the mode from the user request first.

Run `mpcr route --mode <reviewer|applicator|full-cycle> --target-ref <ref> --execution-capability <single_process|bounded_helpers|parallel_subagents> --max-worker-count <n> --orchestrator-read-budget-lines <n> --orchestrator-read-budget-snippets <n> [--changed-file <path>]... [--public-interface <path>]... [--behavior-facing-artifact <path>]...` before loading detailed guidance.

Use `mpcr route --persist ...` whenever the task needs session-visible routing, reviewer registration, recursive child directories, or later `protocol dispatch` lookups.

After routing:
- Use `mpcr protocol mode --mode <reviewer|applicator|full-cycle> --view checklist` for the top-level mode contract.
- Keep the orchestrator thin. Treat `route_decision.worker_plan.role_id` as the worker roster to register or spawn.
- For every active worker, load `mpcr protocol dispatch --role <role> --session-dir <path> [--reviewer-id <id>] --view checklist`.
- When a worker has its dispatch prompt, follow that dispatch plus the referenced packs instead of re-reading this whole skill body.
- Use static `mpcr protocol worker|module|escalation` lookups only for discovery, fallback, or narrow troubleshooting.

## Wrapper behavior
`<skills-file-root>/scripts/mpcr` auto-builds the Rust binary in `<skills-file-root>/scripts/mpcr-src/target/release/mpcr`.

If the release binary is missing or stale, the wrapper runs `cargo build --manifest-path <skills-file-root>/scripts/mpcr-src/Cargo.toml --locked --release`.

If `cargo` is unavailable and the binary is missing, the wrapper fails with a concise Rust-toolchain error.

## Universal rules
- Machine artifacts are canonical truth. Authored `report.md` files are required explanatory companions for each agent directory.
- `_session.json` is the primary session ledger. `_session.toml` is the mirror when TOML writes succeed.
- Canonical machine artifacts live under `.local/reports/code_reviews/YYYY-MM-DD/artifacts/...`.
- Render canonical artifact markdown with `mpcr render --artifact-file <path> --format markdown`.
- Retrieve recursive report trees with `mpcr session reports`.
- Retrieve flat artifact inventory with `mpcr session artifacts`.
- Run `mpcr validate --artifact-file <path> --kind <artifact_kind> --layer hard` before any finalize or checkpoint step.
- Treat hard validation as blocking and soft validation as warning-only.
- Treat `.local/tmp/code-review/` as scratch only.
- Reject legacy v1 session, report, packet, and proof-packet assumptions. Start a fresh v2 session instead.
- Prefer explicit CLI flags such as `--session-dir`, `--reviewer-id`, `--artifact-file`, and `--role`.

## Reviewer and full-cycle guidance
- Reviewer and full-cycle runs cover the full canonical review roster every time: language-detector, one language-research worker per detected language, one domain-reviewer per canonical module, and final-synthesis.
- Each reviewer owns one agent directory, one full `report.md`, one local ledger, and zero or more child helpers beneath `children/<child-id>/...`.
- Parent reviewers claim scope before delegating. Child helpers must not re-run the same investigation slice.
- Final synthesis is recursive: concatenate descendant reports in stable order, then preserve counts from machine artifacts rather than prose.
- `references/reviewer-artifact-examples.md` contains canonical reviewer artifact examples for manual `validate` / `finalize` flows.

## Applicator guidance
- Challenge every finding for anchor quality, scenario realism, duplication, actionability, already-addressed status, and evidence strength before applying it.
- Stop cleanly on low-signal, duplicate, non-actionable, already-fixed, or already-addressed findings after recording the reason.
- Use `mpcr applicator set-status`, `mpcr applicator finalize --artifact-file <application_result>`, and `mpcr applicator verify --artifact-file <verification_result>` to drive application and verification state.

## Full-cycle guidance
- Use `mpcr fullcycle plan`, `mpcr fullcycle checkpoint --artifact-file <convergence_state>`, and `mpcr fullcycle state` to manage reopen logic.
- Reopen only when challenged findings remain high-signal and materially unresolved.
- Use `mpcr session metrics` when grouped precision or convergence detail is needed.

## Skills debugging: error accumulation log
At the start of each top-level invocation, create one log file for this skill.

- Unix path: `/tmp/skill-errors/code-review/<yyyy-mm-dd>/<HH-MM-SS>_errors.md`
- Windows path: `%TEMP%\\skill-errors\\code-review\\<yyyy-mm-dd>\\<HH-MM-SS>_errors.md`

Log skill-caused friction only: documentation drift, policy lookup mismatches, wrapper issues, missing generated fallback docs, or CLI behavior that contradicts the intended code-review workflow. Do not log user-project build or test failures.

## Reference index (CLI unavailable fallback)
Use these only when `mpcr protocol ...` cannot run.

| File | When to read |
| --- | --- |
| `<skills-file-root>/references/reviewer-fallback.md` | Reviewer mode fallback |
| `<skills-file-root>/references/reviewer-artifact-examples.md` | Canonical reviewer artifact examples for manual `validate` / `finalize` flows |
| `<skills-file-root>/references/applicator-fallback.md` | Applicator mode fallback |
| `<skills-file-root>/references/fullcycle-fallback.md` | Full-cycle fallback |
| `<skills-file-root>/references/orchestrator-fallback.md` | Routing, dispatch, and policy-load fallback |
