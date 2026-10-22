# Designing comparisons

## What counts as success

Success criteria come from what the consumer must accomplish and what would make relying on the result fail. Separate genuine requirements from preferences, and adequacy (does it work at all) from preference (which adequate option is better). A rubric translates the requirement into assessment; it never quietly replaces the assignment, settles an open preference, or promotes a convenient proxy into success. Keep the source and status of anything that informed the criteria: a requirement, a standard, common practice, and a contested recommendation carry different weight. For each measure, decide before results which way is better, or that neither is: a measure with no better direction describes the alternatives and ranks none of them.

Keep adequacy, preference, and excellence apart. Adequacy asks whether an alternative meets the legitimate requirements and avoids unacceptable failures; preference asks which adequate alternative better serves the decider's priorities; excellence asks whether it meets a high bar grounded independently of the alternatives present, such as strong reference work, demonstrated performance in use, or informed expert judgment. Winning against weak alternatives shows only that it is the best of them. A regulatory minimum, a practitioner convention, and a customer preference are different kinds of bar.

A criterion's grounds can be the decider's purpose, an obligation, a practice that competent work in the field implies, observed failures, an affected person's experience, or a reasoned inference about what makes the result useful; the last keeps a genuinely new alternative from being judged only by conventions that did not anticipate it. Record the grounds with the criterion, so a proposal never becomes a requirement because its origin was forgotten.

Discover widely before narrowing. Draw candidate concerns from the request, the field's practitioners and standards, the people affected, known failure mechanisms, and interactions, then measure those that could change adequacy, preference, or justified reliance within the claim's scope. Keep the rest visible, grouped by the reason they were set aside: they cannot change the decision, they lie outside the claim's scope, or nothing can observe them. A concern nothing can observe is unassessed, and if it is in scope the conclusion carries it as a limit. A count of dimensions is not coverage.

Challenge a newly built evaluation before results when others will rely on the decision. The challenger forms its own view from the originals before reading the proposed criteria, then looks for a result that would pass and still fail the intended use, a good result that would fail for an irrelevant reason, and a consequential concern nothing measures; finding no supported counterexample is a valid result. A supported concern gets a disposition (added, measured another way, carried as a limit, or rejected with its reason), and one raised by a single contributor does not lapse for that reason.

Fix criteria, cases, allocation, retries, and stopping before inspecting the outcomes they govern. When a later change is justified, keep the earlier observation, say why, and treat the revised comparison as new evidence.

## Alternatives and baselines

Include every live option, including the incumbent and, for guidance or instructions, doing nothing extra: a measured cost with no detected benefit argues for removal. A fair baseline keeps the real task, authority, and information. A component question may need a common harness; an end-to-end choice may need each alternative's native setup. Identical prompts or fresh labels do not make a comparison fair on their own.

Alternatives can be directions that each hold alternatives of their own. Fix before results whether the decision is about the direction, the alternative within it, or both, and compare the alternatives within each direction and the directions as wholes over the same cases. A direction's result pools its alternatives, so report one carried by a single alternative as that alternative; choosing a direction and then its best alternative on the same observations overstates both, so confirm the pick on fresh cases.

## Conditions and setup

Which question the comparison answers decides how setup is treated:

| Question | Setup |
|---|---|
| Which component performs better under common conditions? | Everything outside the component stays the same across alternatives. |
| Which complete alternative performs better under its intended conditions? | Each gets its intended setup, such as a package's supported installation or a recipe's own equipment and preparation; the intended differences are reported. |
| Which alternative is better to adopt from the specified starting point? | Installation, discovery, and activation failures are outcomes, with their costs, and nothing requires them to succeed before scoring. |

Scope each setup item as common to every workspace, specific to one alternative, or under test: a hook that one software package needs, installed in the other's workspace, contaminates that control, and the same hook missing from its own workspace removes the treatment; a proofing step one bread recipe calls for works the same way.

Setup starts at none, and none proposed is not none needed. Contributors in fresh contexts read each alternative's own documentation and dependencies and propose what its workspaces need, with grounds. An item is admitted only when a contributor other than its proposer has checked those grounds and that scope; agreement without the check admits nothing, and a lone proposal whose grounds hold is enough. Install a proposed item first in a disposable preparation workspace and probe it under the conditions the scored runs will use (for software, the same launch mode, permissions, and isolation): the hook fires, the tool loads, the oven holds its temperature. A probe proves preconditions; it never forces a behavior the comparison measures, such as loading an optional skill whose discovery is under test, and its effects never reach a scored workspace. When a necessary item cannot be admitted, block the comparison or narrow its claim to the conditions that held. All of this concerns prerequisites outside the behavior under test: in an adoption comparison, setting an alternative up is part of what is observed. Retain the identity of consequential setup alongside the instructions and scenarios, so a later run can show it ran under the same conditions.

## Allocating judgments

Comparing every pair in both orders costs N(N-1) judgments per case before repeats. Compare each alternative against a baseline first, then spend further judgments where the remaining uncertainty could change the choice. Permit ties and trade-offs; a forced single winner hides both.

## Cases

A case is any context in which alternatives are tried. Cases distinguish adequate work from plausible incomplete work, including failures every alternative shares, and include sound situations where an unnecessary change would be the failure. Draw variation from actual use, known failure mechanisms, and the conditions that produce the behavior in question: for agent behavior that means the real triggers (a long resumed thread, a human gate, a user saying "continue", an agent-written plan) rather than a tidy restatement of them. A diagnostic case can expose a possibility or boundary without showing how often it occurs.

The requirement a case checks appears in what the executor was given, or follows from competent practice the request implies and is recorded with its grounds; a reviewer's preferred practice is not such a requirement. A hidden case tests whether a stated requirement generalizes; it never introduces a requirement the executor could not know. Cases used to revise an alternative become development evidence; claims that a change generalizes need cases it was not tuned on.

The cases bound the claim. A comparison whose cases share one form, domain, or kind of user says nothing about the others, so a conclusion meant to hold generally needs cases that vary along what it generalizes over, including cases where the alternative's premise does not fit.

## Independence and repetition

Choose the unit that actually receives a condition independently. Runs sharing an agent, session, service, or mutable resource are dependent; repeated scoring of one output measures the judge, not the executor; nine cases run five times each are nine cases for generalization. Interleave conditions so drift in the environment or the provider does not align with one alternative. Identical alternatives (the same material under two labels) show how far chance alone moves each measure; include them when the question is whether a gap is real, and read every gap against theirs.

When behavior varies, repeat each alternative on each case before claiming an advantage, and report counts with intervals. Zero failures in n runs bounds the failure rate at roughly 1 - 0.05^(1/n) with 95% confidence: about 45% for 5 runs, 26% for 10, 10% for 30. Rare failures need cases that start at the moment the failure happens, so they occur often enough to measure.

Searching many alternatives, peeking repeatedly, and picking favorable cases or judges inflate apparent gains; account for them or confirm on fresh cases.

Totals without their units (an analytics export, a published table) support rates and means with their stated n and no spread between units; analyze them as totals and say that variation between units is unknown.

## Contributors, judges, and raters

Give each contributor its mission, the originals and access it needs, its authority, and its output location, and nothing that reveals contributions its role does not need, the expected result, or your hypothesis, including your framing of what matters. Roles need different inputs: a criteria author gets the request, domain sources, and what the alternatives are, without candidate results, earlier scores, or the expected winner; a challenger gets the criteria it challenges and the originals; a setup reviewer gets the alternative's own documentation; a judge gets the output without its producer, earlier scores, or the expected winner. Keep blind drafts as written. A challenge made after seeing the alternatives may raise a risk only an alternative reveals: it adds that concern, or sends an existing criterion back for reconsideration against its original grounds, and never removes or reweights criteria itself; each addition is examined too, since enough added criteria shift the effective weighting.

Model families fail differently. For a decision others will rely on, draw contributors from more than one family where the budget allows, separately for designing the evaluation, executing, and judging: diversity in one role does not supply it in another, and several contributors from one family share its blind spots. Another family is another chance to catch an error, not validation, since families can share an incomplete brief or a mistaken premise. Before claiming a contributor is fresh or blind, inspect what the host actually passes it (inherited instructions, mounted files, conversation state); isolation that relies on a participant ignoring what it can see is not isolation.

A judge is an instrument. Qualify it against known-good and known-bad cases, strip labels that reveal the alternative (including disposition vocabulary a framing introduced), prefer deterministic checks on resulting state, and counter self-preference with a judge from another model family. Score every compared alternative with the same judge or panel; a different judge per alternative confounds quality with strictness. Where independent reference outcomes exist, qualify a judge beyond the easy pair, on a polished failure and a sound unconventional success, with reference verdicts grounded in something other than the rubric author's opinion. For a question of taste, qualification shows that the judge assesses the intended attribute without irrelevant distortion, not that every rater shares one taste. Judges favor longer answers and the first position; swapping order addresses position only. Agreement between judges measures agreement, not correctness; compare concrete behavior against explicit criteria where tiers disagree. Any instrument observes from where the behavior it measures cannot move it; one that depends on what the observed party controls misses whatever that party does differently.

People who rate or choose are instruments too: record who they are and what they were shown, keep them blind to which alternative is the favorite, and fix the scale before they use it. Ordinal levels are ordered, not equally spaced, so report counts per level; a mean of ratings invents a distance. Where absolute ratings drift between raters, ask for choices between alternatives or rankings, balanced for order, and report how many raters chose each way, ties and no-choice included.

A handoff or summary supplies information, not understanding. Reconstruct a consequential judgment you rely on from the relevant originals, and trace every decisive claim to a retained record. Summaries guide navigation and do not become authority.

## Attribution and limits

Keep apart infrastructure failures, invalid cases, instrument errors, candidate behavior, and causal explanation. Assign a cause only when evidence separates it from plausible alternatives, typically by intervention: change one thing, keep the rest, repeat. Removing an instruction after it shaped a plan tests response to a late edit, not the instruction's original influence; branch before the first relevant exposure instead, and include unchanged reruns as a baseline and a meaning-preserving rewording as a control for incidental wording sensitivity. When a premise or measurement fails, revisit every judgment and recommendation that depended on it.

Evidence keeps what produced it. Observing an agent execute instructions is direct evidence about that agent; an agent standing in for a customer, a novice, or a reader is a simulation. Simulated behavior supports claims about the simulation and can find failure modes, sharpen questions, or screen alternatives; a claim about people or deployment needs grounds for that transfer, such as validation against observed behavior in a comparable setting, or it is stated as a claim about the simulation. Route each claim to the observation that can support it: a correct procedure to its authoritative source, task success to observed performance, and reader preference to the readers themselves.

Observational data (campaign analytics, logs, existing records) shows association unless assignment was random: state how each alternative came to be shown or used and what else differed (audience, timing, budget) before reading a difference as an effect.

Preserve differences in populations, operating conditions, tails, and interactions when collapsing them could change the action.

## Decisions without measurement

When nothing can be observed, set out each alternative's claims against the criteria, each cell holding the claim and its basis (a source, an expert, an assumption) rather than a score. Where criteria must be traded off, the weights belong to the person deciding: show any they gave and the arithmetic, and whether the leader changes under other weights. A matrix organizes a judgment and measures nothing; say in the report which cells are judgments. Words are evidence: keep a quotation with the value it explains, and let it count when the criteria fixed beforehand said it would.

## Stopping

Stop when the choice is resolved, no obtainable evidence can resolve it, the budget is reached, or the next observation cannot change what anyone would do. When the tools, material, and authority to observe are available and observation is what the decision needs, run it rather than proposing it.
