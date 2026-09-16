# ADR 0022: Do not prescribe benchmark seeds without behavioral gain

- Status: Superseded by [ADR 0025](0025-centralize-comparative-method-declaratively.md)
- Date: 2026-08-17

## Decision

Do not add benchmark-seed instructions merely because a respected external system uses them. Retain the existing decision- and population-grounded task-generation contract unless a prospective intervention materially improves held-out benchmark quality. External guidance may reopen a test; it does not earn permanent context by being plausible or authoritative for a different product.

## Why

An external task-generation method surfaced plausible principles such as grounding cases in real instances, accepted outcomes, observed mistakes, and clean controls while preserving realistic structure where synthetic stand-ins are necessary. Its fixed documents, intake sequence, grader constraints, and handoff form nevertheless served a product-specific interface rather than this domain-free comparison system. Source lineage remains development provenance rather than runtime architecture.

A fresh matched trial compared the existing Split Testing instruction with a candidate that added those portable-looking principles. Both produced substantial maintenance-triage evidence from the same historical record. The blind reviewer preferred the existing instruction: the candidate chose a less literal output interface and allowed the history's subtle imminent-failure pattern to survive its hard safety gate, while the existing version made every unsafe shutdown delay disqualifying. A condition-blind fact-check narrowed the interface criticism and corrected the raw case-count interpretation, but confirmed the consequential gate difference. The added wording therefore did not earn its context cost. One pair does not establish that the principle is harmful in general; it does establish that this intervention lacks the improvement evidence required for adoption.

## Consequences

ADR 0025 replaces this benchmark-centered frame with decision-grounded comparative evidence. Authors retain freedom to use real outcomes, clean controls, synthetic cases, or other evidence when the live decision warrants them; none becomes a runtime archetype or required seed.

Reopen this decision when a different, prospectively frozen wording or mechanism improves benchmark quality on more than one dissimilar held-out task without weakening interface fidelity, hazard coverage, discrimination, or context discipline.
