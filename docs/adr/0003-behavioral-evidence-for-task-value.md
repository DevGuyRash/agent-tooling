# ADR 0003: Require comparative behavior for task-value claims

- Status: Accepted
- Date: 2026-08-15

## Decision

A claim that a skill, plugin, prompt, model, workflow, or other intervention improves work requires observed behavior against a decision-relevant comparator. Document inspection can establish a deterministic defect or explain a trajectory, but it cannot by itself establish task value.

The design follows the actual claim. It may compare a current baseline, no intervention, a previous version, several alternatives, or a compound deployed system. Evidence remains attributed to the independently assigned execution unit, case, model, host, and round rather than flattened into an artifact or vote count.

Before consequential execution, the controller presents one recommended design and its material defaults and assumptions for user acceptance or revision. This is a decision agreement, not a fixed questionnaire. When stochastic agent behavior is plausible and no better basis or user choice sets the initial budget, the repository default is three fresh matched repetitions per key contrast. Every attempt remains evidence; this is not best-of-three selection.

Stopping and replacement rules are fixed before outputs are inspected. When a formal conclusion is updated while new observations arrive, its analysis must remain valid under that observation and stopping scheme; repeatedly peeking at an ordinary fixed-sample result until it looks favorable is not confirmatory evidence.

## Why

The frozen Split Testing candidate produced heterogeneous results: it improved an open-ended game decision but made a deterministic code decision worse by narrowing the user's contract and missing a valid counterexample. Static quality review predicted neither effect. After the instruction was revised, three fresh treatment and three control executions all found a new Unicode boundary, while six blind judgments preferred the treatment's evidence quality.

The result also showed why a vote is not truth. One reviewer falsely claimed retained evidence files were absent; custody hashes showed they existed. A valid counterexample or eligibility failure can decide a required property even when more outputs, reviewers, or aggregate scores point elsewhere.

A later held-out game-design decision tested the general comparison system outside code, skills, and plugin audits. Three fresh assisted executions and three matched unassisted executions analyzed four storm-director alternatives; nine counterbalanced blind reviews preferred the assisted artifact in every presentation. Condition-blind fact-checkers then recomputed the decisive raw-data premises. They preserved the comparative direction while correcting material claims in both conditions, including subgroup regressions, an unsupported fallback branch, and an invalid paired-interval construction. The trial therefore supports behavioral value on this decision, but the support comes from the verified differences—not the 9–0 count—and remains bounded to the tested model, instrument, and simulated population.

Current [Agent Skills evaluation guidance](https://agentskills.io/skill-creation/evaluating-skills) also recommends realistic tasks, fresh contexts, with/without baselines, raw-output inspection, and trace-driven iteration.

[PACE](https://arxiv.org/abs/2606.08106v1) provides recent fixed-version evidence for the acceptance risk: in its tested self-modifying-agent settings, greedy reuse of noisy held-out improvements accepted many false and harmful changes, while an anytime-valid paired gate controlled the stated decision error. That method is an example rather than a repository mandate; the durable decision is that the acceptor and stopping rule need evidence at the strength claimed.

## Consequences

Choose task breadth, independent repetition, and review depth from the consequence, variability, and smallest decision-relevant effect. The three-repetition default is only a modest starting budget, not a universal minimum, reliability claim, or power calculation. Narrow metadata questions need behavior only when their conclusion depends on it; deterministic failures can decide a release without ceremonial trials.

Report gains, regressions, shared failures, costs, and uncertainty separately. Reopen evidence when the task population, condition, host, model, harness, or consequential upstream contract changes.
