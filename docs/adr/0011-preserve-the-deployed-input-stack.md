# ADR 0011: Preserve the deployed input stack in comparative trials

- Status: Accepted
- Date: 2026-08-16

## Decision

A comparative execution must receive the input stack the evaluated system would actually receive. Keep evaluator objectives, diagnostic rationale, rubric content, expected behavior, and private truth outside executor-visible material unless an independent layer of the real deployment supplies the same information. When a condition is meant to supply behavior-guiding content, putting its intended contribution in the common prompt changes the condition and cannot establish the condition's value.

Validate the exact executor-visible payload after condition insertion and launcher composition. Validating only source tasks, prompt fragments, or placeholders is insufficient when the final composition can add answer-bearing guidance. If the deployed system genuinely includes a common base policy, retain it symmetrically and define the condition as the incremental layer being tested.

When the controller created or materially adapted the task, rubric, oracle, checker, or composed payload for a consequential comparison, a separate fresh context validates that final measurement system before candidate exposure. The order is load-bearing: candidate outputs can reveal the planted distinction and make a later repair no longer held out. Maker-supplied settled material does not require ceremonial independent review merely because it enters a comparison.

## Why

Three fresh Split Testing orchestrators independently made the same mistake in the Harborlight holdout. The alternatives were instruction sets whose differences included truthful capability claims, privacy handling, message-boundary authority, and proportionate escalation. Each assisted orchestrator then repeated some or all of those desired behaviors in the common executor prompt. One explicitly observed that Amber executions stayed truthful “despite” Amber's completed-tense instruction—the common prompt had supplied the very behavior the trial was supposed to measure.

The most elaborate run produced three matched executions per proposal and twenty-four blind review judgments. Its behavioral scores tied Birch and Cobalt, and reviewers selected Birch more often, because the common prompt had suppressed Birch's and Amber's planted failures. The final report still recommended Cobalt only by returning to the immutable proposal text and maker contract. That static eligibility correction was sound, but it did not repair the contaminated behavioral comparison. More executions, stronger custody, and more reviewers amplified the wrong system rather than adding evidence about the intended one.

The public instrument itself had been independently validated before execution. The contamination entered later, when orchestrators composed the worker brief. This showed that source-level task validation and generic prompt-purity language did not cover the actual causal boundary.

A later corrected-source orchestrator produced a materially cleaner common brief but still launched its controller-authored task, rubric, and final payload without the independent semantic validation the design reference required. The failure occurred after the agent had read that reference, showing that a buried design suggestion did not reliably protect a one-way contamination boundary. The obligation moved into the semantic kernel; its detailed falsification scope remains in the focused design reference.

The next diagnostic obeyed the new kernel superficially but made the validation claim impossible. It launched a fresh pre-exposure validator to detect duplicated condition contribution while expressly forbidding that validator from reading any condition instruction; the validator saw only the common task, rubric, and reviewer brief. The correction defines the composed payload at the condition level: private labels may be removed and outputs remain ungenerated, but no behavior-changing condition layer may be withheld from a check whose conclusion depends on it.

A subsequent diagnostic gave the validator every composed condition payload yet still repeated the maker's desired truthfulness, privacy, authority, and proportionality behavior in the common worker brief. Because the validator saw no provenance for the common layer, it treated the evaluator's true objective as part of the deployed interface and passed the instrument. Only post-reveal output inspection exposed that the common prompt had again supplied part of Cobalt's treatment. The correction now requires a condition-independent deployed source for every common behavior-guiding layer and makes that provenance available to composition validation.

Two corrective Harborlight rounds then removed the leaked outcome guidance, but the resulting reviewers still found no stable advantage among Amber, Birch, and Cobalt. The harness had flattened each proposed governing instruction into the same ordinary user prompt as the customer cases. That is not the deployed assistant interface: user-level quoted guidance and an adopted system or policy layer can receive different model obedience even when their text is identical. The tie is retained as evidence about the flattened prompt condition, not about production policy value. Composition evidence now preserves role, precedence, placement, and timing as well as bytes.

## Consequences

Experiment records preserve the full composed worker prompt and identify which layer supplied each behavior-changing instruction when that distinction affects the claim. Instrument validation sees the final worker-visible payload and launch authority before candidate exposure. A run whose common material duplicates a condition's intended contribution, or assigns that contribution a different role or precedence, remains useful failure evidence but is excluded from claims about the deployed contribution.

Task sufficiency remains mandatory: workers receive every real fact, authority, constraint, and interface they would have in deployment. The correction removes evaluator-only guidance, not needed context. Reopen this decision when the actual deployed prompt stack changes or a condition is redefined as an incremental layer above a fixed common policy.
