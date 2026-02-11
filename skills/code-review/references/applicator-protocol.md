# Applicator Protocol (Fallback Reference)

This document is a self-contained fallback for when `mpcr protocol` is unavailable.
IF `mpcr protocol` works, you SHALL use it instead — it serves phase-appropriate guidance just-in-time.

## Workflow overview

1. **Ingest** review reports and build a finding inventory.
2. **Disposition** each finding: apply, decline, defer, or mark already-addressed.
3. **Apply** accepted feedback, verifying each change.
4. **Finalize** dispositions and update mpcr status.

## Phase 1: Ingestion

1. You SHALL run `mpcr session reports closed --include-report-contents` to get finished reviews.
2. IF no session exists, you SHALL read report files provided by the user.
3. You SHALL build a finding inventory: list all findings by severity.
4. You SHALL note each reviewer's verdict and acceptance criteria.

`mpcr applicator set-status --initiator-status RECEIVED`

## Phase 2: Disposition

You SHALL decide a disposition for EVERY finding. You SHALL NOT skip any.

| Disposition | When | mpcr command |
|---|---|---|
| APPLIED | Will implement the fix | `mpcr applicator note --note-type applied --content "finding: <title>, action: <what>"` |
| DECLINED | Disagree with finding | `mpcr applicator note --note-type declined --content "finding: <title>, reason: <why>"` |
| DEFERRED | Valid but out of scope | `mpcr applicator note --note-type deferred --content "finding: <title>, tracking: <ref>"` |
| ALREADY_ADDRESSED | Already fixed elsewhere | `mpcr applicator note --note-type already_addressed --content "finding: <title>, ref: <where>"` |

Rules:
- BLOCKER findings SHALL be APPLIED unless you provide a compelling DECLINED reason.
- You SHALL record a disposition note for every finding.

`mpcr applicator set-status --initiator-status REVIEWED`

## Phase 3: Application

1. For each APPLIED finding, you SHALL make the code change.
2. You SHALL verify each change addresses the specific disproof scenario from the review.
3. WHEN tests exist, you SHALL run relevant tests after each change.

`mpcr applicator set-status --initiator-status APPLYING`

## Phase 4: Finalization

1. You SHALL verify all findings have dispositions.
2. You SHALL confirm all APPLIED changes are committed/staged.
3. WHEN a test suite is available, you SHALL run it.

`mpcr applicator set-status --initiator-status APPLIED`

You SHALL present the user a summary: Applied N, Declined N (reasons), Deferred N (tracking), Already addressed N.

## mpcr quick reference

```
mpcr session reports closed --include-report-contents [--json]
mpcr applicator set-status --initiator-status <STATUS> --reviewer-id <ID> --session-id <SID>
mpcr applicator note --note-type <TYPE> --content "..."
mpcr applicator wait [--target-ref <REF>]
```
