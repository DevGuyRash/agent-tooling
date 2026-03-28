# Logging specification

## Canonical data

`events.jsonl` is the only canonical persisted data store.

Each non-empty line is one JSON object representing one friction event.

`INDEX.md` is a derived summary view kept adjacent to `events.jsonl`. It is tool-managed and not part of the canonical data contract.

## Required narrative fields

Normal captures require substantive values for:

- `instruction_text`
- `action_taken`
- `expected_outcome`
- `actual_outcome`
- `interpretation`

The `sources` array is required when the friction can be localized to a specific file, document, or URL.

`title` may be omitted. The tool derives it from `actual_outcome` when needed.

Blank or whitespace-only narrative values are invalid.

## Core event fields

The canonical event record includes:

- schema and taxonomy versions
- event id
- incident id
- fingerprint
- recorded timestamp
- canonical events file path
- repo root when available
- agent identity fields
- narrative fields
- derived category fields
- redaction metadata
- optional sources

Optional fields are omitted from the stored record when empty, zero, or false (sparse output).

Numeric scales used in the schema:

- **confidence** (1–5): 1 = wild guess, 2 = low confidence, 3 = moderate, 4 = high, 5 = near certain
- **guidance_quality** (0–4): 0 = N/A, 1 = misleading, 2 = ambiguous, 3 = partial, 4 = clear

## Identity fields

The event stream may record:

- `agent_name`
- `agent_kind`
- `role`

These fields are descriptive only. There is no parent-child orchestration graph and no session ID.
When provenance is not provided explicitly, it should remain unspecified rather than inferred.

## Sources

Sources are stored as a `sources` array so code and non-code references can be represented uniformly.

Source members may include:

- `type`
- `ref`
- `line`
- `end_line`
- `symbol`
- `excerpt`
- `selector`
- `label`

## Removed fields (v3)

The following fields were present in v2 and are no longer part of the schema:

- `title_line`
- `quick_capture`
- `force_capture`
- `redaction_applied`
- `privacy_tier`
- `incident_status`
- `evidence_type`
- `instruction_source` (replaced by the `sources` array)

## Sanitization

Write-time sanitization is always applied before event text is persisted.

Current redaction covers common bearer tokens, GitHub tokens, API tokens, AWS access keys, Slack tokens, and generic password/token/secret/api-key assignments.

The stored event stream contains sanitized text, not raw secret material.

## JSON input

`--from-json` accepts one JSON object.

On syntax failure, the tool returns:

- concise parser diagnostics
- line/column details when the active runtime exposes them
- a short local snippet or hint when detectable

On schema/content failure, the tool returns concise field-level diagnostics.

Raw parser stack traces are suppressed.

## Index behavior

`INDEX.md` is created and refreshed automatically by the tool after append operations.

Agents do not explicitly create, request, or rebuild `INDEX.md` in the normal workflow.
