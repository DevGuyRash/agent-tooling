---
name: code-review
description: >-
  Perform and apply adversarial code reviews via parallel subagent orchestration
  and coordinate artifacts via mpcr. Use when the task involves: (1) Reviewing
  code changes, diffs, or pull requests for quality and correctness,
  (2) Applying code review feedback to a codebase, (3) Running a full-cycle
  review (review then apply fixes in one pass), (4) Generating structured code
  review reports, (5) Performing security-focused or adversarial code audits,
  or (6) Any task where code needs to be critically reviewed before merging.
  Supports reviewer, applicator, and full-cycle modes.
compatibility: Requires a POSIX shell. If `<skills-file-root>/scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `<skills-file-root>/scripts/mpcr-src`.
---

# Code Review

Three invocation modes: **Reviewer**, **Applicator**, and **Full-cycle** (reviewer → applicator in one pass).
All coordinate via the `mpcr` CLI at `<skills-file-root>/scripts/mpcr`.

## Invocation aliases (HIGHEST PRIORITY)

You SHALL recognize these user prompts as skill triggers:

| User says (case-insensitive) | Mode |
|------------------------------|------|
| `code-review reviewer [ctx]` | Reviewer only |
| `code-review review [ctx]` | Reviewer only |
| `code-review applicator [ctx]` | Applicator only |
| `code-review apply [ctx]` | Applicator only |
| `code-review full-cycle [ctx]` | Full-cycle |
| `code-review full [ctx]` | Full-cycle |
| `code-review auto [ctx]` | Full-cycle |
| `code-review [ctx]` (no keyword) | Infer from context (see Workflow Selection) |

`[ctx]` is optional additional context the user provides (e.g., file paths, PR links, focus areas).
You SHALL pass `[ctx]` through to the appropriate workflow as additional scope constraints.

## Execution model

You are an orchestrator by default. Worker mode (see below) takes precedence when triggered.

- **Single-agent mode** (diff ≤ 500 lines AND user did not request multi-agent): you SHALL spawn exactly ONE worker subagent and wait for its result. You do not review code yourself.
- **Multi-agent mode** (diff > 500 lines OR user requests it): you SHALL spawn multiple specialist workers in parallel.
- **Subagent fallback**: IF the runtime cannot spawn subagents, you SHALL perform the review yourself using `mpcr protocol reviewer` phase-by-phase.
- **Concurrency cap**: you SHALL run at most 8 parallel subagents (explorers + reviewers + applicators combined). WHEN 8 are running, you SHALL wait for one to finish before launching another.
- In orchestrator modes you coordinate, dispatch, validate, synthesize, and finalize. You do NOT read code, generate theorems, attempt disproofs, write findings, or apply patches.

## Role detection (precedence: WORKER > ORCHESTRATOR)

### WORKER (subagent) mode

IF the incoming prompt includes any of:
- `## Proof Packet:`
- `MPCR_DISPATCH_ROLE=`
- `MPCR_APPLICATOR_ROLE=`
- explicit instruction that you are a subagent or worker

THEN you are in WORKER mode:
- You SHALL run only child-scoped `mpcr` commands for your assigned identity.
- You SHALL include worker identity bindings in your execution context: `MPCR_REVIEWER_ID`, `MPCR_SESSION_ID`, and `MPCR_SESSION_DIR`.
- You SHALL NOT run `mpcr reviewer register`, `spawn-children`, `complete-child`, or parent `finalize`.
- You SHALL NOT run repo-wide `git diff` or `git show`.
- You SHALL work ONLY within your assigned scope.
- You SHALL return EXACTLY the output format specified in your dispatch prompt.

### ORCHESTRATOR mode

WHEN you are NOT in WORKER mode, you are the ORCHESTRATOR:
- You SHALL follow `mpcr protocol orchestrator`.
- You SHALL NOT read code files. You MAY only use diff summary commands (`--stat`, `--name-only`, `--numstat`).
- You SHALL NOT generate theorems, attempt disproofs, write findings, or apply patches.
- You SHALL dispatch all work to subagents and synthesize their results.

## Token / context discipline (all modes)

- You SHALL NOT paste raw diffs unless explicitly requested by the user.
- You SHALL treat large tool outputs as toxic; prefer `--stat`, `--name-only`, `--numstat`, `head`, `sed -n`.
- Code excerpts: ≤ 12 lines, ≤ 3 excerpts total.
- Worker prompts: scope + acceptance criteria only. No repo-wide context, no conversation history.

## Artifact hygiene

The code-review skill SHALL NOT leave scratch files in the user's worktree.

- You SHALL NOT write dispatch prompts, report templates, test lists, or working files to the repo root or any directory outside `.local/tmp/`.
- IF you must write intermediate files (dispatch prompts, draft reports, packet files), you SHALL write them under `.local/tmp/` and you SHALL delete them when the workflow completes.
- `mpcr reviewer finalize --report-file` moves the report into `.local/reports/`; you SHALL NOT leave a copy behind unless `--copy-report-input` is explicitly passed.
- You SHALL pipe report markdown via stdin to `mpcr reviewer finalize` instead of writing temporary report files when possible.
- AFTER the reviewer workflow completes (finalize succeeds), the orchestrator SHALL delete `.local/tmp/` if it exists.
- AFTER the applicator workflow completes (status set to APPLIED), the orchestrator SHALL delete `.local/tmp/` if it exists.
- You SHALL NOT write files with names like `selected_tests.txt`, `report.md`, or any other scratch artifact to the repo root.
- WHEN running AGENTS.md verification commands (Phase 2 scans, `cargo test`, etc.), you SHALL NOT redirect output to files in the worktree. Capture output in your context or pipe to `/dev/null`.

IF `.local/tmp/` exists at the start of a workflow, you MAY clean it up after confirming no other agent is using it.
The `.local/` directory itself is gitignored in this repo, but consumers of this skill may not have it in their `.gitignore`.


## Workflow selection

WHEN the user provides an explicit invocation alias → use that mode.
OTHERWISE you SHALL infer the workflow. You SHALL NOT ask the user which workflow to use.

- WHEN a diff, PR/MR, patch, or uncommitted changes are present → **Reviewer**.
- WHEN a review report exists or the user references review findings → **Applicator**.
- WHEN both conditions apply → **Full-cycle** (Reviewer then Applicator).
- IF genuinely ambiguous → ask ONE clarifying question.

## Subagent tiers

The system uses three subagent tiers. Any tier may spawn explorers.

### Explorer subagents

Explorers gather context. They do NOT review, produce findings, or apply patches.
- The orchestrator SHALL spawn explorer subagents to pre-digest code context before dispatching reviewers.
- Reviewer and applicator workers MAY spawn their own explorer subagents for targeted context gathering.
- Explorer output: structured summary (file inventory, key patterns, dependency maps, API surfaces). Max 200 lines.

### Reviewer subagents

Each reviewer subagent owns exactly ONE domain (or one dynamically-discovered domain).
They produce Proof Packets. They do NOT apply patches.
Get dispatch prompts via: `mpcr protocol dispatch --role <ROLE>
# Cybersecurity specialist roles: supply-chain-auditor, auth-access-prover, crypto-secrets-auditor,
#   injection-hunter, infra-runtime-auditor, data-privacy-guardian`

Additionally, two supplemental specialists run after domain reviewers:
- `complexity-analyst`: evaluates Big-O time/space complexity, data structure fitness, and algorithm choice across all changed code.
- `overengineering-guard`: applies smell tests for unnecessary abstraction introduced by this change.

After all Proof Packets are collected, one synthesis specialist runs:
- `ship-readiness-assessor`: synthesizes all Proof Packets into a SHIP / SHIP_WITH_FIXES / DO_NOT_SHIP verdict.

### Applicator subagents

Each applicator subagent owns a subset of findings.
They apply patches and record dispositions. They do NOT re-review.
Get dispatch prompts via: `mpcr protocol dispatch --role applicator-worker`

## Dynamic domain discovery

The 17 seed domains (11 general + 6 cybersecurity) are a starting point, NOT an exhaustive list.

WHEN the orchestrator inspects the diff summary, it SHALL:
1. Run `mpcr protocol domains` to load the 17 seed domains (11 general-purpose + 6 cybersecurity-focused).
2. Identify additional domains relevant to the specific codebase and change (e.g., i18n, accessibility, ML safety, platform-specific, database-specific, UX consistency, backwards compatibility, deployment safety, configuration management). Note: common cybersecurity concerns (supply chain, auth, crypto, injection, infra security, data privacy) are already covered by seed domains 12-17.
3. For each dynamically-discovered domain, define: name, "defend that..." statement, and 2-3 seed challenges.
4. Spawn one specialist reviewer per domain (seed + discovered). Each agent owns exactly one domain.

The orchestrator SHALL discover at least 2 additional domains beyond the 17 seeds for any non-trivial change.

## Reviewer workflow (orchestrator perspective)

1. Register: `mpcr reviewer register --target-ref <REF>`
2. Get orchestration guidance: `mpcr protocol orchestrator`
3. Spawn explorer subagents to pre-digest code context for each file cluster.
4. Run `mpcr protocol domains` and perform dynamic domain discovery.
5. Spawn children in mpcr: `mpcr reviewer spawn-children --parent-id <ID> --session-id <SID> --target-ref <REF> --count N`
6. For each domain (seed + discovered):
   a. Get the closest matching dispatch profile: `mpcr protocol dispatch --role <ROLE>`
   b. Customize the prompt with: assigned files, domain focus, explorer context summary, child mpcr IDs, and worker env contract (`MPCR_REVIEWER_ID`, `MPCR_SESSION_ID`, `MPCR_SESSION_DIR`).
   c. Launch as a parallel subagent.
7. Wait for all workers to return Proof Packets.
8. Run quality validation on each packet (see Quality Gate below).
9. Dispatch `complexity-analyst` and `overengineering-guard` as supplemental reviewers (they review the full changed file set).
10. After all Proof Packets arrive, dispatch `ship-readiness-assessor` with all collected packets.
11. Wait for ship-readiness verdict.
12. Re-dispatch workers whose packets fail validation (max 1 retry per worker).
13. Synthesize: merge findings, deduplicate, resolve severity conflicts (keep higher). Include the ship-readiness verdict as section 1 of the report.
14. Write report using `mpcr protocol report-template --scale <SCALE>`.
15. Finalize: `mpcr reviewer finalize --verdict <V> --report-file report.md`

### Quality gate

AFTER collecting all Proof Packets, you SHALL validate each against this rubric:

| Criterion | Pass | Fail |
|-----------|------|------|
| Domain Ledger present | Machine-parseable table with columns: Domain, Scope, Theorems, Disproofs, Findings, Defended | Missing or incomplete |
| Theorem specificity | Every theorem references a concrete `file:line` and a falsifiable invariant | Generic claims like "the code works" |
| Disproof effort | Every disproof describes a specific input, sequence, or scenario | "I tried and it works" or empty |
| Evidence grounding | Findings cite actual code locations that exist | No anchors or fabricated references |
| Severity evidence | BLOCKER/MAJOR findings include concrete trigger path + impact evidence | Severity asserted without concrete exploit/impact path |
| Proportionality | Depth proportional to assigned code complexity (≥ 2 theorems per 100 lines reviewed) | Single trivial theorem for large scope |
| Section completeness | Coverage, Findings (or explicit "none"), Defended Proofs, Residual Risk all present | Missing required sections |

WHEN a packet fails validation:
1. You SHALL note the specific failures.
2. You SHALL re-dispatch the worker with feedback on what was insufficient.
3. IF the retry also fails, you SHALL record the gap as Residual Risk in the final report.
4. You SHALL NOT fabricate findings to fill the gap.

## Applicator workflow (orchestrator perspective)

1. Ingest reports: `mpcr session reports closed --include-report-contents --include-leaf-children`
2. Build a finding inventory grouped by file cluster.
3. For each cluster, get dispatch prompt: `mpcr protocol dispatch --role applicator-worker`
4. Customize with: assigned findings, file list, verification criteria.
5. Launch applicator subagents in parallel (one per file cluster), subject to concurrency cap of 8.
6. Each worker runs the **evidence challenge protocol** before applying any fix (spawning explorer subagents to verify):
   - Spawn an explorer subagent to verify finding anchors actually exist and contain the claimed code.
   - Reproduce the reviewer's disproof scenario independently.
   - Check for hallucinated findings (references to nonexistent code/functions).
   - Validate severity is proportionate to actual exploitability.
   - DECLINE findings that fail evidence challenge, regardless of stated severity.
7. Workers that pass challenge: apply patches → run relevant tests → return results.
8. Synthesize worker results and record all dispositions via `mpcr applicator note`.
9. Set final status: `mpcr applicator set-status --initiator-status APPLIED`
10. Present summary to user (including count of declined-via-challenge findings).

## Full-cycle workflow

Full-cycle runs Reviewer → Applicator → Re-review with convergence control. You SHALL follow `mpcr protocol fullcycle` when available, or this section as fallback.

### Phase 1: Initial review
1. Run the complete Reviewer workflow (above). Produce merged report with ship-readiness verdict.
2. IF ship-readiness verdict is **SHIP** (zero BLOCKER/MAJOR) → STOP. Present report to user. Done.
3. OTHERWISE → proceed to Phase 2.

### Phase 2: Application
4. Run the Applicator workflow on findings from Phase 1.
5. Dispatch applicator-worker subagents for APPLIED findings (subject to concurrency cap of 8).
6. Each applicator-worker SHALL spawn explorer subagents for evidence challenge verification.
7. Collect Application Reports. Record all dispositions.

### Phase 3: Scoped re-review
8. Identify the delta: files modified by applicator-workers in Phase 2.
9. Run a NEW reviewer workflow targeting ONLY the delta files.
   - You SHALL use fresh subagents (not reuse Phase 1 workers).
   - You SHALL NOT re-examine code reviewed in Phase 1 that was not modified.
   - Spawn domain specialists relevant to the delta only (not all 17+).
   - The ship-readiness-assessor runs last, as in Phase 1.
10. Collect re-review report and ship-readiness verdict.

### Phase 4: Convergence
11. IF the re-review produces zero net-new BLOCKER or MAJOR → STOP. Present final report.
12. IF net-new issues exist AND this is cycle 1 → repeat Phases 2-3 on net-new findings only.
13. IF this is cycle 2 → HARD STOP. Remaining issues become Residual Risk. Present to user for decision.

### Full-cycle constraints
- Maximum 2 full cycles (review → apply → re-review). No infinite loops.
- Each cycle SHALL use fresh subagents to prevent convergent laziness.
- The orchestrator SHALL track cycle count and enforce the hard limit.
- At each stop point, present a cycle summary: Applied N, Declined N, Deferred N, Net-new N, Ship-readiness verdict.

## Autonomous operation

You SHALL resolve context WITHOUT asking the user:
- Target ref: infer from current branch. WHEN a git hosting CLI is available (e.g., `gh`, `glab`), you SHALL check for associated PRs/MRs.
- Acceptance criteria: derive from PR/MR description, commit messages, or diff content. Mark [Assumed] if inferred.
- PR/MR/issue context: check silently. IF found, use it. IF not, proceed with the diff.
- Parallelism: single-agent for ≤ 500 line diffs (still spawns 1 worker), multi-agent otherwise.

You SHALL only ask the user IF you are genuinely blocked (e.g., cannot determine what code to review).

## Getting started

`mpcr protocol` serves phase-appropriate guidance so you never need to hold the full protocol in context.
You SHALL run it at each phase transition.

### Quick reference

```
# Reviewer (register returns PARENT_ID8 and SESSION_ID8)
mpcr reviewer register --target-ref <REF>
mpcr protocol orchestrator
mpcr protocol domains
mpcr protocol dispatch --role <ROLE>
mpcr protocol dispatch --role complexity-analyst
mpcr protocol dispatch --role overengineering-guard
mpcr protocol dispatch --role ship-readiness-assessor
mpcr reviewer spawn-children --parent-id <PARENT_ID8> --session-id <SESSION_ID8> --target-ref <REF> --count N
mpcr reviewer update --reviewer-id <CHILD_ID8> --session-id <SESSION_ID8> --status IN_PROGRESS --phase <PHASE>
mpcr reviewer complete-child --reviewer-id <CHILD_ID8> --session-id <SESSION_ID8> --verdict ... --report-file ...
mpcr reviewer close-children --parent-id <PARENT_ID8> --session-id <SESSION_ID8>
mpcr reviewer finalize --reviewer-id <PARENT_ID8> --session-id <SESSION_ID8> --verdict <V> --report-file report.md

# Applicator
mpcr session reports closed --include-report-contents --include-leaf-children
mpcr protocol dispatch --role applicator-worker
mpcr applicator note --reviewer-id <ID8> --session-id <ID8> --note-type applied|declined|deferred|already_addressed --content "..."
mpcr applicator set-status --reviewer-id <ID8> --session-id <ID8> --initiator-status RECEIVED|REVIEWED|APPLYING|APPLIED

# Report templates
mpcr protocol report-template --scale compact|standard|full
```

## Reference documents (fallback)

IF `mpcr protocol` is unavailable, you SHALL read these files directly:
- Reviewer: `<skills-file-root>/references/reviewer-protocol.md`
- Applicator: `<skills-file-root>/references/applicator-protocol.md`
- Domains: `mpcr protocol domains` (or see the domains table in the reviewer protocol reference)
