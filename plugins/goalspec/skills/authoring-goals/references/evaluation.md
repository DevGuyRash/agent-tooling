# Evaluation Guide

Evaluate GoalSpec on design clarity first and final product lift second. The skill succeeds when it helps vague intent converge on a better direction and then hands execution source-faithful probes.

## Compared Conditions

Run each case at least two ways:

- Raw/no-skill: give the worker only the original prompt or source.
- GoalSpec-assisted: have one agent use GoalSpec to produce an Option Map, decision capture, Probe Pack, or Probe Note as appropriate, then have a fresh worker use that output.

WHEN a condition receives extra source context not available to the others THEN you SHALL record the asymmetry before scoring. You SHALL NOT score document polish as planning quality. You SHALL treat premature durable docs as a regression in design-shaped or known-change cases.

## Cases

Use cases where left-shift should matter:

- Vague design prompt where the correct first output is an Option Map.
- Known bugfix where the correct output is a Probe Note with no durable doc.
- PRD with an ambiguous API or UX decision where alternatives and safe defaults matter.
- Post-convergence handoff where a Probe Pack should improve final product quality.
- File-restraint trap where `context/docs/` would be artifact overhead.

## Scoring

Score each condition from 0 to 3:

| Dimension | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| Design clarity | Confuses or narrows the problem prematurely | Names the obvious direction only | Shows useful alternatives | Makes tradeoffs clear and recommends a source-grounded direction |
| Convergence quality | Never reaches a usable direction | Reaches a vague direction | Reaches a usable direction with weak rationale | Captures chosen and rejected directions with rationale |
| Artifact restraint | Writes irrelevant docs | Over-produces with some useful content | Mostly right-sized | Uses chat, docs, and handoff only at the right phase |
| Probe quality | No concrete probes | Probes adjacent claims | Probes main outcome | Probes main outcome plus adversarial and compatibility risks |
| Default handling | Blocks on safe choices or guesses true blockers | Mixes blockers and defaults | Usually separates them | Clearly separates true blockers from safe executor-owned defaults |
| Product outcome | Misses source outcome | Partially works | Works with minor quality gaps | Satisfies source outcome and avoids known traps |

## Regression Classification

WHEN GoalSpec-assisted output is worse than raw/no-skill THEN you SHALL classify the regression as one of:

- Premature docs: durable artifacts appeared before convergence or for a known change.
- Weak Option Map: directions were fake, method-level, or lacked recommendation.
- Missing probes: handoff lacked acceptance probes or final source-review checks.
- False blocker: a safe default was treated as a stop condition.
- HOW leakage: implementation moves became acceptance.
- Handoff drift: the executor followed the output but produced a weaker product.

The gauntlet passes when GoalSpec-assisted output improves design clarity or convergence for vague cases and equals or beats raw/no-skill on final product quality once execution begins.
