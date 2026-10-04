# Designing comparisons

## What counts as success

Success criteria come from what the consumer must accomplish and what would make relying on the result fail. Separate genuine requirements from preferences, and adequacy (does it work at all) from preference (which adequate option is better). A rubric translates the requirement into assessment; it never quietly replaces the assignment, settles an open preference, or promotes a convenient proxy into success. Keep the source and status of anything that informed the criteria: a requirement, a standard, common practice, and a contested recommendation carry different weight.

Fix criteria, cases, allocation, retries, and stopping before inspecting the outcomes they govern. When a later change is justified, keep the earlier observation, say why, and treat the revised comparison as new evidence.

## Alternatives and baselines

Include every live option, including the incumbent and, for guidance or instructions, doing nothing extra: a measured cost with no detected benefit argues for removal. A fair baseline keeps the real task, authority, and information. A component question may need a common harness; an end-to-end choice may need each alternative's native setup. Identical prompts or fresh labels do not make a comparison fair on their own.

Comparing every pair in both orders costs N(N-1) judgments per case before repeats. Compare each alternative against a baseline first, then spend further judgments where the remaining uncertainty could change the choice. Permit ties and trade-offs; a forced single winner hides both.

## Cases

Cases distinguish adequate work from plausible incomplete work, including failures every alternative shares, and include sound situations where an unnecessary change would be the failure. Draw variation from actual use, known failure mechanisms, and the conditions that produce the behavior in question: for agent behavior that means the real triggers (a long resumed thread, a human gate, a user saying "continue", an agent-written plan) rather than a tidy restatement of them. A diagnostic case can expose a possibility or boundary without showing how often it occurs.

The requirement a case checks appears in what the executor was given. A hidden case tests whether a stated requirement generalizes; it never introduces a requirement the executor could not know. Cases used to revise an alternative become development evidence; claims that a change generalizes need cases it was not tuned on.

The cases bound the claim. A comparison whose cases share one form, domain, or kind of user says nothing about the others, so a conclusion meant to hold generally needs cases that vary along what it generalizes over, including cases where the alternative's premise does not fit.

## Independence and repetition

Choose the unit that actually receives a condition independently. Runs sharing an agent, session, service, or mutable resource are dependent; repeated scoring of one output measures the judge, not the executor; nine cases run five times each are nine cases for generalization. Interleave conditions so drift in the environment or the provider does not align with one alternative.

When behavior varies, repeat each alternative on each case before claiming an advantage, and report counts with intervals. Zero failures in n runs bounds the failure rate at roughly 1 - 0.05^(1/n) with 95% confidence: about 45% for 5 runs, 26% for 10, 10% for 30. Rare failures need cases that start at the moment the failure happens, so they occur often enough to measure.

Searching many alternatives, peeking repeatedly, and picking favorable cases or judges inflate apparent gains; account for them or confirm on fresh cases.

## Contributors and judges

Each contributor gets its mission, the originals and access it needs, its authority, and its output location, and nothing that reveals other contributions, the expected result, or your hypothesis, including your framing of what matters. Before claiming a contributor is fresh or blind, inspect what the host actually passes it (inherited instructions, mounted files, conversation state); isolation that relies on a participant ignoring what it can see is not isolation.

A judge is an instrument. Qualify it against known-good and known-bad cases, strip labels that reveal the alternative (including disposition vocabulary a framing introduced), prefer deterministic checks on resulting state, and counter self-preference with a judge from another model family. Judges favor longer answers and the first position; swapping order addresses position only. Agreement between judges measures agreement, not correctness; compare concrete behavior against explicit criteria where tiers disagree. Any instrument observes from where the behavior it measures cannot move it; one that depends on what the observed party controls misses whatever that party does differently.

A handoff or summary supplies information, not understanding. Whoever relies on a consequential judgment reconstructs it from the relevant originals, and every decisive claim traces to a retained record. Summaries guide navigation and do not become authority.

## Attribution and limits

Keep apart infrastructure failures, invalid cases, instrument errors, candidate behavior, and causal explanation. Assign a cause only when evidence separates it from plausible alternatives, typically by intervention: change one thing, keep the rest, repeat. Removing an instruction after it shaped a plan tests response to a late edit, not the instruction's original influence; branch before the first relevant exposure instead, and include unchanged reruns as a baseline and a meaning-preserving rewording as a control for incidental wording sensitivity. When a premise or measurement fails, revisit every judgment and recommendation that depended on it.

Preserve differences in populations, operating conditions, tails, and interactions when collapsing them could change the action.

## Stopping

Stop when the choice is resolved, more authorized evidence cannot resolve it, the budget is reached, or the next observation cannot change what anyone would do. Report unresolved required work as unresolved. When the tools, material, and authority to observe are available and observation is what the decision needs, run it rather than proposing it.
