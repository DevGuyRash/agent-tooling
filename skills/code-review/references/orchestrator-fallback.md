# Orchestrator Fallback

Use semantic routing first. Keep the orchestrator thin: instantiate the canonical reviewer roster every run, persist session state, and hand each worker only its dispatch prompt plus relevant policy packs. Use `mpcr session reports` for report retrieval and `mpcr session artifacts` for flat artifact inventory.

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