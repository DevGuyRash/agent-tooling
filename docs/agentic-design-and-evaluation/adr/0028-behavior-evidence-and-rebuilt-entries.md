# ADR 0028: Decide instructions by observed behavior, and rebuild the entries around that evidence

- Status: Accepted.
- Scope: Agentic Design & Evaluation (all five entries, the foundation, and the authoring guidance), the repository's `evals/` suite, and the user's global instruction layer that the plugin maintains.

## Context

Agents on every host were failing to converge: stopping early, grinding through re-verification and replanning for weeks, building self-continuing heartbeats, leaving worktrees and branches behind, and treating agent-written plans as the user's requests. The plugin that was meant to prevent this never reached execution in ordinary work, its Self-Healing entry never ran, and each observed failure had been answered by adding text. Review by reading kept growing the text without a way to tell whether any of it changed behavior.

## Decision

Behavior evidence decides what instructions say. The Split Testing entry carries a trial runtime (`scripts/trial.py`) that runs each alternative on each scenario repeatedly in confined, isolated homes and working directories, with qualified deterministic checks, an optional blind judge, retained native records, interval reporting, re-scoring of stored runs, and two-stage trials that hand what one agent wrote to the agent that follows it. The repository keeps its scenarios in `evals/`, and a scenario that justifies a change stays as that change's regression check.

The entries are rebuilt on that basis:

- Split Testing leads with the decision, fixes its properties (criteria before results, blind isolated contributors, repeated observation, qualified instruments, real conditions, traceable conclusions), and makes the standalone HTML report optional; four method references merge into one.
- Self-Healing records observations in the order the user designed (what happened and was expected, how the agent read what guided it, what it did, then hypotheses), runs healing passes on request or through a harness-agnostic launcher, reads evidence through a cross-host digest, changes a reusable source only after N consecutive reproductions, and ends each problem and its consequences as healed, deliberately unchanged, or open with an owner.
- Prompt and Context Design and Skill Auditor shrink to their entries plus one reference each; Skill Auditor gives a verdict per unit with evidence and carries a field guide of defect shapes, including those the trials demonstrated.
- The authoring guidance shrinks from a 1,093-word charter to two invariants on what an author delivers: a correction lives where its cause was, without restating the removed behavior and without changing lines the principal did not ask about; and standing instructions carry no snapshots of the moment. In trials, no authoring text changed whether the resulting instructions worked for the agents that followed them; this text kept every safety line, shrank repairs, avoided restated duties in new skills, and cost the least.
- The foundation and the authoring guidance change by revising the statement a new finding bears on, and a change to what they direct rests on a trial against the replaced text and against no text. This replaces the earlier rule that kept them verbatim.
- The user's global instruction layer is replaced by the smallest text that beat both the previous layer and no layer on the scenarios where agents failed, with the State Files section removed pending the user's own storage redesign.

## Consequences

Claims about instructions now name their model, run count, and scenarios, and an instruction with a measured cost and no detected benefit is a candidate for removal. On single-repository healing passes, the rebuilt Self-Healing entry tied a capable model with no skill and beat the entry it replaced; its distinctive value lies in its cross-session tools and the user's own policies, and its text is a candidate for compression. The trials so far ran on one model family, with an Astra confirmation of the global layer; results on other families remain to be observed. Removed references and entry text remain in Git history.
