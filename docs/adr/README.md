# Architecture decision records

These records preserve why repository-wide instruction and evaluation choices were made, the evidence that supported them, and what would justify reopening them. They are not a second policy layer or a required template for skills and plugins. Current normative instructions remain in [`AGENTS.md`](../../AGENTS.md), target contracts, host schemas, and maker requirements.

An accepted ADR records the decision horizon at the time it was made. When evidence changes the direction, add or revise a superseding record rather than silently rewriting the historical reason. Not every implementation choice needs an ADR; use one only when the decision is consequential and reusable across targets.

| ADR | Decision |
| --- | --- |
| [0001](0001-outcome-driven-ai-instructions.md) | Bind AI instruction outcomes, not unneeded pathways |
| [0002](0002-semantic-policy-and-deterministic-mechanisms.md) | Keep semantic policy in instructions and deterministic responsibility in mechanisms |
| [0003](0003-behavioral-evidence-for-task-value.md) | Require comparative behavior for task-value claims |
| [0004](0004-blind-custody-and-prompt-purity.md) | Protect experiments through custody and task-pure prompts |
| [0005](0005-decision-specific-review-rubrics.md) | Give blind reviewers a shared, researched, decision-specific rubric |
| [0006](0006-progressive-disclosure-and-source-horizons.md) | Route context progressively and choose source horizons deliberately |
| [0007](0007-use-comparisons-to-correct-foundations.md) | Use comparative evidence to correct the earliest supported cause |
| [0008](0008-treat-reviewers-as-measurement-instruments.md) | Treat reviewer behavior as part of the measured system |
| [0009](0009-establish-consumer-semantics-before-contract-findings.md) | Establish adopted consumer meaning before contract findings |
| [0010](0010-bind-evaluation-claims-to-exposure.md) | Bind evaluation claims to actual exposure and named concealment |
| [0011](0011-preserve-the-deployed-input-stack.md) | Preserve the real deployed input stack in comparative trials |
| [0012](0012-preserve-matches-through-randomization.md) | Preserve condition-neutral match structure through blinding |
| [0013](0013-observe-claims-at-their-real-boundary.md) | Observe each claim at the layer where its property exists |
| [0014](0014-match-mechanism-assurance-to-the-named-hazard.md) | Match deterministic assurance to the failure the consumer actually needs |
| [0015](0015-replicate-the-source-of-variation.md) | Replicate the source of variation and give each review layer one evidence role |
| [0016](0016-treat-answer-keys-as-fallible-instruments.md) | Let pre-exposure evidence correct private answer keys and validations |
| [0017](0017-separate-option-evidence-artifact-review-and-decision-authority.md) | Separate evidence about options, artifact QA, and rightful decision authority |
| [0018](0018-compare-at-a-shared-consequence-boundary.md) | Compare alternatives only at a shared decision-relevant consequence boundary |
| [0019](0019-verify-evidence-at-the-delivery-boundary.md) | Verify evidence and references from the boundary the consumer receives |
| [0020](0020-do-not-let-a-defect-select-its-own-repair.md) | Keep repair choice and repair scope separate from defect discovery |
| [0021](0021-preserve-authority-across-runtime-identity.md) | Preserve authority when distinct logical roles resolve to the same runtime object |
| [0022](0022-ground-generated-benchmarks-in-outcome-evidence.md) | Do not prescribe benchmark seeds without demonstrated behavioral gain |
| [0023](0023-narrow-assurance-when-coverage-does-not-improve.md) | Narrow assurance claims when repeated interventions do not improve coverage |
| [0024](0024-compensate-observed-blind-spots-with-boundary-evidence.md) | Compensate a repeated model blind spot with observable boundary evidence |
| [0025](0025-centralize-comparative-method-declaratively.md) | Centralize comparative method in a declarative skill |
| [0026](0026-agentic-design-and-evaluation.md) | Share one foundation across prompt/context design, skill audits, and domain-general comparisons |
