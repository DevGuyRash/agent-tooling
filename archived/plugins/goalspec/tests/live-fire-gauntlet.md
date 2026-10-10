# GoalSpec V4 Decision-Funnel Gauntlet

This gauntlet measures whether GoalSpec improves product direction before execution and final quality once execution begins. It does not treat polished documents as success.

## Compared Conditions

Run each case two ways:

- Raw/no-skill: give the worker only the original prompt or source.
- GoalSpec-assisted: have one agent use GoalSpec to produce the phase-appropriate output, then have a fresh worker use that output when execution is relevant.

WHEN a condition receives extra source context not available to the others THEN you SHALL record the asymmetry before scoring. You SHALL NOT score artifact polish as planning quality. You SHALL count premature `context/docs/` creation as a regression for design-shaped and known-change cases.

## Cases

### Case 1: Vague Design Prompt

Use an intentionally broad product request:

```text
Make imports less painful for customers.
```

Grade whether GoalSpec produces an Option Map with distinct product directions, tradeoffs, and a recommendation instead of writing durable docs or jumping into implementation.

### Case 2: Known Bugfix

Use a concrete change request:

```text
The contact CSV import basically works, but quoted mailing addresses with commas split wrong. Don't replace the importer or introduce pandas.
```

Grade whether GoalSpec produces a Probe Note only: intent delta, acceptance probes, non-goals, executor freedom, and final review. Durable docs are a failure unless explicitly requested.

### Case 3: PRD With Design Choice

Use a PRD with acceptance criteria, exclusions, and an ambiguous API or UX decision. Grade whether GoalSpec separates true blockers from safe defaults and recommends a direction when the executor can proceed safely.

### Case 4: Post-Convergence Handoff

Use a prompt where the user has selected a direction. Grade whether GoalSpec captures only the durable decision/rationale needed under `context/docs/` and includes a Probe Pack before execution.

### Case 5: Execution Comparison

Have planned and raw executors implement the same source after GoalSpec produces probes. Grade whether planned execution equals or beats raw execution on final product quality, especially compatibility and adversarial cases.

## Scoring

Score each condition from 0 to 3 for each dimension:

| Dimension | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| Design clarity | Confuses or prematurely narrows the problem | Names only the obvious direction | Shows useful alternatives | Makes tradeoffs clear and recommends a source-grounded direction |
| Convergence quality | No usable direction | Vague direction | Usable direction with weak rationale | Chosen and rejected directions are clear with rationale |
| Artifact restraint | Irrelevant docs | Over-produced docs | Mostly right-sized | Chat/docs/handoff appear only at the right phase |
| Probe quality | No concrete probes | Probes adjacent claims | Probes main outcome | Probes main outcome plus adversarial and compatibility risks |
| Default handling | Blocks on safe choices or guesses true blockers | Mixes blockers and defaults | Usually separates them | Clearly separates true blockers from safe executor-owned defaults |
| Product outcome | Misses the source outcome | Partially works | Works with minor quality gaps | Satisfies the source and avoids known traps |

## Regression Classification

WHEN GoalSpec-assisted output is worse than raw/no-skill THEN you SHALL classify the regression as one of:

- Premature docs: durable artifacts appeared before convergence or for a known change.
- Weak Option Map: directions were fake, method-level, or lacked recommendation.
- Missing probes: handoff lacked acceptance probes or final source-review checks.
- False blocker: a safe default was treated as a stop condition.
- HOW leakage: implementation moves became acceptance.
- Handoff drift: the executor followed the output but produced a weaker product.

## Report Shape

Write the gauntlet report as:

```md
# GoalSpec V4 Decision-Funnel Gauntlet Report

## Summary
- Case count:
- Design clarity wins:
- Execution wins:
- Ties:
- Losses:
- Product regressions:
- Decision:

## Case Results
| Case | Condition | Design clarity | Convergence quality | Artifact restraint | Probe quality | Default handling | Product outcome | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |

## Regressions
- <case>: <classification> - <short reason>

## Evidence
- <links/paths to prompts, Option Maps, Probe Packs, docs, final outputs, commands, reviewer notes, or parser checks>
```

The gauntlet passes when GoalSpec improves design clarity or convergence for vague cases and equals or beats raw/no-skill on final product quality once execution begins.
