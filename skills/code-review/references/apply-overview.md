# Applicator workflow overview (apply review feedback)

Use this workflow when you are asked to **apply findings from completed review reports**. Your primary output is dispositions (applied/declined/deferred/etc) plus the corresponding code changes.

## Mandatory ingestion (once per conversation)

Before applying any code changes, you SHALL read:

1) `<skills-file-root>/references/apply/code-review-application-protocol.md` (application protocol + disposition rules)
2) `<skills-file-root>/references/apply/mpcr-workflow.md` (how to gather reports and record status/notes via `mpcr`)

### Chunking rule (explicit; do not skip)

- IF you need to ingest files in parts THEN you SHALL read them in **<= 500-line chunks**.
- IF you have already ingested these files earlier in this conversation THEN you SHALL NOT re-ingest them; proceed with the workflow.

## Deliverables

- A disposition (applied/declined/deferred/etc) for every finding, recorded via `mpcr applicator note`
- Code changes for findings you apply
- Updated `initiator_status` reflecting your progress
