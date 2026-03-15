# Reviewer Fallback

## reviewer
version: 2026.03.08
Produce canonical review artifacts from semantic routing and concern-specific worker execution.

### Must
- route by semantic surfaces
- emit machine artifacts first
- register one root reviewer ledger and then spawn every required routed worker before synthesis
- keep first-hand exploration in routed workers rather than the orchestrator
- challenge each surviving reviewer claim end-to-end before escalation: prove the introducing condition and the downstream effect or closure path
- render markdown only from artifacts

### Must Not
- treat prose as canonical
- route primarily by churn
- store full artifacts in _session.toml

### Inputs
- target_ref
- surface_map
- route_decision
- selected policy refs

### Outputs
- child_findings
- parent_review

### Checks
- load mode checklist after routing
- reuse the persisted canonical session_dir and same target_ref string when resuming
- validate artifacts at hard and soft layers
- preserve evidence-backed findings only
- surviving findings keep repo anchors and cited supporting sources
- surviving findings still prove both the introducing condition and the downstream effect or closure path before escalation

### Stop When
- every required worker is finalized or categorically closed and parent_review is finalized
- hard validation fails
- session is legacy v1

### Escalate When
- malformed output
- security risk exceeds baseline route
- route revision raises rigor

### Anti Patterns
- domain sprawl without surface evidence
- manual markdown synthesis before machine artifact exists

### Examples
- Low-risk docs-only update -> direct architecture + lite rigor + the full reviewer roster.
- Auth boundary change -> delegated + forensic + exploit-tracer + contract-comparer + release-risk-assessor coverage.

### Schema
- mode
- execution_architecture
- rigor_level
- worker_plan
- selected_modules
- loaded_policy_refs

Route first. Treat `target-ref` as an opaque session key: branch name, commit SHA, or literal `HEAD` all work as long as every later command reuses the exact same string. For a fresh isolated session, prefer an unused canonical date leaf via `--repo-root <path> --date <yyyy-mm-dd>`; one canonical date leaf holds one session, so pick another date or clean up the stale leaf if that path already belongs to a different `target-ref`. For an existing session, reuse the exact persisted `session_dir` and the same `target-ref` string instead of inventing a new path. Register one root reviewer ledger as the orchestration anchor with `mpcr reviewer register --target-ref <same-exact-ref> --session-dir <persisted.session_dir>`, prefer `mpcr reviewer spawn-routed --parent-id <root-reviewer-id> --session-dir <persisted.session_dir>` to materialize every missing routed worker from `route_decision.worker_plan`, and fall back to `mpcr reviewer spawn-children` only for targeted manual replay. Use the current worker's `reviewer_id` for session-bound prompts, not the root anchor. The reviewer roster is language-detector, zero or more language-research workers, one domain-reviewer per canonical module, and the `final-synthesis` dispatch role (`final-synthesizer` worker policy). Use `mpcr session cleanup --session-dir <path>` to discard a stale canonical session leaf before reruns.

Manual reviewer artifact examples are indexed in SKILL.md, and machine-valid TOML scaffolds live under `<skills-file-root>/references/examples/`.

## language-detector
version: 2026.03.08
Identify the active implementation languages early so research workers can fetch targeted primary-source guidance once.

### Must
- derive languages from changed files and relevant interfaces
- normalize languages to stable slugs
- flag when public-interface or PR context implies downstream docs or API research
- avoid speculative language guesses when evidence is absent

### Must Not
- emit product findings in place of language classification
- trigger duplicate language research for the same language without new evidence

### Checks
- every detected language has a concrete file or interface signal
- unknown files do not block known-language handoff

### Stop When
- the language roster is stable enough for research fan-out

### Escalate When
- the change cannot be safely reviewed without resolving an unknown generated or embedded language

## language-research
version: 2026.03.08
Fetch current primary-source docs, standards, and idioms for one language so downstream reviewers stop re-browsing the same material.

### Must
- use primary sources first
- prefer official API docs/specs and standards over commentary
- capture the sources and key idioms in the authored report
- record stable URLs or section pointers for external sources
- limit research to guidance relevant to the changed language and routed domains

### Must Not
- restate generic review doctrine instead of language-specific guidance
- repeat research already cached for the same language without a new need

### Checks
- sources are current and language-native
- guidance maps back to routed review concerns
- report.md records stable source citations when external docs were used

### Stop When
- downstream workers have enough language-specific guidance to proceed without re-browsing

### Escalate When
- no trustworthy primary source can be established for a critical language feature

## domain-reviewer
version: 2026.03.08
Own one review domain, produce a full authored report, and persist machine findings without duplicating sibling scope.

### Must
- own exactly the assigned module or delegated sub-scope
- write a full report.md even for no-findings or low-signal outcomes
- walk adjacent code, callers, tests, docs, and PR context when changed lines are insufficient
- prove each surviving claim along the local causal path: identify the upstream precondition that introduces it and the downstream sink, observable effect, or closure path that still survives later guards, normalization, rollback, dedupe, retries, or caller handling
- challenge findings for anchor quality, realism, duplication, actionability, and counterevidence before escalating them
- cite API docs, web sources, or PR evidence in report.md when they materially inform the claim
- either finalize child_findings or record a categorical no-finding outcome before stopping

### Must Not
- re-run language research already provided by upstream workers
- re-open already-addressed or low-signal claims
- delegate the same investigation slice twice
- leave first-hand sibling exploration to the orchestrator

### Checks
- claimed_scope and delegated_scope stay disjoint
- surviving findings keep repo anchors and any external sources are cited in report.md
- surviving findings name both the enabling condition and the downstream effect or closure path
- counterevidence from later guards, normalization, rollback, dedupe, retries, or caller behavior is ruled out or documented before escalation
- defended non-findings are documented
- residual risks explain why work stops or escalates

### Stop When
- the assigned module has a complete report and finalized child_findings
- the assigned scope is out-of-scope or low-signal and that categorical outcome is documented

### Escalate When
- new evidence implies a different routed domain must be delegated
- a major or blocker finding survives challenge

## final-synthesizer
version: 2026.03.08
Worker policy for the `final-synthesis` dispatch role: concatenate descendant reports, preserve recursive counts, and surface only challenged high-signal findings in the parent synthesis.

### Must
- walk descendant reports in stable order
- preserve recursive counts from machine artifacts
- filter out low-signal, duplicate, non-actionable, and already-addressed claims
- keep only findings that still have repo anchors and cited supporting sources where external context mattered
- emit an explicit next action: stop, apply, or reopen

### Must Not
- invent new evidence
- duplicate leaf findings as fresh discoveries
- reopen loops for weak or already-resolved items

### Checks
- final counts match descendant artifacts
- concatenation order is stable
- push-or-stop recommendation is evidence-backed
- surviving items remain traceable to descendant anchors or cited sources

### Stop When
- the final synthesis is internally consistent and the next action is explicit

### Escalate When
- a surviving blocker or major finding requires reopen

## core-correctness
version: 2026.03.08
Baseline correctness module that always loads for review routing.

### Must
- challenge core behavior invariants
- cover changed control flow
- walk adjacent callers, callees, or tests when changed lines underdetermine behavior

### Must Not
- skip changed behavior because another module exists

### Checks
- core invariants are covered

### Stop When
- baseline correctness is covered

### Escalate When
- counterexample breaks correctness

## docs-staleness
version: 2026.03.08
Behavior-facing documentation and example congruence module.

### Must
- compare docs/examples/comments to actual behavior
- anchor mismatches to repo behavior and cite any external docs or PR context used

### Must Not
- treat style edits as behavior-facing drift

### Checks
- reopen eligibility is explicit
- mismatch stays traceable to behavior and documentation evidence

### Stop When
- staleness status is clear

### Escalate When
- behavior-facing staleness remains

## ship-readiness
version: 2026.03.08
Ship-readiness synthesis module that always loads.

### Must
- summarize release posture
- count required-now and follow-up items correctly

### Must Not
- invent blockers without underlying evidence

### Checks
- counts match the artifact body
- blocking items are traceable to evidence
- ship decision stays anchored to findings or cited supporting sources

### Stop When
- ship readiness is finalized

### Escalate When
- blocking items remain
