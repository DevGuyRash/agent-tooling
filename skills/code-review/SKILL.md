---
name: code-review
description: Perform and apply code reviews (UACRP + application protocol) and coordinate artifacts via mpcr.
compatibility: Requires a POSIX shell. If `<skills-file-root>/scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `<skills-file-root>/scripts/mpcr-src`.
---

# Code Review

Two workflows: **Reviewer** (perform adversarial code review) and **Applicator** (apply review feedback).

Both use the `mpcr` CLI at `<skills-file-root>/scripts/mpcr` for session coordination.

## Workflow selection

You SHALL infer the workflow from context. You SHALL NOT ask the user which workflow to use.

- WHEN a diff, PR/MR, patch, or uncommitted changes are present → you SHALL use **Reviewer**.
- WHEN a review report exists or the user references review findings → you SHALL use **Applicator**.
- WHEN both reviewing AND applying → you SHALL run **Reviewer** first, then **Applicator**.
- IF genuinely ambiguous (e.g., both a report and uncommitted changes exist) → you SHALL ask ONE clarifying question.

## Getting started

`mpcr protocol` serves phase-appropriate guidance so you never need to hold the full protocol in context. You SHALL run it at each phase transition.

### Reviewer

1. Register: `mpcr reviewer register --target-ref <REF>`
2. For each phase, get guidance: `mpcr protocol reviewer --phase <PHASE>`
   - Phases: `INGESTION` → `DOMAIN_COVERAGE` → `THEOREM_GENERATION` → `ADVERSARIAL_PROOFS` → `SYNTHESIS` → `REPORT_WRITING`
3. You SHALL update progress at each phase: `mpcr reviewer update --status IN_PROGRESS --phase <PHASE>`
4. Get report template: `mpcr protocol report-template --scale compact|standard|full`
   - compact: <100 line diffs, single concern
   - standard: medium changes
   - full: large or high-risk changes
5. You SHALL finalize: `mpcr reviewer finalize --verdict APPROVE|REQUEST_CHANGES|BLOCK --report-file report.md`

### Applicator

1. Ingest reports: `mpcr session reports closed --include-report-contents`
2. For each phase, get guidance: `mpcr protocol applicator --phase <PHASE>`
   - Phases: `INGESTION` → `DISPOSITION` → `APPLICATION` → `FINALIZATION`
3. You SHALL record dispositions: `mpcr applicator note --note-type applied|declined|deferred --content "..."`
4. You SHALL set status: `mpcr applicator set-status --initiator-status RECEIVED|REVIEWED|APPLYING|APPLIED`

## Multi-agent orchestration

You SHALL use multi-agent mode WHEN the diff exceeds 500 lines or the user requests it. For most reviews, single-agent is sufficient.

WHEN using multi-agent:
1. Get orchestration guidance: `mpcr protocol orchestrator`
2. Get dispatch templates: `mpcr protocol dispatch --role scope-mapper|red-team|systems-auditor`
3. Spawn children: `mpcr reviewer spawn-children --parent-id <ID> --count N`

## Autonomous operation

You SHALL resolve context WITHOUT asking the user:
- Target ref: infer from current branch. WHEN a git hosting CLI is available (e.g., `gh`, `glab`), you SHALL check for associated PRs/MRs.
- Acceptance criteria: derive from PR/MR description, commit messages, or diff content. Mark [Assumed] if inferred.
- PR/MR/issue context: check silently. IF found, use it. IF not, proceed with the diff.
- Parallelism: default to single-agent unless the diff is large or user requests otherwise.

You SHALL only ask the user IF you are genuinely blocked (e.g., cannot determine what code to review).

## Reference documents (fallback)

IF `mpcr protocol` is unavailable, you SHALL read these files directly:
- Reviewer: `<skills-file-root>/references/reviewer-protocol.md`
- Applicator: `<skills-file-root>/references/applicator-protocol.md`
- Domains: `mpcr protocol domains` (or see the domains table in the reviewer protocol)
