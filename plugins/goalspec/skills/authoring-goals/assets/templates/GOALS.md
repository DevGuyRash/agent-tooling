# GOALS.md

This file is a registry, not an execution target. Do not run `/goal` against this entire file. Compile one ready item into `.goals/current.md` before execution.

## Active

_No active goal._

## Ready

### G-001: Example ready goal

- Status: ready
- Type: bugfix | test | docs | refactor | research | maintenance-slice | campaign-child
- Terminal state: [checkable state]
- Verifier: [command / artifact / gate]
- Scope: [bounded area]
- Risk: low | medium | high | extreme
- Depends on: none
- Contract: pending

## Conditional

### G-002: Example conditional goal

- Status: conditional
- Missing: [verifier / scope / budget / decision]
- Suggested repair: [finite version]

## Deferred (far map)

[The destination beyond the active wave, enumerated so nothing the sources
name is invisible. One entry per far work unit (milestone grain is fine),
each naming the gate or decision that opens it. These are map entries, not
launchable goals — they materialize into campaign children when their gate
opens.]

### [M2: Example far milestone]

- Status: deferred
- Opens when: [the gate/verdict/decision that unlocks this work]
- Source: [the section of the source document that defines it]

## Blocked / Not Launchable

### G-003: Example vague goal

- Status: not-launchable
- Reason: no terminal state, verifier, budget, or frozen target
- Needs: [specific missing data]

## Follow-Up Candidates

### F-001: Example follow-up

- Source: discovered during G-000
- Status: candidate
- Note: not required for active goal
