# Applicator workflow overview (apply review feedback)

Use this workflow when you are asked to **apply findings from completed review reports**. Your primary output is dispositions (applied/declined/deferred/etc) plus the corresponding code changes.

## Mandatory ingestion (once per conversation)

Before applying any code changes, you SHALL read:

1) `<skills-file-root>/references/apply/code-review-application-protocol.md` (application protocol + disposition rules)
2) `<skills-file-root>/references/apply/mpcr-workflow.md` (how to gather reports and record status/notes via `mpcr`)
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

Specifically, after capturing the minimal deterministic coordination context (`session_dir` + the set of completed reports to process), you SHALL delegate in parallel rather than performing full sequential ingestion yourself.
This is mandatory because it increases depth and throughput without sacrificing determinism (mpcr remains the state owner).

You SHALL ask the user how much parallelism they want (no fixed cap). If the user gives a concurrency budget, you SHALL respect it (use waves if needed); otherwise you SHALL continue delegating until additional independent analysis stops producing new failure modes / evidence / mitigations (saturation stop condition).

### Default delegation plan (recommended; low-bloat)

IF the user has not specified a decomposition THEN you SHOULD start with subagents partitioned by report entry and/or finding clusters:

1) **Report Extractor:** parse report(s) into a normalized finding list (severity/title/anchor/claim).  
2) **Anchor Verifier:** validate each finding against current code at the cited anchors.  
3) **Patch Designer:** draft patch sketches + verification steps for “applied” recommendations.

Each subagent SHALL read `<skills-file-root>/references/apply/subagent-contract.md` and return exactly one Disposition Packet.

## Await review completion (mandatory)

IF the review is still in progress for the target entries you intend to apply THEN you SHALL wait for completion before applying changes.
Use `mpcr applicator wait` (it uses an exponential backoff poll loop) and proceed only when the relevant reviewer statuses are terminal.

## Deliverables

- A disposition (applied/declined/deferred/etc) for every finding, recorded via `mpcr applicator note`
- Code changes for findings you apply
- Updated `initiator_status` reflecting your progress
