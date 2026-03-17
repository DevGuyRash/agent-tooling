---
name: Skill Auditor
description: >-
  Audit a skill's packaging, trigger behavior, task leverage, context design,
  verification loop, and AGENTS.md adherence, then produce a concise Skill
  Improvement Brief. Use when the task involves: (1) Auditing or self-auditing
  a skill for quality or correctness, (2) Health-checking a skill's trigger
  reliability or context efficiency, (3) Evaluating whether a skill belongs as
  a skill, AGENTS.md entry, explicit prompt, or tool, (4) Reviewing or revising
  a skill's packaging, descriptions, or references, or (5) Any task requiring
  structured skill evaluation with concrete improvement checks.
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
`references/profile-rules.md`.
WHEN you need reusable repair ideas THEN you MAY read
`references/improvement-patterns.md`.
You SHALL format the default deliverable with
`references/output-contract.md`.

## Default Leverage Order

You SHALL use this default order unless a downstream failure is obviously the
dominant blocker:

1. Packaging fit
2. Trigger fit
3. Task fit
4. Context fit
5. Verification fit

## Choose The Primary Question

- Packaging fit → `references/packaging-fit.md`
- Trigger fit → `references/trigger-evals.md`
- Task fit → `references/task-evals.md`
- Context fit → `references/context-redesign.md`
- Verification fit → `references/verification-loop.md`

WHEN the target may belong in `AGENTS.md`, custom instructions, an explicit
prompt surface, an MCP-backed workflow, or a tool THEN you SHALL use packaging
fit.
WHEN the skill activates at the wrong times or misses obvious prompts THEN you
SHALL use trigger fit.
WHEN the skill triggers but does not improve task completion THEN you SHALL use
task fit.
WHEN the skill loads too much context or hides key steps THEN you SHALL use
context fit.
WHEN success, retries, or regression checks are unclear THEN you SHALL use
verification fit.

## Direct References

- Output contract → `references/output-contract.md`
- Profile rules → `references/profile-rules.md`
- Improvement patterns → `references/improvement-patterns.md`

## Default Workflow

You SHALL gather only the smallest evidence set needed for the current
question.
WHEN the packaging verdict is `MIGRATE_TO_AGENTS`,
`MIGRATE_TO_EXPLICIT_PROMPT`, `MIGRATE_TO_TOOL`, or `HYBRID_RECOMMENDED` THEN
you SHALL stop optimizing the target as a standalone skill and you SHALL return
migration guidance plus verification.
WHEN the packaging verdict is `KEEP_AS_SKILL` or `REWORK_AS_SKILL` THEN you
SHALL continue only until the leading bottleneck and next verification step are
clear unless the user explicitly asks for a full reboot or end-to-end revision.
WHEN the user asks for a full reboot or end-to-end revision AND the first
brief reveals a second bottleneck THEN you MAY load one additional direct
reference at a time only as needed.
WHEN the user asks for a full reboot or end-to-end revision THEN you MAY
answer multiple questions, one at a time, in leverage order.
You SHALL keep the default output concise enough for a human maintainer to act
on without appendices.
You SHALL NOT require a router CLI, a phase/domain matrix, or heuristic lint
gates for normal use.

## Deterministic Helpers

WHEN structural evidence helps THEN you MAY run one or more of these helpers:

- `scripts/frontmatter_check.sh`
- `scripts/reference_check.sh`
- `scripts/script_sanity.sh`

WHEN reasoning alone answers the question well enough THEN you SHALL NOT run
scripts just to satisfy the workflow.
WHEN helpers do not add deterministic leverage THEN you SHALL skip them.
