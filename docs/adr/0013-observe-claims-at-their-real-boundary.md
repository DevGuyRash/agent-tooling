# ADR 0013: Observe claims at their real boundary

- Status: Accepted
- Date: 2026-08-16

## Decision

Evaluation evidence must observe the property a conclusion names at the layer where that property exists. Artifact inspection can establish artifact facts. A semantic reviewer can judge supplied evidence and predict likely effects. Neither becomes evidence that an intended person or system can use, understand, play, operate, perceive, or benefit from the alternative unless that role is actually exercised or faithfully simulated.

Derived evidence must preserve the same boundary. A checker, simulator, oracle, reference answer, rubric, or metric supports only the source rules and population it faithfully models. Computation can be exhaustive within a partial model without being evidence for the complete system. Reviewer agreement cannot widen that scope.

When direct access to the claimed boundary is unavailable, retain the narrower supported result and name the unverified outcome. Additional reviewers are useful only when they observe a decision-relevant uncertainty; they do not repair missing execution evidence by agreeing about it.

## Why

A held-out paper-game comparison supplied the Split Testing candidate with four complete alternatives and a maker request centered on mixed-group use and one-reading understandability. The treatment created multiple fresh semantic reviewers, a detailed rubric, and deterministic analyses, but did not observe a group learning or playing any game. Its reviewers unanimously selected one alternative while later source-reconciled reviewers remained split between that alternative and a simpler one. The consensus measured interpretation of rules under a shared measurement model, not the claimed mixed-group experience.

Two treatment reports also demonstrated false assurance at the derived-evidence boundary. One source hash was incorrect. Another report described a two-player checker as exhaustive even though the checker removed every played East bid and never returned East's winning tied slip, contradicting the immutable rule it purported to model. Higher-level reviewers still often preferred the report because its quantitative evidence looked stronger. The correct repair is to align observation and model with the claimed property, not to add another score, reviewer, or report section.

Current external evidence supports the same distinction without deciding the local case. [Anthropic's agent-evaluation guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) places agents in real or sandboxed environments and grades outcomes with complementary mechanical, model, and human evidence. [Criterion Validity of LLM-as-Judge for Business Outcomes](https://arxiv.org/abs/2604.00022) reports that coherent rubric dimensions differed materially in their relationship to the downstream outcome and that an equal-weight composite diluted the strongest signals. [PReMISE](https://arxiv.org/abs/2605.30803) reports that high inter-rater agreement did not imply low rubric exploitability. These sources are reopening signals, not substitutes for target-specific evidence.

## Consequences

Experiment designs bind each conclusion to the actual execution population and observation surface. Reviewers interpret retained outcomes; they do not silently replace the population under test. Checkers and simulations are validated against the source contract and described at their honest scope. Reports preserve the difference between observed behavior, artifact judgment, and predicted behavior whenever collapsing it could change a decision.

Reopen this decision when a validated measurement method establishes that a proxy reliably tracks the named outcome for the relevant population, or when the user's decision explicitly concerns the proxy rather than the downstream behavior.
