# Full-Cycle Fallback

Use `mpcr fullcycle plan --output <path>` as a preview only. The output path is resolved from the current working directory, `.json` writes JSON, other extensions write TOML, and `mpcr fullcycle checkpoint --artifact-file <path>` is the step that persists the chosen convergence state for `mpcr fullcycle state`. Run convergence planning only after the session has finalized a current `parent_review`; `application_result` and `verification_result` add more convergence signal once the applicator phase has run. Use `mpcr session cleanup --session-dir <path>` before rerouting a discarded canonical full-cycle session.

## full-cycle
version: 2026.03.08
Preserve severity-bounded reopen and behavior-facing staleness handling across review, apply, and verify cycles.

### Must
- persist convergence_state artifacts
- continue the cycle whenever stop_condition is reopen_required
- reopen only for blocker/major/staleness/verification failure/fix regression
- allow one bounded terminal cleanup pass
- carry forward only anchored or verified unresolved evidence into reopen decisions
- reopen only when the unresolved claim still survives end-to-end challenge across review evidence, current code, and verification results

### Must Not
- reopen for minor or nit alone
- depend on v1 proof-packet assumptions
- collapse convergence state into session prose

### Inputs
- parent_review
- application_result
- verification_result
- current convergence_state

### Outputs
- next convergence_state
- next route focus inputs

### Checks
- keep reopen severity floor at major
- keep behavior_staleness_reopens true
- carry only compact pointers in session
- reopen reasons remain traceable to anchored findings or verification evidence
- reopen reasons still survive both introduction-side and closure-side challenge instead of repeating a claim already neutralized downstream

### Stop When
- stop_condition is converged
- hard validation fails

### Escalate When
- verification fails
- behavior-facing staleness remains
- major findings remain after application

### Anti Patterns
- infinite reopen loops
- using minor cleanup to reopen the cycle

### Examples
- Only minor cleanup remains -> terminal cleanup allowed.
- Verification failure -> reopen with focused files and surfaces.

### Schema
- cycle_index
- reopen_threshold
- reopen_triggers
- next_route_inputs
- stop_condition

## reopen
version: 2026.03.08
Escalate a full-cycle reopen only when severity-bounded rules or staleness rules require it.

### Must
- reopen only for blocker, major, behavior staleness, verification failure, or fix regression
- reopen only when the unresolved claim still survives both the introducing condition check and the downstream effect or closure path after application and verification

### Must Not
- reopen for minor or nit alone

### Checks
- reason codes are categorical
- severity floor remains major
- reopen reasons still survive introduction-side and closure-side challenge instead of repeating a claim already neutralized downstream

### Stop When
- reopen decision is finalized

### Escalate When
- allowed trigger is present

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
