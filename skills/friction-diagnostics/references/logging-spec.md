# Logging specification

## Canonical data

`events.jsonl` is the only canonical persisted data store.

Each non-empty line is one JSON object representing one friction event.

`INDEX.md` is a derived summary view kept adjacent to `events.jsonl`. It is tool-managed and not part of the canonical data contract.

## Required narrative fields

Normal captures require substantive values for:

- `expected_outcome`
- `actual_outcome`
- `reading`

`hindsight` is recommended but optional.

The `sources` array is required. Each entry must have `type` and `ref`.

`title` may be omitted. The tool derives it from `actual_outcome` when needed.

Blank or whitespace-only narrative values are invalid.

## Core event fields

The canonical field definitions, types, constraints, and enums live in `friction-event-schema.json` (the single source of truth). All scripts derive field lists and enums from that file at runtime.

## Classification

- **`impact`** (required): `blocked`, `degraded`, `noisy`, or `continued`
- **`tags`** (optional): specific classification labels, normalized to lowercase
- **`aliases`** (optional): broader groupings, normalized to lowercase

There is no auto-categorizer. Classification is agent-provided.

## Sources

Sources are stored as a `sources` array. Valid source types are defined in `friction-event-schema.json`.

| Field | Description |
|---|---|
| `type` | `file`, `url`, `conversation`, `audio`, `visual`, `documentation`, `other` |
| `ref` | File path, URL, or description |
| `line`, `end_line` | Line range (for files) |
| `excerpt` | Verbatim quote from the source |

## Sanitization

Write-time sanitization is always applied before event text is persisted.

Current redaction covers common bearer tokens, GitHub tokens, API tokens, AWS access keys, Slack tokens, and generic password/token/secret/api-key assignments.

The stored event stream contains sanitized text, not raw secret material.

## JSON input

`--from-json` accepts one JSON object.

On syntax failure, the tool returns concise parser diagnostics with line/column details. On schema/content failure, concise field-level diagnostics. Raw parser stack traces are suppressed.

## Tags and aliases

Tags and aliases may be provided at filing time via `--tags` and `--aliases` (comma-separated). Both are normalized to lowercase on write.

Post-hoc additions are available via `--add-tags` and `--add-aliases`:

```sh
sh scripts/report-friction.sh --add-tags evt-NNNN "tag1,tag2"
sh scripts/report-friction.sh --add-aliases evt-NNNN "alias1,alias2"
```

Both commands rewrite the canonical file under the report lock and atomically swap in the updated JSONL. No other event fields are modified.

## Index behavior

`INDEX.md` is created and refreshed automatically by the tool after append operations.

Agents do not explicitly create, request, or rebuild `INDEX.md` in the normal workflow.
