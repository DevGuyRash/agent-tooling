# ADR 0014: Match mechanism assurance to the named hazard

- Status: Accepted
- Date: 2026-08-16

## Decision

A deterministic helper must enforce the custody, integrity, recovery, or persistence boundary its consumer actually needs. Do not add a stronger failure model merely because the mechanism can implement one. Name the event the assurance protects against and preserve the smallest mechanism that makes that event observable or recoverable.

For disposable comparison workspaces, complete preflight, condition-local state, staged atomic publication, source and copy hashes, serialized controller mutations, immutable judgment snapshots, and reveal gating protect the declared experiment boundary. Physical durability through a machine or storage-power failure is a different contract. Per-file or per-directory disk barriers belong only when that survival property is required.

Measure a structural helper on realistic topology, not only tiny fixtures. File count, artifact depth, candidate reuse, and number of reviewer presentations can multiply work even when the input bytes look small. Performance evidence informs the design; it does not create a universal timing threshold.

## Why

The first Split Testing workspace helper forced each copied candidate file to disk twice and then forced every staging directory before publication. Its unit tests passed, but a real nine-reviewer comparison with 7.1 MB of source material spent more than two minutes in anonymization. The assurance exceeded the plugin's temporary-workspace contract and scaled with every candidate-by-reviewer copy.

Removing the unclaimed physical-durability barriers retained locks, complete preflight, byte and mode hashes, staged publication, transaction recovery, tamper checks, and judgment-before-reveal gating. The same comparison topology then anonymized in 1.293 seconds on the evaluation host, while the full structural suite remained green. The useful correction was at the assumed failure model, not a micro-optimization of the copy loop.

The same run exposed an output-boundary version of the problem. `reveal` originally emitted the complete file-by-file mapping to stdout, injecting about 124,700 characters into controller context for one modest comparison even though the durable mapping file already existed. Returning only its path, digest, state, and counts reduced that command output to 672 bytes. The evidence was not discarded; it was moved to the interface whose purpose is retention rather than attention.

This is a general instruction-system lesson: sophisticated assurance can be artifact theater when no maker requirement, named hazard, or observed failure needs it. Its cost may remain invisible in small fixtures and only appear after composition multiplies the mechanism.

## Consequences

Mechanism documentation states what is and is not protected. Tests cover the claimed boundary and adversarial transitions without implying stronger resilience. Representative performance probes are used when topology can amplify work, and an unexplained cost is traced to its assurance premise before implementation tuning.

Reopen this decision when retained evidence must survive host power loss, storage loss, cross-machine handoff, hostile concurrent mutation beyond the declared controller boundary, or another named failure that process-level atomicity and integrity checks cannot cover.
