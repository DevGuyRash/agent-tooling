# ADR 0016: Treat answer keys as fallible instruments

- Status: Accepted
- Date: 2026-08-16

## Decision

A private oracle, answer key, reference validation, or expected finding set is measurement evidence, not maker authority merely because it is hidden from candidates. Before candidate exposure, an independent validator must be able to contradict, narrow, or extend it when stronger public contract, source, or executable evidence requires that change.

Freeze the task, key, checker, rubric, and reviewer interface only after that semantic validation. Once candidates have been exposed, a material correction creates a new prospective instrument or round. Preserve the earlier work as evidence about the failed measurement system; do not rewrite its key and present the old outputs as if they had seen the corrected test.

Keep the key open to evidence-backed unanticipated issues without rewarding novelty or finding count. A closed answer inventory is justified only when the governing contract itself is closed and the instrument has established that its representation covers every decision-changing branch it claims.

## Why

The held-out Relay audit fixture was initially validated with two confirmed verifier defects. A candidate-blind rubric author treated that reference as exhaustive and built a polished fact map, non-compensatory gate, numerical weights, and release bands around “exactly two” blockers.

A separate high-reasoning validator inspected and executed the target before any candidate audit was exposed. It reproduced the two known defects and found a third: JSON `schema_version: true` passed because Python Boolean equality satisfied `== 1`, even though Relay's contract requires the JSON number `1`. Repairing only the reference defects would therefore leave another false-acceptance path at the same trust boundary. The right correction was to replace the incomplete key and unsupported decision model before exposure, not to penalize later candidates for disagreeing with private truth.

This is foundational rather than a new edge-case checklist. It changes the authority model of the evaluation system: hidden material can protect blinding, but concealment does not make it true.

The non-audit Driftlight instrument exposed the same problem in deterministic form before any candidate saw the task. Its first telemetry and decision checkers accepted unknown scenarios, malformed nested players, impossible counts, nonexistent artifact paths, and a deferred disposition that still selected a candidate. After those holes were repaired, a second independent validator found that a polished decisive claim could cite opaque prose while an unrelated existing artifact satisfied the package-level evidence list. The final interface requires exact claim-to-artifact linkage and deliberately stops there: a structural checker can prove that a referenced artifact is declared and available, but not that it semantically supports the claim. A third fresh validator accepted that boundary. The two failed validations were useful instrument evidence, not candidate failures, and pre-exposure ordering allowed both to be corrected without contaminating a comparison.

## Consequences

Instrument validation can fail because the reference is wrong even when the public task and candidate prompts are clean. Validators receive enough target authority and executable access to falsify the key, while remaining blind to candidate outputs and desired winners. Reviewers may recognize supported novel findings, but a post-exposure discovery does not retroactively validate the original design.

Evidence custody also preserves the distinction between artifact presence, explicit claim linkage, and semantic sufficiency. A deterministic mechanism may enforce the first two. The third remains a decision-specific judgment unless a faithful closed oracle actually owns it.

Reopen this decision when an adopted external contract makes the answer space formally complete, when the validator lacks safe access to the consequential mechanism, or when new evidence changes the authority order or a decision-changing branch.
