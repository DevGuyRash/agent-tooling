# ADR 0002: Separate semantic policy from deterministic mechanisms

- Status: Accepted
- Recorded: 2026-08-15
- Scope: Instruction and executable responsibilities across the repository

## Context

Agent tooling combines instructions with programs that inspect, transform, package, or preserve artifacts. Assigning the same responsibility to both can duplicate policy or make a mechanical check appear to establish semantic quality.

## Decision

Instructions and the responsible executor own interpretation, sufficiency, quality judgment, and application of task authority. Executable mechanisms own mechanically decidable operations and interfaces, including parsing, containment, integrity checks, serialization, packaging, and deterministic state transitions.

A mechanism may enforce an adopted literal contract. Its successful exit establishes that contract's declared result; semantic judgments remain with the responsible decision maker.

## Rationale and consequences

Keyword counts, headings, and file inventories cannot establish whether an instruction serves its task. Conversely, repeatable byte handling, locking, and path containment benefit from executable enforcement rather than repeated model reconstruction.

Programs expose observations and failures through explicit interfaces. Their consumers interpret those observations against the task. Verification covers the mechanism and, when consequential, the behavior of the composed system. A semantic responsibility can move into code when an adopted interface makes it mechanically decidable.
