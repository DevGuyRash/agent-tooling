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

# review-composite
version: 2026.03.08
Single-worker direct review that performs surface mapping, baseline correctness, staleness when needed, and ship readiness.

## Must
- produce child_findings or parent_review artifacts only
- cover baseline correctness
- cover staleness when required
- cover ship readiness

## Must Not
- delegate to an orchestrator layer
- emit narrative-only output

## Checks
- keep scope bounded to routed surfaces
- record loaded_policy_refs
- compute fingerprints for findings

## Stop When
- child_findings artifact is finalized

## Escalate When
- new high-weight surface appears

# invariant-challenger
version: 2026.03.08
Use theorem/disproof style checks for correctness, integrity, and concurrency concerns.

## Must
- state the invariant
- attempt a counterexample
- emit defended or failed evidence

## Must Not
- use rhetorical prose as evidence

## Checks
- anchors are precise
- defended checks include attempted_counterexample

## Stop When
- targeted concern is covered

## Escalate When
- counterexample implies major or blocker

# release-risk-assessor
version: 2026.03.08
Assess ship readiness after concern-specific review is complete.

## Must
- synthesize ship risk last
- record blocking items and verdict

## Must Not
- duplicate lower-level findings as new evidence

## Checks
- blocking item counts match required_now
- ship_readiness is consistent

## Stop When
- parent_review is emitted

## Escalate When
- blocking items remain

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
