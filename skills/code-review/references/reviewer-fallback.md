# Reviewer Fallback

# reviewer
version: 2026.03.08
Produce canonical review artifacts from semantic routing and concern-specific worker execution.

## Must
- route by semantic surfaces
- emit machine artifacts first
- render markdown only from artifacts

## Must Not
- treat prose as canonical
- route primarily by churn
- store full artifacts in _session.toml

## Inputs
- target_ref
- surface_map
- route_decision
- selected policy refs

## Outputs
- child_findings
- parent_review

## Checks
- load mode checklist after routing
- validate artifacts at hard and soft layers
- preserve evidence-backed findings only

## Stop When
- parent_review finalized
- hard validation fails
- session is legacy v1

## Escalate When
- malformed output
- security risk exceeds baseline route
- route revision raises rigor

## Anti Patterns
- domain sprawl without surface evidence
- manual markdown synthesis before machine artifact exists

## Examples
- Low-risk docs-only update -> direct + lite + review-composite.
- Auth boundary change -> delegated + forensic + exploit + contract + release-risk coverage.

## Schema
- mode
- execution_architecture
- rigor_level
- worker_plan
- selected_modules
- loaded_policy_refs

Route first, then use `mpcr protocol dispatch --role <role>` for the current worker instead of loading the whole skill body again. The reviewer roster is language-detector, zero or more language-research workers, one domain-reviewer per canonical module, and final-synthesis.

Canonical artifact examples for manual reviewer flows live at `<skills-file-root>/references/reviewer-artifact-examples.md` with machine-valid TOML under `<skills-file-root>/references/examples/`.

# language-detector
version: 2026.03.08
Identify the active implementation languages early so research workers can fetch targeted primary-source guidance once.

## Must
- derive languages from changed files and relevant interfaces
- normalize languages to stable slugs
- avoid speculative language guesses when evidence is absent

## Must Not
- emit product findings in place of language classification
- trigger duplicate language research for the same language without new evidence

## Checks
- every detected language has a concrete file or interface signal
- unknown files do not block known-language handoff

## Stop When
- the language roster is stable enough for research fan-out

## Escalate When
- the change cannot be safely reviewed without resolving an unknown generated or embedded language

# language-research
version: 2026.03.08
Fetch current primary-source docs, standards, and idioms for one language so downstream reviewers stop re-browsing the same material.

## Must
- use primary sources first
- capture the sources and key idioms in the authored report
- limit research to guidance relevant to the changed language and routed domains

## Must Not
- restate generic review doctrine instead of language-specific guidance
- repeat research already cached for the same language without a new need

## Checks
- sources are current and language-native
- guidance maps back to routed review concerns

## Stop When
- downstream workers have enough language-specific guidance to proceed without re-browsing

## Escalate When
- no trustworthy primary source can be established for a critical language feature

# domain-reviewer
version: 2026.03.08
Own one review domain, produce a full authored report, and persist machine findings without duplicating sibling scope.

## Must
- own exactly the assigned module or delegated sub-scope
- write a full report.md even for no-findings or low-signal outcomes
- challenge findings for anchor quality, realism, duplication, and actionability before escalating them

## Must Not
- re-run language research already provided by upstream workers
- re-open already-addressed or low-signal claims
- delegate the same investigation slice twice

## Checks
- claimed_scope and delegated_scope stay disjoint
- defended non-findings are documented
- residual risks explain why work stops or escalates

## Stop When
- the assigned module has a complete report and finalized child_findings
- the assigned scope is out-of-scope or low-signal and that result is documented

## Escalate When
- new evidence implies a different routed domain must be delegated
- a major or blocker finding survives challenge

# final-synthesizer
version: 2026.03.08
Concatenate descendant reports, preserve recursive counts, and surface only challenged high-signal findings in the parent synthesis.

## Must
- walk descendant reports in stable order
- preserve recursive counts from machine artifacts
- filter out low-signal, duplicate, non-actionable, and already-addressed claims

## Must Not
- invent new evidence
- duplicate leaf findings as fresh discoveries
- reopen loops for weak or already-resolved items

## Checks
- final counts match descendant artifacts
- concatenation order is stable
- push-or-stop recommendation is evidence-backed

## Stop When
- the final synthesis and recursive counts are internally consistent

## Escalate When
- a surviving blocker or major finding requires reopen

# core-correctness
version: 2026.03.08
Baseline correctness module that always loads for review routing.

## Must
- challenge core behavior invariants
- cover changed control flow

## Must Not
- skip changed behavior because another module exists

## Checks
- core invariants are covered

## Stop When
- baseline correctness is covered

## Escalate When
- counterexample breaks correctness

# docs-staleness
version: 2026.03.08
Behavior-facing documentation and example congruence module.

## Must
- compare docs/examples/comments to actual behavior

## Must Not
- treat style edits as behavior-facing drift

## Checks
- reopen eligibility is explicit

## Stop When
- staleness status is clear

## Escalate When
- behavior-facing staleness remains

# ship-readiness
version: 2026.03.08
Ship-readiness synthesis module that always loads.

## Must
- summarize release posture
- count required-now and follow-up items correctly

## Must Not
- invent blockers without underlying evidence

## Checks
- counts match the artifact body
- blocking items are traceable to evidence

## Stop When
- ship readiness is finalized

## Escalate When
- blocking items remain