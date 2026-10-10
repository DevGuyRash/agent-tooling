# Probe Pack

A Probe Pack is the execution-pressure output. It makes weak products harder to accept without dictating implementation.

## Ingredients

- Source anchors: wording or source facts the probes protect.
- Acceptance probes: concrete inputs, scenarios, examples, parser checks, user journeys, or review checks.
- Adversarial probes: cases that catch plausible bad implementations.
- Compatibility probes: existing behavior, callers, formats, or invariants that must keep working.
- Non-goals: explicit exclusions and tempting overreach.
- True blockers: owner decisions to settle before handoff.
- Safe defaults: executor-owned choices that can proceed with a note.
- Executor-owned design space: what the executor is free to decide.
- Final source-review checklist: what to compare against before returning.

## Probe Note

For known-change work, use a short Probe Note instead of durable docs:

```md
## Probe Note

Intent delta:
- <what is easy to miss or overdo>

Acceptance probes:
- <source-faithful probe>
- <compatibility probe>

Non-goals:
- <explicit exclusion>

Executor freedom:
- Any implementation is acceptable if it passes the probes and preserves constraints.

Final review:
- Re-read the source and confirm each explicit constraint is still satisfied.
```

## Ready-To-Build Handoff

A planned execution handoff is ready only when it includes probes. Durable docs without probes are not enough.

WHEN a probe checks only "the command exits" but not the source-defined outcome THEN you SHALL strengthen the probe. WHEN a probe dictates implementation method without source support THEN you SHALL rewrite it as an observable outcome. WHEN a design decision is executor-owned THEN you SHALL name the freedom and the probes that bound it.

## Final Source-Review Checklist

Before execution returns, the worker should be able to answer:

- Which source acceptance items are satisfied?
- Which exclusions stayed out of scope?
- Which compatibility behaviors still work?
- Which design choices were made that the source did not specify?
- What is one plausible way the output could still be wrong?
