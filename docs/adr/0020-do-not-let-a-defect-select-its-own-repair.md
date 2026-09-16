# ADR 0020: Do not let a defect select its own repair

- Status: Accepted
- Date: 2026-08-16

## Decision

A contradiction or failing observation establishes that the represented outcome cannot remain as it is. It does not, by itself, establish which conflicting declaration expresses maker intent or which change is the smallest safe repair.

When plausible repairs serve materially different meanings, keep those meanings reachable until maker authority, an adopted consumer contract, or outcome evidence selects among them. State the decision and evidence needed to choose rather than promoting the evaluator's reading into a requirement.

A repair-scope claim needs evidence about what must remain working as well as what fails. A failing probe can diagnose a defect. Calling a repair narrow, sufficient, or release-ready additionally requires support that the change preserves consequential adjacent behavior. The representation is open: source semantics, focused passing cases, executable invariants, downstream observations, or another faithful check may supply that boundary.

## Why

In the matched Dispatch Skill Auditor trial, all three blind reviewers of one replicate preferred the revised audit. Their shared decisive premise was that the revised audit correctly changed an absent plugin starter from `queue-sorter` to `operator-handoff`, while the comparison audit's `queue-triage` repair would select the wrong operation. A fresh condition-blind fact-check found that the target itself supported two meanings: the prompt prose named handoff composition, while the stale skill name and another target description suggested queue normalization or a queue-first pipeline. The contradiction was real, but neither proposed replacement was uniquely authorized. All three preferences lost their claimed factual separator.

A different replicate exposed the second half of the same mistake. Both audits reproduced the two hard failures, but the preferred audit also retained focused evidence that same-identity update selection, a neighboring sort branch, and non-monitoring handoff branches still worked. Three blind preferences for that audit survived source reconciliation, although the fact-check narrowed what the passing probes actually covered. The additional evidence mattered because it bounded the proposed change; it did not matter merely because there were more artifacts.

The following candidate made the authority correction reliably but one replicate again lost the preservation advantage: it proposed suitable future regression tests without retaining evidence from the currently working neighboring branches. Blind reviewers preferred the older audit on that replicate, and condition-blind fact-checking preserved the preference. A test recommendation is a repair plan; it is not current evidence that the proposed repair boundary is already understood.

The lesson is not a mandatory pair of failing and passing tests. It is an authority and evidence boundary: failure establishes repair need, maker intent selects meaning, and preservation evidence supports repair scope. Collapsing those roles creates confident but unactionable recommendations.

## Consequences

Audits, plans, and implementation reviews distinguish a supported defect from a selected repair. They preserve alternatives when target signals remain materially ambiguous and name the evidence or decision that would resolve them. Recommendations may still choose directly when maker authority or observed outcome supplies that choice.

Claims that a change is minimal, sufficient, safe, or ready remain conditional until the evidence also covers consequential behavior the change must preserve. This does not require exhaustive branch enumeration; it requires enough discrimination that a different repair boundary would no longer change the decision.

Reopen this decision when the governing interface formally makes one declaration authoritative over the others, or when repair technology can guarantee preservation without additional observational evidence.
