# Logging specification

## Canonical data

`events.jsonl` is the only canonical persisted data store.

Each non-empty line is one JSON object representing one friction event.

`INDEX.md` is a derived summary view kept adjacent to `events.jsonl`. It is tool-managed and not part of the canonical data contract.

## Required narrative fields

Normal captures require substantive values for:

- `instruction_source`
- `instruction_text`
- `action_taken`
- `expected_outcome`
- `actual_outcome`
- `interpretation`

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
- optional anchors

## Identity fields

The event stream may record:

- `agent_name`
- `agent_kind`
- `role`

These fields are descriptive only. There is no parent-child orchestration graph and no session ID.
When provenance is not provided explicitly, it should remain unspecified rather than inferred.

## Anchors

Anchors are stored as an `anchors` array so code and non-code references can be represented uniformly.

Anchor members may include:

- `kind`
- `path`
- `line`
- `end_line`
- `symbol`
- `section`
- `url`
- `selector`
- `label`

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
