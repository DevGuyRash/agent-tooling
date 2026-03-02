# Applicator Fallback

Primary source: `mpcr protocol applicator --phase <PHASE>`.

If the CLI is unavailable, use the sections below. They mirror the applicator protocol phases.

## Ingestion (`INGESTION`)

You SHALL locate and read review reports:

1. You SHALL run `mpcr session reports closed --session-dir <DIR> --include-report-contents --include-leaf-children` to get finished reviews.
2. IF no session exists, you SHALL look for review report files provided by the user.
3. You SHALL read each report and build a finding inventory listing all findings by severity.
4. You SHALL note each reviewer's verdict and acceptance criteria.
5. You SHALL group findings by file cluster for parallel dispatch.
6. You SHALL dispatch `scope-mapper-applicator` and ingest its Scope Map packet before Disposition.

You SHALL run: `mpcr applicator set-status --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --initiator-status RECEIVED`

## Disposition (`DISPOSITION`)

You SHALL decide a disposition for EVERY finding. You SHALL NOT skip any.

### Evidence challenge protocol

BEFORE accepting any finding at face value, you SHALL independently verify its legitimacy:

1. **Anchor verification**: You SHALL spawn an explorer subagent to confirm the finding's anchor (`file:line`) exists and contains the code the reviewer claims.
   IF the anchor is wrong, fabricated, or points to unrelated code → DECLINE with reason "invalid anchor".

2. **Disproof reproduction**: You SHALL attempt to reproduce the reviewer's disproof scenario yourself.
   - Trace the code path the reviewer claims is vulnerable.
   - Construct the specific input/sequence the reviewer describes.
   - IF the scenario is impossible (e.g., input is validated upstream, type system prevents it, the code path is unreachable) → DECLINE with reason "disproof not reproducible: <explanation>".

3. **Severity validation**: You SHALL assess whether the severity is proportionate.
   - BLOCKER: must be exploitable/triggerable in production with concrete impact.
   - MAJOR: must have a realistic (not just theoretical) trigger path.
   - IF a BLOCKER finding's scenario requires preconditions that are already mitigated → downgrade or DECLINE.

4. **Hallucination detection**: You SHALL watch for these reviewer anti-patterns:
   - Findings referencing functions, variables, or code patterns that do not exist in the codebase.
   - Disproof scenarios that misunderstand the language semantics or framework behavior.
   - Claims about missing validation when validation exists in a caller/middleware/framework layer.
   - Copy-paste findings that are generic and not specific to the actual code.
   IF detected → DECLINE with reason "hallucinated finding: <specific evidence>".

5. **Redundancy check**: IF two findings from different reviewers describe the same underlying issue at the same location → keep the higher-severity one, DECLINE the duplicate with reason "duplicate of <other finding title>".

### Dispositions

- APPLIED: you verified the finding is legitimate and will implement the fix. Record via:
  `mpcr applicator note --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --note-type applied --content "finding: <title>, verified: <how you confirmed>, action: <what you will do>"`
- DECLINED: the finding failed evidence challenge. Record reasoning via:
  `mpcr applicator note --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --note-type declined --content "finding: <title>, challenge: <which check failed>, reason: <specific evidence>"`
- DEFERRED: verified but out of scope for this change. Record via:
  `mpcr applicator note --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --note-type deferred --content "finding: <title>, tracking: <issue/ticket>"`
- ALREADY_ADDRESSED: already fixed or handled elsewhere. Record via:
  `mpcr applicator note --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --note-type already_addressed --content "finding: <title>, ref: <where>"`

### Disposition rules

- BLOCKER findings SHALL be APPLIED only AFTER passing evidence challenge steps 1-3.
- You SHALL NOT blindly apply findings — every APPLIED disposition requires a "verified" note.
- You SHALL DECLINE findings that fail evidence challenge, regardless of stated severity.
- WHEN declining a BLOCKER, your challenge evidence SHALL be specific and traceable (cite file:line).
- You SHALL record a disposition note via `mpcr applicator note` for every finding.

You SHALL run: `mpcr applicator set-status --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --initiator-status REVIEWED`

## Application (`APPLICATION`)

You SHALL apply accepted feedback using parallel applicator subagents:

## Orchestrator mode (you are coordinating)
1. Group APPLIED findings by file cluster.
2. For each cluster, get dispatch prompt: `mpcr protocol dispatch --role applicator-worker`
3. Customize with: assigned findings (full detail including disproof scenarios), file list, acceptance criteria.
4. Launch applicator-worker subagents in parallel (subject to concurrency cap of 8).
5. Each worker SHALL spawn explorer subagents for context gathering rather than reading unassigned files directly.
6. Each worker applies fixes and returns an Application Report.
7. Collect results. Verify all APPLIED findings were addressed.
8. WHEN APPLIED findings span at least 2 file clusters, launch an applicator-verifier subagent to spot-check fixes against original disproofs.

## Worker mode (you are a subagent applying fixes)
IF MPCR_APPLICATOR_ROLE is set, you are a worker:
1. For each assigned finding, FIRST spawn an explorer subagent to verify the disproof scenario is reproducible against the current code.
2. IF the finding fails verification (anchor wrong, scenario not reproducible, code already handles it), report back DECLINED with specific evidence rather than applying a spurious fix.
3. For verified findings, make the code change.
4. Verify each change addresses the specific scenario from the disproof.
5. WHEN tests exist, run relevant tests after each change.
6. IF a change introduces new issues, note them but do NOT cascade-fix.
7. Return your Application Report.

You SHALL run: `mpcr applicator set-status --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --initiator-status APPLYING`

## Finalization (`FINALIZATION`)

You SHALL record final state:

1. You SHALL verify all findings have dispositions.
2. You SHALL confirm all APPLIED changes are committed or staged.
3. WHEN a test suite is available, you SHALL run it.

You SHALL run: `mpcr applicator set-status --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --initiator-status APPLIED`

You SHALL present the user a summary:
- Applied: N findings
- Declined: N findings (with reasons)
- Deferred: N findings (with tracking refs)
- Already addressed: N findings

IF this application is part of a full-cycle (review → apply → re-review):
1. After finalization, the orchestrator SHALL run a scoped re-review targeting ONLY files modified during application.
2. The re-review SHALL NOT re-examine previously reviewed code that was not modified.
3. The re-review SHALL use fresh subagents (not reuse previous cycle workers).
4. The re-review SHALL include the `staleness-auditor` domain reviewer alongside other relevant domains.
5. Convergence: IF re-review produces zero net-new actionable findings (BLOCKER/MAJOR, plus staleness mismatches that affect shipped behavior or operator guidance) → stop.
6. IF net-new actionable findings exist, recurse another cycle on net-new findings only.
7. Continue recursion until a fixed point is reached (no net-new actionable findings).

## Artifact cleanup
AFTER finalization completes:
- You SHALL delete `.local/tmp/` if it exists:
  - POSIX: `rm -rf .local/tmp/`
  - PowerShell: `Remove-Item -Force -Recurse .local/tmp/ -ErrorAction SilentlyContinue`
- You SHALL NOT leave dispatch prompts, report templates, packet files, or any other scratch artifacts in the worktree.
