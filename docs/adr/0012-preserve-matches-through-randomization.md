# ADR 0012: Preserve match structure through blinded randomization

- Status: Accepted
- Date: 2026-08-16

## Decision

Blinding and random presentation must not erase the condition-neutral identity needed to interpret a comparison. When outputs are matched by task, case, subject, block, or another shared exposure, each reviewer receives an opaque identity that preserves that correspondence across candidates without revealing semantic case names or condition identities. A randomized view that cannot show which outputs share a match cannot support a matched judgment.

The structural workspace helper may generate this opaque view index from controller-supplied match identity. It does not decide what constitutes a valid match, whether reviewers should see it, or how the result is scored. Designs that do not need matched review may omit the identity.

## Why

In a fresh four-way Harborlight comparison, one orchestrator correctly created seventy-two retained executions and randomized the candidate and sample presentation. The helper preserved every artifact but independently permuted samples within each candidate. The first review brief assumed that sample labels aligned by case, so its judgments were invalid. A corrected pass then discovered that the labels still did not expose the case correspondence and was invalidated as well. Only a third pass, after the controller reconstructed a condition-neutral case index from private assignments, could support comparison.

Nothing was wrong with the candidate outputs or the desire to randomize order. The foundational mistake was treating concealment as information removal rather than protecting a named inference. The reviewer needed to know which anonymous outputs answered the same anonymous case; semantic case names and condition mappings could remain hidden.

## Consequences

Review views carry the smallest opaque grouping needed for the declared comparison, and custody hashes cover that index. Reviewers do not infer matching from directory order or independently randomized sample numbers. When a view lacks required correspondence, preserve the attempted judgment as harness evidence and obtain a fresh judgment after repairing the view; later synthesis cannot invent the missing match.

Opaque grouping is not a universal worksheet or topology. The controller decides whether a match is decision-relevant, and the helper exposes only the structure explicitly supplied for that purpose. Reopen this decision if a comparison's intended judgment is deliberately unpaired or if revealing even opaque grouping would disclose the condition under test.
