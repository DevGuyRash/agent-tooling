# ADR 0018: Compare at a shared consequence boundary

## Status

Accepted.

## Context

A blind decision-report trial produced two correct clearance-time maxima: 50.2 minutes for one facility and 60.8 minutes for another. The maxima came from different cohort/case pairs whose deadlines were 60 and 70 minutes. Subtracting them yielded a true 10.6-minute number, but presenting that number as a facility benefit made unlike limiting observations look like a common consequence. Two of three blind reviewers slightly preferred the report that used the common deadline-slack comparison instead.

The defect is broader than maxima. Equal units do not make measurements comparable when populations, cases, thresholds, horizons, scales, or loss meanings differ. Totals and averages can hide the same problem.

## Decision

Comparative claims SHALL preserve a shared decision-relevant consequence boundary. A difference, rank, or aggregate requires either like-for-like observations or an adopted normalization, frequency, weight, loss, or invariance that makes the transformation meaningful. Otherwise the observations remain separate facts and their numerical difference SHALL NOT be presented as an option benefit.

This is an outcome invariant, not a required analysis method or report form.

## Consequences

- Correct arithmetic can still be rejected as a decision-invalid comparison.
- Reviewers and auditors inspect the denominator and consequence semantics, not only values and units.
- Profiles, interactions, and thresholds remain visible when aggregation would change the decision.
- A maker-provided consequence model can authorize normalization; absent one, the system preserves the frontier rather than inventing comparability.

## Evidence and reopening condition

The rule follows the observed blind preference and the fixed task's explicit deadline semantics. It should be revisited if representative trials show that the control suppresses useful comparisons whose consequence equivalence is otherwise unambiguous.
