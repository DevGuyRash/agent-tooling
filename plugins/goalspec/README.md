# GoalSpec Plugin

GoalSpec is a Codex and Claude plugin package that turns messy intent — broad
project context, PRDs, logs, issues, and existing goal notes — into bounded,
verifiable, stoppable goal contracts.

Doctrine:

> **Open-world discovery. Closed-world execution.**

Discover broadly, compile narrowly, execute ONE finite frozen contract, verify
externally, record follow-ups, stop. GoalSpec is meant to feed a bounded
execution loop, not replace one. Its core is one primary skill
(`$authoring-goals`); the plugin container bundles hooks, deterministic helper
scripts, templates, and `.goals/` artifacts.

## What this package contains

```text
goalspec/
  .codex-plugin/plugin.json              Codex plugin manifest
  .claude-plugin/plugin.json             Claude plugin manifest
  skills/authoring-goals/SKILL.md        primary skill, invoked as $authoring-goals
  skills/authoring-goals/references/     doctrine, schema, rubric, hooks policy, workflows
  skills/authoring-goals/assets/         templates (current, provenance, campaign, ...), AGENTS snippet
  skills/authoring-goals/scripts/        deterministic helpers + the goalspec.py wrapper CLI
  hooks/hooks.json                       lifecycle hook bundle
  hooks/scripts/                         prompt/scope/evidence/stop guards + conformance probe
  tests/                                 fast smoke test and fixtures
```

## Key invariants

- **The verifier is the oracle.** `audit_goal.py` only reports `achieved` when a
  machine-readable `goalspec.verifier.v1` result file (written by
  `run_verifiers.py --run`) shows the verifier passed — plus required report
  sections and a matching contract hash. Report headings and a non-empty evidence
  directory are necessary but never sufficient.
- **Freeze gate.** `render_goal.py` refuses to project an unlocked or
  hash-mismatched `current.md` into a `/goal` (use `--allow-unlocked` only to
  preview). Hooks are defense-in-depth; this refusal plus the audit hash are the
  freeze backstop.
- **Provenance is not execution scope.** The verbatim request is stored in
  `.goals/provenance/` (reference only); `current.md` carries only a pointer, and
  the rendered `/goal` excludes the raw request.

## Initialize a project

After installing and trusting the plugin, scaffold artifacts from the repo root:

```bash
python3 plugins/goalspec/skills/authoring-goals/scripts/goalspec.py init --append-agents-md
```

This creates `.goals/` (including `provenance/` and `evidence/`), templates, and
appends evidence-ignore rules to `.gitignore`. Hooks require a trust review in
the host (`/hooks`) before they run.

## Evidence & secrets

`.goals/evidence/` captures raw tool input/output and runtime state
(`run_state.json`) for auditing. Secrets matching common patterns
(`Authorization: Bearer`, `*_API_KEY=`, `password=`, `token=`, `secret=`) are
redacted best-effort and oversized output is truncated
(`GOALSPEC_EVIDENCE_MAX_BYTES`, default 16 KB) — but **evidence may still contain
sensitive raw output**. `init` gitignores `.goals/evidence/` and
`.goals/run_state.json` by default; keep evidence local and do not paste it
outside the project. `.goals/reports/` is the reviewable summary and stays
tracked.
