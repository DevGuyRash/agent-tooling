---
name: systematic-debugging
description: "Use when a bug, failure, crash, hang, flaky test, unexpected output, or regression has an unknown cause: reproduction, falsifiable hypotheses, discriminating probes, and a fix of the cause. Excludes known-cause fixes."
---

# Systematic Debugging

This skill builds on the [Software Foundation](../software-foundation/SKILL.md) skill.

An unexplained failure gets a supported causal account before it gets a fix, and the fix is the smallest durable correction of that cause. Each probe changes what you believe; speculative fixes do not accumulate.

When users, data, or stability are being harmed now, contain first (roll back, isolate, disable a path) within your authority, keep the evidence, and keep containment separate from diagnosis and repair.

- Capture the exact symptom (error, stack, failing assertion, observable effect), without exposing credentials or unrelated private data, with its environment, input, frequency, and a nearby case that works; an intermittent failure keeps its signature and occurrence conditions.
- Reproduce with the smallest faithful case when feasible, and check recent code, dependency, configuration, traffic, and environment changes that intersect the symptom.
- Compare the failing and working paths and find where their states first diverge, instrumenting only what distinguishes plausible causes.
- State each hypothesis so it can be falsified, predict what a probe will show before running it, and change one decision-relevant variable at a time when attribution matters; a negative result that removes a plausible cause is progress. Revisit the model when probes stop discriminating; no fixed attempt count proves the architecture wrong.
- A clean run proves a repair only when the probe deterministically discriminates; otherwise it shows only what its exposure (runs, schedules, seeds, load) could have caught. After the fix, the original reproducer runs clean.
- Fix the supported cause rather than the symptom; when a retry, timeout, or fallback is the right answer to an external condition, name the condition it handles. Temporary diagnostics come out unless you mean to keep them.

Read [difficult failures](references/difficult-failures.md) for intermittent, concurrent, distributed, environment-specific, or cross-component failures.
