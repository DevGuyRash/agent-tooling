---
name: skill-auditor
description: >-
  Evaluate whether a target capability is correctly packaged as a skill,
  improve its trigger behavior, task leverage, context design, and
  verification loop, and produce a concise Skill Improvement Brief with
  actionable changes and checks. Use when reviewing or revising a skill, not
  when enforcing a large lint taxonomy or rebuilding a router CLI.
---

# Skill Auditor

`skill-auditor` is an eval-driven skill improver. It answers five questions:
packaging fit, trigger fit, task fit, context fit, and verification fit. The
default product is a short Improvement Brief, not a long audit report.

## Start Here

You SHALL read the target skill's `SKILL.md` before loading other target files.
You SHALL decide which of the five improvement questions is primary.
WHEN the request is ambiguous THEN you SHALL start with packaging fit.
You SHALL read at most one question-specific reference file before drafting the
first brief.
WHEN you need profile-specific interpretation THEN you SHALL read
`<skills-file-root>/references/profile-rules.md`.
WHEN you need reusable repair ideas THEN you MAY read
`<skills-file-root>/references/improvement-patterns.md`.
You SHALL format the default deliverable with
`<skills-file-root>/references/output-contract.md`.

## Choose The Primary Question

- Packaging fit → `<skills-file-root>/references/packaging-fit.md`
- Trigger fit → `<skills-file-root>/references/trigger-evals.md`
- Task fit → `<skills-file-root>/references/task-evals.md`
- Context fit → `<skills-file-root>/references/context-redesign.md`
- Verification fit → `<skills-file-root>/references/verification-loop.md`

WHEN the target may belong in `AGENTS.md`, custom instructions, an explicit
prompt surface, or a tool THEN you SHALL use packaging fit.
WHEN the skill activates at the wrong times or misses obvious prompts THEN you
SHALL use trigger fit.
WHEN the skill triggers but does not improve task completion THEN you SHALL use
task fit.
WHEN the skill loads too much context or hides key steps THEN you SHALL use
context fit.
WHEN success, retries, or regression checks are unclear THEN you SHALL use
verification fit.

## Direct References

- Output contract → `<skills-file-root>/references/output-contract.md`
- Profile rules → `<skills-file-root>/references/profile-rules.md`
- Improvement patterns → `<skills-file-root>/references/improvement-patterns.md`

## Default Workflow

You SHALL gather only the smallest evidence set needed for the current
question.
WHEN the packaging verdict is `MIGRATE_TO_AGENTS`,
`MIGRATE_TO_EXPLICIT_PROMPT`, `MIGRATE_TO_TOOL`, or `HYBRID_RECOMMENDED` THEN
you SHALL stop optimizing the target as a standalone skill and you SHALL return
migration guidance plus verification.
WHEN the packaging verdict is `KEEP_AS_SKILL` or `REWORK_AS_SKILL` THEN you
SHALL continue to the next highest-leverage question.
WHEN the user asks for a full reboot or end-to-end revision THEN you MAY answer
multiple questions, one at a time, in leverage order.
You SHALL keep the default output concise enough for a human maintainer to act
on without appendices.
You SHALL NOT require a router CLI, a phase/domain matrix, or heuristic lint
gates for normal use.

## Deterministic Helpers

WHEN structural evidence helps THEN you MAY run one or more of these helpers:

- `<skills-file-root>/scripts/frontmatter_check.sh`
- `<skills-file-root>/scripts/reference_check.sh`
- `<skills-file-root>/scripts/script_sanity.sh`

WHEN reasoning alone answers the question well enough THEN you SHALL NOT run
scripts just to satisfy the workflow.
