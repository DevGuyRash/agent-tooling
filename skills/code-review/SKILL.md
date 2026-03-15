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

Run `mpcr route --mode <reviewer|applicator|full-cycle> --target-ref <ref-string> --execution-capability <single_process|bounded_helpers|parallel_subagents> --max-worker-count <n> --orchestrator-read-budget-lines <n> --orchestrator-read-budget-snippets <n> [--changed-file <path>]... [--public-interface <path>]... [--behavior-facing-artifact <path>]...` before loading detailed guidance. `target-ref` is an opaque session key: a branch name, commit SHA, or literal `HEAD` all work as long as every later command reuses the exact same string for that session.

Use `mpcr route --persist ...` whenever the task needs session-visible routing, reviewer registration, recursive child directories, or later `protocol dispatch` lookups.

Prefer `parallel_subagents` whenever helpers are available so routed workers, not the orchestrator, perform most first-hand exploration.

For a fresh isolated session, prefer an unused canonical date leaf via `--repo-root <path> --date <yyyy-mm-dd>` or the matching canonical session dir under `.local/reports/code_reviews/YYYY-MM-DD`. One canonical date leaf holds one session. If that leaf already belongs to a different `target-ref`, pick another date or run `mpcr session cleanup --session-dir <path>` before rerouting. For existing sessions, reuse the exact `persisted.session_dir` and the same `target-ref` string for all later route, dispatch, reviewer, applicator, and full-cycle steps; do not point `--session-dir` at scratch or ad hoc directories.

After routing:
- Use `mpcr protocol mode --mode <reviewer|applicator|full-cycle> --view checklist` for the top-level mode contract.
- Keep the orchestrator thin. Treat `route_decision.worker_plan.role_id` as the worker roster to register or spawn.
- For reviewer/full-cycle runs, bootstrap with `mpcr reviewer register --target-ref <same-exact-ref> --session-dir <persisted.session_dir>` to create the orchestration anchor. Prefer `mpcr reviewer spawn-routed --parent-id <root-reviewer-id> --session-dir <persisted.session_dir>` to materialize every missing routed worker from the current `route_decision.worker_plan`; use `mpcr reviewer spawn-children` only when you need to replay or hand-materialize an individual worker with explicit `role_id`, `worker_kind`, `module_ids`, `focus_surfaces`, `claimed_scope`, and `delegated_scope`.
- Register one root reviewer ledger, then spawn every required worker in `route_decision.worker_plan` before synthesis. The orchestrator coordinates, challenges, and checkpoints; it does not absorb sibling worker scope.
- `mpcr reviewer register` creates only the root orchestration anchor. It does not accept per-worker role flags; routed worker roles belong in `spawn-routed` / `spawn-children`.
- For every active worker, load `mpcr protocol dispatch --role <role> --session-dir <path> [--reviewer-id <id>] --view checklist`. The root reviewer ID is only the orchestration anchor; use the current worker's `reviewer_id` for session-bound prompts instead of the unbound discovery view.
- When a worker has its dispatch prompt, follow that dispatch plus the referenced packs instead of re-reading this whole skill body.
- Use static `mpcr protocol worker --kind <kind>`, `mpcr protocol module --id <id>`, or `mpcr protocol escalation --id <id>` lookups only for discovery, fallback, or narrow troubleshooting.

## Wrapper behavior
`<skills-file-root>/scripts/mpcr` auto-builds the Rust binary in `<skills-file-root>/scripts/mpcr-src/target/release/mpcr`.

If the release binary is missing or stale, the wrapper runs `cargo build --manifest-path <skills-file-root>/scripts/mpcr-src/Cargo.toml --locked --release`.

If `cargo` is unavailable and the binary is missing, the wrapper fails with a concise Rust-toolchain error.

## Universal rules
- Machine artifacts are canonical truth. Each agent directory must finish with a full `report.md` explanatory companion; `mpcr reviewer complete-child` and `mpcr reviewer finalize` render one from the stored artifact when you do not author it separately.
- Keep `findings[].anchors` repo-relative (`path:line` or `path:start-end`). Cite PR threads, API docs, specs, and web sources in `report.md`, then tie them back to anchored repo evidence before escalating a claim.
- `_session.json` is the primary session ledger. `_session.toml` is the mirror when TOML writes succeed.
- Canonical machine artifacts live under `.local/reports/code_reviews/YYYY-MM-DD/artifacts/...`.
- Render canonical artifact markdown with `mpcr render --artifact-file <path> --format markdown`.
- Retrieve descendant report trees with `mpcr session reports --recursive`; omit `--recursive` only when you want the root summary entries alone.
- Retrieve flat artifact inventory with `mpcr session artifacts`.
- Discard stale canonical session leaves with `mpcr session cleanup --session-dir <path>` before reruns; confirm the reports tree is either empty or the exact session you intend to reuse.
- Run `mpcr validate --artifact-file <path> --kind <artifact_kind> --layer hard` before any finalize or checkpoint step.
- CLI `--kind` accepts the stored snake_case spellings and kebab-case aliases: `child_findings`/`child-findings`, `parent_review`/`parent-review`, `application_result`/`application-result`, `verification_result`/`verification-result`, and `convergence_state`/`convergence-state`.
- Treat hard validation as blocking and soft validation as warning-only.
- Treat `.local/tmp/code-review/` as scratch only.
- Reject legacy v1 session, report, packet, and proof-packet assumptions. Start a fresh v2 session instead.
- Prefer explicit CLI flags such as `--session-dir`, `--reviewer-id`, `--artifact-file`, and `--role`.

## Reviewer and full-cycle guidance
- Reviewer and full-cycle runs cover the full canonical review roster every time: language-detector, one language-research worker per detected language, one domain-reviewer per canonical module, and the `final-synthesis` dispatch role (`final-synthesizer` worker policy).
- Each reviewer owns one agent directory, one full `report.md`, one local ledger, and zero or more child helpers beneath `children/<child-id>/...`.
- Parent reviewers claim scope before delegating. Child helpers must not re-run the same investigation slice.
- Before escalating a finding, trace both the introducing path and the downstream effect or closure path. Reject suspicions that a later guard, normalization step, rollback, dedupe, retry path, or caller behavior already neutralizes.
- Final synthesis is recursive: concatenate descendant reports in stable order, then preserve counts from machine artifacts rather than prose.
- `references/reviewer-artifact-examples.md` contains canonical reviewer artifact examples for manual `validate` / `finalize` flows.

## Applicator guidance
- Challenge every finding for anchor quality, scenario realism, duplication, actionability, already-addressed status, and evidence strength before applying it.
- Challenge both sides of the claim before accepting it: the introducing path and the downstream effect or closure path. Decline findings when later guards, normalization, rollback, dedupe, retries, or caller behavior already neutralize them.
- Drive every routed finding to `applied` or a categorical decline. Stop on low-signal, duplicate, non-actionable, already-fixed, or already-addressed findings only after recording the reason.
- Finish only after `application_result` and `verification_result` are finalized and any unresolved items are carried forward explicitly.
- `verification_result` must cover exactly the finding IDs listed in `application_result.verification_needed`; partial or failed verification keeps the applicator blocked.
- Use `mpcr applicator set-status`, `mpcr applicator finalize --artifact-file <application_result>`, and `mpcr applicator verify --artifact-file <verification_result>` to drive application and verification state.

## Full-cycle guidance
- Use `mpcr fullcycle plan`, `mpcr fullcycle checkpoint --artifact-file <convergence_state>`, and `mpcr fullcycle state` to manage reopen logic. `mpcr fullcycle plan --output <file>.json` writes JSON; other outputs default to TOML.
- Run `mpcr fullcycle plan` only after the session has finalized a current `parent_review`; `application_result` and `verification_result` refine convergence once the applicator phase has run, but convergence planning is not a substitute for the review/apply/verify cycle itself.
- If the state says `reopen_required`, continue into the next routed cycle. Stop only when the state is converged or the one allowed terminal cleanup pass is the only work left.
- Reopen only when challenged findings remain high-signal, materially unresolved, and still survive both the introducing path and the downstream effect or closure path after application and verification are considered.
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
