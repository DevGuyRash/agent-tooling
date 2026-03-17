---
name: Code Review
description: >-
  Run recursive, machine-first code review, review application, and full-cycle
  convergence workflows with the `mpcr` CLI. Use when the task involves:
  (1) Reviewing a diff, pull request, or set of commits, (2) Applying
  structured review findings back to code, (3) Validating canonical review
  artifacts or report trees, (4) Driving review→apply→verify convergence
  loops, or (5) Any task requiring systematic, multi-pass code review with
  per-agent report trees.
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

## Role detection

IF your prompt includes dispatch markers (assigned scope, `reviewer_id`
bindings, `MPCR_DISPATCH_ROLE`) THEN you SHALL follow the dispatch prompt
only; you SHALL NOT run orchestrator commands (`register`, `spawn-routed`,
`finalize`).

ELSE you SHALL follow Bootstrap below as the orchestrator.

## Bootstrap
Infer the mode from the user request first.

Run `mpcr route --mode <reviewer|applicator|full-cycle> --target-ref <ref-string> --execution-capability <single_process|bounded_helpers|parallel_subagents> --max-worker-count <n> --orchestrator-read-budget-lines <n> --orchestrator-read-budget-snippets <n> [--changed-file <path>]... [--public-interface <path>]... [--behavior-facing-artifact <path>]...` before loading detailed guidance. `target-ref` is an opaque session key: a branch name, commit SHA, or literal `HEAD` all work as long as every later command reuses the exact same string for that session.

Use `mpcr route --persist ...` whenever the task needs session-visible routing, reviewer registration, recursive child directories, or later `protocol dispatch` lookups.

Prefer `parallel_subagents` whenever helpers are available so routed workers, not the orchestrator, perform most first-hand exploration.

For a fresh isolated session, prefer an unused canonical date leaf via `--repo-root <path> --date <yyyy-mm-dd>` or the matching canonical session dir under `.local/reports/code_reviews/YYYY-MM-DD`. One canonical date leaf holds one session. If that leaf already belongs to a different `target-ref`, pick another date or run `mpcr session cleanup --session-dir <path>` before rerouting. For existing sessions, reuse the exact `persisted.session_dir` and the same `target-ref` string for all later route, dispatch, reviewer, applicator, and full-cycle steps; do not point `--session-dir` at scratch or ad hoc directories.

After routing, you SHALL read `<skills-file-root>/references/execution-playbook.md`
and follow the section for your mode (Reviewer, Applicator, or Full-cycle).

You MAY use `mpcr protocol mode --mode <reviewer|applicator|full-cycle> --view checklist`
for supplementary policy constraints during execution.

You MAY load `mpcr protocol dispatch --role <role> --session-dir <path> [--reviewer-id <id>] --view checklist`
for worker-specific prompts; load `mpcr protocol dispatch --role orchestrator-root` for the
thin coordination rules. Use the current worker's `reviewer_id` for session-bound dispatch.

You MAY use static `mpcr protocol worker --kind <kind>`, `mpcr protocol module --id <id>`,
or `mpcr protocol escalation --id <id>` lookups for discovery, fallback, or narrow
troubleshooting.

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

## Reviewer, applicator, and full-cycle guidance

You SHALL follow `<skills-file-root>/references/execution-playbook.md` for
the complete procedure for each mode.

The following constraints apply universally across all modes:

- Each reviewer owns one agent directory, one full `report.md`, one local
  ledger, and zero or more child helpers beneath `children/<child-id>/...`.
- Parent reviewers SHALL claim scope before delegating. Child helpers SHALL
  NOT re-run the same investigation slice.
- Register the root anchor with `mpcr reviewer register --target-ref <same-exact-ref> --session-dir <persisted.session_dir>`, then prefer `mpcr reviewer spawn-routed` to materialize workers; use `mpcr reviewer spawn-children` only for targeted manual replay.
- Before escalating a finding, trace both the introducing path and the downstream effect or closure path. Reject claims that later guards already neutralize.
- Before a finding becomes canonical, run a 3-voter legitimacy gate. Only findings with 2-of-3 `legitimate` votes proceed. Record rejected findings with `mpcr reviewer note` or `mpcr applicator note`.
- The reviewer roster includes the `final-synthesis` dispatch role (`final-synthesizer` worker policy).
- `references/reviewer-artifact-examples.md` contains canonical reviewer
  artifact examples for manual `validate` / `finalize` flows.
- `verification_result` SHALL cover exactly the finding IDs listed in
  `application_result.verification_needed`; partial or failed verification
  keeps the applicator blocked.
- Use `mpcr fullcycle plan`, `mpcr fullcycle checkpoint`, and `mpcr fullcycle state` for convergence management.
- Use `mpcr session metrics` when grouped precision or convergence detail
  is needed.

## Skills debugging: error accumulation log
At the start of each top-level invocation, create one log file for this skill.

- Unix path: `/tmp/skill-errors/code-review/<yyyy-mm-dd>/<HH-MM-SS>_errors.md`
- Windows path: `%TEMP%\\skill-errors\\code-review\\<yyyy-mm-dd>\\<HH-MM-SS>_errors.md`

Log skill-caused friction only: documentation drift, policy lookup mismatches, wrapper issues, missing generated fallback docs, or CLI behavior that contradicts the intended code-review workflow. Do not log user-project build or test failures.

## Reference index

You SHALL load only the reference needed for the current step.

| File | When to read |
| --- | --- |
| `<skills-file-root>/references/execution-playbook.md` | After routing — primary execution procedure |
| `<skills-file-root>/references/orchestrator-fallback.md` | Orchestrator policy WHEN `mpcr protocol` unavailable |
| `<skills-file-root>/references/reviewer-fallback.md` | Reviewer policy WHEN `mpcr protocol` unavailable |
| `<skills-file-root>/references/applicator-fallback.md` | Applicator policy WHEN `mpcr protocol` unavailable |
| `<skills-file-root>/references/fullcycle-fallback.md` | Full-cycle policy WHEN `mpcr protocol` unavailable |
| `<skills-file-root>/references/reviewer-artifact-examples.md` | Manual `validate` / `finalize` flows |
