# Reviewer workflow overview (UACRP)

Use this workflow when you are asked to **review a change** (diff/PR/patch). Your primary output is a UACRP report, not code changes.

## Mandatory ingestion (once per conversation)

Before reviewing any code, you SHALL read:

1) `<skills-file-root>/references/perform/uacrp.md` (UACRP baseline + report template)
2) `<skills-file-root>/references/perform/mpcr-workflow.md` (how to coordinate sessions/reports via `mpcr`)
3) `<skills-file-root>/references/multi-agent.md` (multi-agent orchestration; required IF subagents are available)
4) IF the user provides OR requests GitHub PR/issue context OR you need to request it to satisfy the Deterministic context check THEN you SHALL read `<skills-file-root>/references/gitops/github-context.md` (deterministic, low-bloat ingestion of authoritative intent/acceptance criteria)

### Chunking rule (explicit; do not skip)

- IF you need to ingest files in parts THEN you SHALL read them in **<= 500-line chunks**.
- IF you have already ingested these files earlier in this conversation THEN you SHALL NOT re-ingest them; proceed with the workflow.
- IF GitHub PR/issue context appears later in the conversation AND you have not yet ingested `<skills-file-root>/references/gitops/github-context.md` THEN you SHALL ingest it then (do not re-ingest it if already ingested).

## Deterministic context check (mandatory; low-bloat)

There SHALL exist an authoritative problem statement and acceptance criteria for the change.
IF the user has not provided it (via PR/issue or equivalent) THEN you SHALL ask whether there is an associated PR and/or issue and request a deterministic reference (URL, `PR <owner>/<repo>#<num>` / `Issue <owner>/<repo>#<num>`, or `PR <num>` / `Issue <num>` when operating in the current worktree repo).
IF no authoritative source exists (PR/issue or equivalent acceptance criteria) THEN you SHALL ask the user to provide explicit acceptance criteria in chat and WAIT before proceeding; if the user explicitly instructs you to proceed anyway, you SHALL record the missing context as Assumed/Unknown in Residual Risk.

## Concurrency default (mandatory when available)

IF subagents / parallel workers are available THEN multi-agent execution SHALL begin early.

After capturing the minimal deterministic coordination context (register via `mpcr` and establish the target ref / session context), you SHALL delegate in parallel rather than performing full sequential codebase ingestion yourself.
This is mandatory because it increases depth and throughput without sacrificing determinism (mpcr remains the state owner).

You SHALL ask the user how much parallelism they want (no fixed cap). If the user gives a concurrency budget, you SHALL respect it (use waves if needed); otherwise you SHALL continue delegating until the saturation stop condition defined in `<skills-file-root>/references/multi-agent.md` is met.

## Deliverables

- A UACRP report (Sections 0–11) with exactly one verdict: `APPROVE`, `REQUEST_CHANGES`, or `BLOCK`
- Findings anchored to specific code locations with evidence
- Report saved via `mpcr reviewer finalize` (or output to chat if `mpcr` is unavailable)
