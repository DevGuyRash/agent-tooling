# ADR 0015: Replicate the source of variation

- Status: Accepted
- Date: 2026-08-16

## Decision

Place repeated trials at the smallest independent unit containing the uncertainty the comparison is meant to measure. Fresh agent, person, process, host, or system executions can measure variability in that unit. Replaying an unchanged source-faithful deterministic substep inside one execution is a consistency check, not another independent trial and not evidence about agent reliability.

Give every evaluation layer a distinct unresolved property. Executable mechanisms establish facts within their validated contract. Semantic reviewers judge properties those mechanisms do not decide, including material tradeoffs and unanticipated concerns. An executor-created review panel contributes task evidence only when it is part of the tested condition or observes a different real population or property; it does not strengthen a deterministic fact by duplicating the experiment's outer review.

The ordinary three-execution default for variable agent work applies to fresh condition exposures, not to every nested command. Additional repetition or reviewers require a plausible consequential source of variation or uncertainty. Preserve the larger design when it is itself the product or condition under test.

## Why

A held-out recovery-card comparison tested the current Split Testing candidate against unguided controls. Three treatment and three control agents all chose the same correct card. Treatment agents used three deterministic simulator replays per card and some added their own blind semantic review. Their mean input use was about 462,742 tokens versus 310,387 for controls, yet eight of nine fresh blind reviewers found the matched reports materially tied. One reviewer preferred the treatment's larger evidence packet; no reviewer identified a decision the extra repetitions had corrected.

The result did not show that replication or review is generally useless. It located the mistaken premise: the instructions made “three repetitions” salient without making the source of variation equally salient, so executors spent the budget below the variable agent boundary. They also duplicated the controller's review role inside the candidate artifact. More evidence-shaped activity therefore measured no new uncertainty.

The foundational correction is to align the evidence unit and measurement responsibility with the claim. This preserves repeated fresh generative trials where model variability is real, executable checks where outcomes are deterministic, and semantic review where judgment remains. It avoids a surface correction such as reducing every panel to one reviewer or forbidding repeated commands.

Current primary guidance supports that distinction without proving the repository result. [Anthropic's statistical evaluation guidance](https://www.anthropic.com/research/statistical-approach-to-model-evals) places resampling at nondeterministic model answers and clusters uncertainty at the unit of randomization. Its [agent-evaluation guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) separates code, model, and human graders by the outcome each can assess. The local six-run and nine-reviewer evidence establishes the correction here; the external material supplies the broader experimental-design basis and reopening horizon.

## Consequences

Experiment designs name or otherwise make recoverable the unit whose variation justifies repetition. Reports distinguish independent runs, clustered observations, and deterministic consistency checks. Review plans state what unresolved property each evaluator can observe, and cost or artifact volume does not substitute for that property.

Reopen this decision when a supposedly deterministic mechanism shows consequential nondeterminism, shared state, flakiness, platform sensitivity, or another uncertainty that repeated execution can measure; when an inner panel is a real part of a candidate system; or when downstream evidence shows a duplicated review layer improves criterion validity rather than only confidence or presentation.
