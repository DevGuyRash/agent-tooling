# Designing comparisons

## What counts as success

Success criteria come from what the consumer must accomplish and what would make relying on the result fail. Separate genuine requirements from preferences, and adequacy (does it work at all) from preference (which adequate option is better). A rubric translates the requirement into assessment; it never quietly replaces the assignment, settles an open preference, or promotes a convenient proxy into success. Keep the source and status of anything that informed the criteria: a requirement, a standard, common practice, and a contested recommendation carry different weight. For each measure, decide before results which way is better, or that neither is: a measure with no better direction describes the alternatives and ranks none of them.

Fix criteria, cases, allocation, retries, and stopping before inspecting the outcomes they govern. When a later change is justified, keep the earlier observation, say why, and treat the revised comparison as new evidence.

## Alternatives and baselines

Include every live option, including the incumbent and, for guidance or instructions, doing nothing extra: a measured cost with no detected benefit argues for removal. A fair baseline keeps the real task, authority, and information. A component question may need a common harness; an end-to-end choice may need each alternative's native setup. Identical prompts or fresh labels do not make a comparison fair on their own.

Alternatives can be directions that each hold alternatives of their own. Fix before results whether the decision is about the direction, the alternative within it, or both, and compare the alternatives within each direction and the directions as wholes over the same cases. A direction's result pools its alternatives, so report one carried by a single alternative as that alternative; choosing a direction and then its best alternative on the same observations overstates both, so confirm the pick on fresh cases.

Comparing every pair in both orders costs N(N-1) judgments per case before repeats. Compare each alternative against a baseline first, then spend further judgments where the remaining uncertainty could change the choice. Permit ties and trade-offs; a forced single winner hides both.

## Cases

A case is any context in which alternatives are tried. Cases distinguish adequate work from plausible incomplete work, including failures every alternative shares, and include sound situations where an unnecessary change would be the failure. Draw variation from actual use, known failure mechanisms, and the conditions that produce the behavior in question: for agent behavior that means the real triggers (a long resumed thread, a human gate, a user saying "continue", an agent-written plan) rather than a tidy restatement of them. A diagnostic case can expose a possibility or boundary without showing how often it occurs.

The requirement a case checks appears in what the executor was given. A hidden case tests whether a stated requirement generalizes; it never introduces a requirement the executor could not know. Cases used to revise an alternative become development evidence; claims that a change generalizes need cases it was not tuned on.

The cases bound the claim. A comparison whose cases share one form, domain, or kind of user says nothing about the others, so a conclusion meant to hold generally needs cases that vary along what it generalizes over, including cases where the alternative's premise does not fit.

## Independence and repetition

Choose the unit that actually receives a condition independently. Runs sharing an agent, session, service, or mutable resource are dependent; repeated scoring of one output measures the judge, not the executor; nine cases run five times each are nine cases for generalization. Interleave conditions so drift in the environment or the provider does not align with one alternative. Identical alternatives (the same material under two labels) show how far chance alone moves each measure; include them when the question is whether a gap is real, and read every gap against theirs.

When behavior varies, repeat each alternative on each case before claiming an advantage, and report counts with intervals. Zero failures in n runs bounds the failure rate at roughly 1 - 0.05^(1/n) with 95% confidence: about 45% for 5 runs, 26% for 10, 10% for 30. Rare failures need cases that start at the moment the failure happens, so they occur often enough to measure.

Searching many alternatives, peeking repeatedly, and picking favorable cases or judges inflate apparent gains; account for them or confirm on fresh cases.

Totals without their units (an analytics export, a published table) support rates and means with their stated n and no spread between units; analyze them as totals and say that variation between units is unknown.

## Contributors, judges, and raters

Give each contributor its mission, the originals and access it needs, its authority, and its output location, and nothing that reveals other contributions, the expected result, or your hypothesis, including your framing of what matters. Before claiming a contributor is fresh or blind, inspect what the host actually passes it (inherited instructions, mounted files, conversation state); isolation that relies on a participant ignoring what it can see is not isolation.

A judge is an instrument. Qualify it against known-good and known-bad cases, strip labels that reveal the alternative (including disposition vocabulary a framing introduced), prefer deterministic checks on resulting state, and counter self-preference with a judge from another model family. Judges favor longer answers and the first position; swapping order addresses position only. Agreement between judges measures agreement, not correctness; compare concrete behavior against explicit criteria where tiers disagree. Any instrument observes from where the behavior it measures cannot move it; one that depends on what the observed party controls misses whatever that party does differently.

People who rate or choose are instruments too: record who they are and what they were shown, keep them blind to which alternative is the favorite, and fix the scale before they use it. Ordinal levels are ordered, not equally spaced, so report counts per level; a mean of ratings invents a distance. Where absolute ratings drift between raters, ask for choices between alternatives or rankings, balanced for order, and report how many raters chose each way, ties and no-choice included.

A handoff or summary supplies information, not understanding. Reconstruct a consequential judgment you rely on from the relevant originals, and trace every decisive claim to a retained record. Summaries guide navigation and do not become authority.

## Attribution and limits

Keep apart infrastructure failures, invalid cases, instrument errors, candidate behavior, and causal explanation. Assign a cause only when evidence separates it from plausible alternatives, typically by intervention: change one thing, keep the rest, repeat. Removing an instruction after it shaped a plan tests response to a late edit, not the instruction's original influence; branch before the first relevant exposure instead, and include unchanged reruns as a baseline and a meaning-preserving rewording as a control for incidental wording sensitivity. When a premise or measurement fails, revisit every judgment and recommendation that depended on it.

Observational data (campaign analytics, logs, existing records) shows association unless assignment was random: state how each alternative came to be shown or used and what else differed (audience, timing, budget) before reading a difference as an effect.

Preserve differences in populations, operating conditions, tails, and interactions when collapsing them could change the action.

## Decisions without measurement

When nothing can be observed, set out each alternative's claims against the criteria, each cell holding the claim and its basis (a source, an expert, an assumption) rather than a score. Where criteria must be traded off, the weights belong to the person deciding: show any they gave and the arithmetic, and whether the leader changes under other weights. A matrix organizes a judgment and measures nothing; say in the report which cells are judgments. Words are evidence: keep a quotation with the value it explains, and let it count when the criteria fixed beforehand said it would.

## Stopping

Stop when the choice is resolved, no obtainable evidence can resolve it, the budget is reached, or the next observation cannot change what anyone would do. When the tools, material, and authority to observe are available and observation is what the decision needs, run it rather than proposing it.
