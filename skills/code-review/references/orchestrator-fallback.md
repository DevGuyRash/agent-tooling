# Orchestrator Fallback

Use semantic routing first. Load mode second. Load worker and module packs only for the selected route. Load escalation packs only after triggers fire. Load examples only on uncertainty, malformed output, retry, or explicit request.

# surface-mapper
version: 2026.03.08
Build the semantic surface map and determine whether staleness checks are required.

## Must
- emit risk_surface_record values
- mark behavior-facing artifacts
- decide staleness_required deterministically

## Must Not
- route by churn alone

## Checks
- surface weights match defaults
- suggested modules include always-on modules later

## Stop When
- surface_map is emitted

## Escalate When
- new surface weight >= 4 appears

# contract-comparer
version: 2026.03.08
Compare API, schema, CLI, config, and migration contracts for congruent behavior across versions.

## Must
- compare before and after contracts
- call out compatibility drift

## Must Not
- treat implementation refactors as contract drift without evidence

## Checks
- claim references a concrete contract element
- verification is actionable

## Stop When
- contract deltas are covered

## Escalate When
- compatibility break is unguarded

# exploit-tracer
version: 2026.03.08
Trace exploit paths across auth, privilege, and input-validation surfaces.

## Must
- follow untrusted input to privileged operations
- state exploit scenario concretely

## Must Not
- emit abstract security claims without path evidence

## Checks
- scenario is reproducible
- severity is proportional

## Stop When
- security path coverage is complete

## Escalate When
- privilege or auth bypass is plausible

# congruence-checker
version: 2026.03.08
Check congruence between behavior-facing code changes and docs, comments, examples, or operator guidance.

## Must
- treat staleness as first-class
- check docs whenever behavior-facing evidence requires it

## Must Not
- assume docs are irrelevant when code changes behavior

## Checks
- behavior-facing mismatch is explicit
- reopen_eligible is set correctly

## Stop When
- staleness coverage is complete

## Escalate When
- behavior-facing staleness remains

# simplification-checker
version: 2026.03.08
Interrogate scope creep and overengineering when the route or revision indicates excess complexity.

## Must
- justify scope-creep claims with concrete simplification paths

## Must Not
- treat any abstraction as overengineering

## Checks
- recommendation simplifies behavior or structure
- severity stays bounded

## Stop When
- scope-creep concerns are resolved

## Escalate When
- change scope meaningfully exceeds routed need
