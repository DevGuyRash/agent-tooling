# Full-Cycle Fallback

# full-cycle
version: 2026.03.08
Preserve severity-bounded reopen and behavior-facing staleness handling across review, apply, and verify cycles.

## Must
- persist convergence_state artifacts
- reopen only for blocker/major/staleness/verification failure/fix regression
- allow one bounded terminal cleanup pass

## Must Not
- reopen for minor or nit alone
- depend on v1 proof-packet assumptions
- collapse convergence state into session prose

## Inputs
- parent_review
- application_result
- verification_result
- current convergence_state

## Outputs
- next convergence_state
- next route focus inputs

## Checks
- keep reopen severity floor at major
- keep behavior_staleness_reopens true
- carry only compact pointers in session

## Stop When
- stop_condition is converged
- fresh start is required
- hard validation fails

## Escalate When
- verification fails
- behavior-facing staleness remains
- major findings remain after application

## Anti Patterns
- infinite reopen loops
- using minor cleanup to reopen the cycle

## Examples
- Only minor cleanup remains -> terminal cleanup allowed.
- Verification failure -> reopen with focused files and surfaces.

## Schema
- cycle_index
- reopen_threshold
- reopen_triggers
- next_route_inputs
- stop_condition

# reopen
version: 2026.03.08
Escalate a full-cycle reopen only when severity-bounded rules or staleness rules require it.

## Must
- reopen only for blocker, major, behavior staleness, verification failure, or fix regression

## Must Not
- reopen for minor or nit alone

## Checks
- reason codes are categorical
- severity floor remains major

## Stop When
- reopen decision is finalized

## Escalate When
- allowed trigger is present

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
