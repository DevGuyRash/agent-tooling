# ADR 0021: Preserve authority across runtime identity

- Status: Accepted
- Date: 2026-08-16

## Decision

When a contract assigns different authority, mutability, confidentiality, or lifecycle to logical roles, establish whether those roles remain distinct in the runtime system. Permission to replace, publish, expose, or mutate one role does not transfer when it resolves to the same underlying object as an independently protected role.

Names, parameters, schema fields, and preflight checks establish represented roles; they do not by themselves establish object identity over the operation. Different names can alias one object, one name can resolve to a different object after a check, and a destination can be backed by an input or protected state. The required evidence is that the composed mechanism preserves the authority boundary at the consequence and concurrency horizon the target promises. No fixed alias or filesystem-case inventory is implied.

Keep this judgment semantic. Deterministic mechanisms may enforce or probe identities, containment, atomicity, and mutation, but a helper cannot decide which role is authorized or what consequence matters without the governing contract.

## Why

A held-out eDNA Skill Auditor target expressly allowed replacement of one output manifest while forbidding edits to collection records, profiles, and declared sample bytes. The builder validated each named input and output separately, then passed the caller's output path to `os.replace`. With `--replace`, an output naming a declared sample, collection CSV, or profile destroyed that protected input while returning success. Without `--replace`, a dangling destination symlink was also replaced, and the separate existence check left a concurrent-creator overwrite window.

All three assisted audits found the target's timestamp, order, containment, schema, and instruction- design defects. None found the destructive input/output identity collapse or the observed dangling- symlink boundary; one mentioned only the broader race. Unguided controls found the no-clobber defect in every replicate and the direct input alias in one. Initial blind reviewers still preferred all three assisted reports because a rubric over-weighted their better instruction-design analysis. Condition-blind fact-checking reversed two comparisons and narrowed the third after reproducing the hard mutation boundary.

The missed property was not “remember to test symlinks.” It was that independently authorized roles had been reasoned about as though their labels guaranteed separate runtime objects. That failure generalizes to files, records, cache entries, database rows, destinations, credentials, handles, and other mechanisms without turning those examples into a closed taxonomy.

A direct wording intervention subsequently made the composition principle more explicit while leaving the audit task generic. Only one of three fresh auditors recovered the destructive input/output collapse, two omitted it again, and the condition cost about 18 percent more mean input and wall time than the prior revision. The wording was reverted. This ADR records a real contract and design boundary; its presence in prose is not evidence that an auditor discovered or verified it.

A follow-up instruction instead required independent falsification before a sufficient repair or release-readiness claim. All three auditors deferred readiness to a future fresh review, but none executed that review in the current audit or recovered the identity collapse; one also lost the previously consistent no-clobber race. It too was reverted. Honest deferral is safer than a false completion claim, but it does not satisfy a maker requirement to find the hard defect.

## Consequences

Audits and designs preserve role-specific authority through composition, not only at each local input check. Where identity collapse could change safety, correctness, release scope, or repair, the evidence covers the relevant runtime object and state transition. A successful operation on the nominal destination is not success when it mutates a separately protected role.

Repairs remain mechanism- and contract-specific. They may reject aliases, separate namespaces, retain object handles, use atomic primitives, narrow authority, or change the interface, but this ADR does not prescribe one route. Claims of complete repair remain conditional until consequential adjacent behavior and the intended identity horizon are also preserved.

Reopen this decision when a governing interface explicitly makes the roles interchangeable, or when the runtime can prove role separation independently of the application mechanism.
