# Applicator Protocol (Fallback Reference)

This document is a self-contained fallback for when `mpcr protocol` is unavailable.
IF `mpcr protocol` works, you SHALL use it instead — it serves phase-appropriate guidance just-in-time.

## Workflow overview

1. **Ingest** review reports and build a finding inventory.
2. **Disposition** each finding: apply, decline, defer, or mark already-addressed.
3. **Apply** accepted feedback via parallel applicator subagents.
4. **Finalize** dispositions and update mpcr status.

## Phase 1: Ingestion

1. You SHALL run `mpcr session reports closed --include-report-contents --include-leaf-children` to get finished reviews.
2. IF no session exists, you SHALL read report files provided by the user.
3. You SHALL build a finding inventory listing all findings by severity.
4. You SHALL note each reviewer's verdict and acceptance criteria.
5. You SHALL group findings by file cluster for parallel dispatch.

`mpcr applicator set-status --initiator-status RECEIVED`

## Phase 2: Disposition

You SHALL decide a disposition for EVERY finding. You SHALL NOT skip any.

### Evidence challenge protocol

BEFORE accepting any finding, you SHALL independently verify its legitimacy:

1. **Anchor verification**: Confirm the finding's `file:line` exists and contains the claimed code. IF wrong or fabricated → DECLINE.
2. **Disproof reproduction**: Reproduce the reviewer's disproof scenario yourself. Trace the code path. IF the scenario is impossible (input validated upstream, type system prevents it, path unreachable) → DECLINE.
3. **Severity validation**: Assess whether severity is proportionate. BLOCKER must be exploitable in production; MAJOR must have a realistic trigger path.
4. **Hallucination detection**: Watch for findings referencing nonexistent functions/variables, misunderstanding language semantics, claiming missing validation when it exists upstream, or generic copy-paste findings. IF detected → DECLINE.
5. **Redundancy check**: IF two findings describe the same issue at the same location → keep higher-severity one, DECLINE the duplicate.

### Dispositions

| Disposition | When | mpcr command |
|---|---|---|
| APPLIED | Finding passed evidence challenge; will implement | `mpcr applicator note --note-type applied --content "finding: <title>, verified: <how>, action: <what>"` |
| DECLINED | Finding failed evidence challenge | `mpcr applicator note --note-type declined --content "finding: <title>, challenge: <which check failed>, reason: <evidence>"` |
| DEFERRED | Verified but out of scope | `mpcr applicator note --note-type deferred --content "finding: <title>, tracking: <ref>"` |
| ALREADY_ADDRESSED | Already fixed elsewhere | `mpcr applicator note --note-type already_addressed --content "finding: <title>, ref: <where>"` |

Rules:
- BLOCKER findings SHALL be APPLIED only AFTER passing evidence challenge.
- You SHALL NOT blindly apply findings — every APPLIED disposition requires a "verified" note.
- You SHALL DECLINE findings that fail evidence challenge, regardless of stated severity.
- You SHALL record a disposition note for every finding.

`mpcr applicator set-status --initiator-status REVIEWED`

## Phase 3: Application

### Orchestrator mode (you are coordinating)
1. Group APPLIED findings by file cluster.
2. For each cluster, get dispatch prompt: `mpcr protocol dispatch --role applicator-worker`
3. Customize with: assigned findings (full detail including disproof scenarios), file list.
4. Launch applicator-worker subagents in parallel.
5. Collect Application Reports from each worker.
6. Optionally launch applicator-verifier subagents to spot-check fixes.

### Worker mode (you are a subagent)
1. For each assigned finding, FIRST verify the disproof scenario is reproducible against the current code.
2. IF the finding fails verification (anchor wrong, scenario not reproducible, code already handles it), report back DECLINED with specific evidence.
3. For verified findings, make the code change.
4. Verify each change addresses the specific disproof scenario.
5. WHEN tests exist, run relevant tests after each change.
6. Return your Application Report.

`mpcr applicator set-status --initiator-status APPLYING`

## Phase 4: Finalization

1. You SHALL verify all findings have dispositions.
2. You SHALL confirm all APPLIED changes are committed/staged.
3. WHEN a test suite is available, you SHALL run it.

`mpcr applicator set-status --initiator-status APPLIED`

You SHALL present the user a summary: Applied N, Declined N (reasons), Deferred N (tracking), Already addressed N.

### Full-cycle convergence

IF this application is part of a full-cycle:
1. After finalization, the orchestrator runs a scoped re-review targeting ONLY modified files.
2. Convergence: zero net-new BLOCKER/MAJOR → stop.
3. Otherwise: one more cycle (max 2 total).
4. After cycle 2: remaining issues → Residual Risk → user decides.
5. Each cycle uses fresh subagents.

## mpcr quick reference

```
mpcr session reports closed --include-report-contents --include-leaf-children [--json]
mpcr applicator set-status --initiator-status <STATUS> --reviewer-id <ID> --session-id <SID>
mpcr applicator note --note-type <TYPE> --content "..."
mpcr applicator wait [--target-ref <REF>]
mpcr protocol dispatch --role applicator-worker
mpcr protocol dispatch --role applicator-verifier
```
