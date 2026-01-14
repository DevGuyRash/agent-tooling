# Reviewer workflow overview (UACRP)

Use this workflow when you are asked to **review a change** (diff/PR/patch). Your primary output is a UACRP report, not code changes.

## Mandatory ingestion (once per conversation)

Before reviewing any code, you SHALL read:

1) `<skills-file-root>/references/perform/uacrp.md` (UACRP baseline + report template)
2) `<skills-file-root>/references/perform/mpcr-workflow.md` (how to coordinate sessions/reports via `mpcr`)

### Chunking rule (explicit; do not skip)

- IF you need to ingest files in parts THEN you SHALL read them in **<= 500-line chunks**.
- IF you have already ingested these files earlier in this conversation THEN you SHALL NOT re-ingest them; proceed with the workflow.

## Deliverables

- A UACRP report (Sections 0–11) with exactly one verdict: `APPROVE`, `REQUEST_CHANGES`, or `BLOCK`
- Findings anchored to specific code locations with evidence
- Report saved via `mpcr reviewer finalize` (or output to chat if `mpcr` is unavailable)
