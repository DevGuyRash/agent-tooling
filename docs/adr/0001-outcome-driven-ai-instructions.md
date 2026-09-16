# ADR 0001: Adopt one governing contract for instruction authoring

- Status: Accepted
- Recorded: 2026-08-15
- Scope: AI instruction authoring across the repository

## Context

Reusable instructions can standardize either the outcome and authority needed for a task or the author's preferred reasoning and presentation. Repeating a fixed method across packages can make compliance visible while displacing the work the user actually requested.

## Decision

Adopt outcome-oriented instruction authoring through the governing contract referenced by [AGENTS.md](../../AGENTS.md). Instructions establish the assignment, relevant reality, authority, consequential constraints, and usable completion. Reasoning and implementation choices remain with the executor unless an actual interface, hazard, or justified task requirement makes a method necessary.

Keep the governing contract in one maintained source. Package instructions apply it within its authoring scope rather than reproduce it as mandatory headings or a workflow.

## Rationale and consequences

This preserves expert judgment while making real obligations explicit. Exact sequences and output structures remain appropriate where a consumer or operational boundary needs them. A report matching a preferred shape is insufficient evidence that the intended task was completed.

Repository adoption governs authoring here; an external audit target is assessed against the requirements it actually adopts. Current source ownership and editing restrictions remain in AGENTS.md.
