# Task Evals

Task evaluation asks whether the skill changes real agent behavior on
representative work.

## Canonical Task Selection

You SHALL choose 1–3 canonical tasks that the skill is meant to improve.
You SHALL prefer tasks that expose the highest-value promise of the skill.
WHEN feasible THEN you SHALL compare the skill-active run to a no-skill or
prior-version baseline.
WHEN a baseline is not feasible THEN you SHALL say so and you SHALL rely on
direct observation plus output comparison.

## Evaluation Axes

Assess each task on:

1. Outcome — Was the task completed correctly?
2. Process — Did the agent follow the intended workflow or use the intended resources?
3. Quality — Did the output match the conventions the skill claims to help with?
4. Efficiency — Did the skill reduce guessing, thrashing, or unnecessary work?

## Evidence Sources

Allowed evidence includes:

- direct observation
- command traces
- output comparison
- human-in-the-loop rubric

You SHALL keep the evidence set small and decision-relevant.
You SHALL NOT build a large benchmark suite unless the user explicitly asks for
it.

## Repair Strategy

WHEN one failure mode dominates multiple tasks THEN you SHALL fix that failure
before chasing smaller issues.
WHEN the skill improves process but not outcome THEN you SHALL question whether
the workflow is solving the right problem.
WHEN the skill improves outcome but wastes large amounts of context or effort
THEN you SHALL hand off the follow-up to context fit.

## Deliverables

You SHALL name the canonical tasks you evaluated.
You SHALL note the strongest evidence for or against improvement.
You SHALL propose the smallest workflow repair that is likely to change the
next run.
You SHALL carry a verification step forward for any changed task path.
