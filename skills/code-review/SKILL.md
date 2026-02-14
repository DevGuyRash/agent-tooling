---
name: code-review
description: Perform and apply code reviews (UACRP + application protocol) and coordinate artifacts via mpcr.
compatibility: Requires a POSIX shell. If `<skills-file-root>/scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `<skills-file-root>/scripts/mpcr-src`.
---

# Code Review

Two workflows: **Reviewer** (perform adversarial code review) and **Applicator** (apply review feedback).

Both use the `mpcr` CLI at `<skills-file-root>/scripts/mpcr` for session coordination.

## Role modes (HIGHEST PRIORITY)

You SHALL determine your role mode BEFORE choosing Reviewer vs Applicator workflow.

### WORKER (subagent) mode

IF the incoming prompt includes any of:
- `## Proof Packet:`
- `MPCR_DISPATCH_ROLE=`
- explicit instruction that you are a subagent or worker

THEN you are in WORKER mode.

In WORKER mode:
- You SHALL NOT run any `mpcr` commands (`register`, `update`, `note`, `finalize`, or session mutations).
- You SHALL NOT run repo-wide `git diff` or `git show` patch commands.
- You SHALL review ONLY the assigned files and minimal surrounding context needed for proof.
- You SHALL return EXACTLY one Proof Packet and NOTHING else.

### ORCHESTRATOR (multi-agent coordinator) mode

WHEN multi-agent mode is enabled (diff > 500 lines OR the user requests multi-agent)
AND you are not in WORKER mode,
THEN you are the ORCHESTRATOR.

In ORCHESTRATOR mode:
- You SHALL follow `mpcr protocol orchestrator`.
- You SHALL NOT fetch or print full patch diffs. You MAY only use diff summary commands.
- You SHALL NOT perform proofs yourself; workers do.
- You SHALL dispatch workers with assigned file lists and focus areas, not full diffs or full files.
- You SHALL send workers a fresh, minimal prompt; you SHALL NOT forward full conversation history.

## Token / context discipline (all modes)

- You SHALL NOT paste raw diffs into chat unless explicitly requested by the user.
- You SHALL treat large tool outputs as toxic and prefer narrow commands (`--stat`, `--name-only`, `--numstat`, `head`, `sed -n`).
- When quoting code, you SHALL keep excerpts to <= 12 lines and <= 3 excerpts total.
- In multi-agent mode, worker prompts SHALL include scope and acceptance criteria only, not repository-wide context.

## Workflow selection

You SHALL infer the workflow from context. You SHALL NOT ask the user which workflow to use.

- WHEN a diff, PR/MR, patch, or uncommitted changes are present → you SHALL use **Reviewer** (unless WORKER or ORCHESTRATOR mode applies).
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
3. Spawn children: `mpcr reviewer spawn-children --parent-id <ID> --session-id <SID> --target-ref <REF> --count N`

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
