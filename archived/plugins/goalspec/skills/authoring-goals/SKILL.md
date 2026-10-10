---
name: authoring-goals
description: >-
  Shape vague intent into clearer product decisions before execution. Use when
  the task involves: (1) exploring ambiguous product, design, or implementation
  directions with an Option Map, (2) converging on a chosen direction before
  writing durable context/docs artifacts, (3) generating Probe Packs with
  acceptance examples, adversarial checks, non-goals, and final source review
  prompts before handoff, or (4) reviewing planning output for premature docs,
  false blockers, HOW leakage, weak probes, and lost source nuance. Do not use
  for direct execution unless a probe note or handoff is needed first.
---

# Authoring Goals

Use this decision-funnel skill to help vague intent become a clearer product direction before execution, then turn the chosen direction into acceptance probes and only the durable docs worth preserving.

Improve product work on the left side of the funnel: make options explicit, name tradeoffs, preserve source nuance, and start execution with probes that make weak outputs harder to accept.

## Decision Funnel

1. Inspect the user request, named files, existing docs, and repo context before asking questions.
2. Classify the request shape:
   - **Design-shaped:** the user does not yet know the product direction.
   - **Chosen direction:** the outcome is selected, but decisions should be preserved.
   - **Ready to build:** the direction is concrete enough for execution.
   - **Known change:** the user already named the specific change or bugfix.
3. Use the lightest output that changes the next decision:
   - Design-shaped work gets an **Option Map** in chat.
   - Chosen direction work may update `context/docs/` after convergence.
   - Ready-to-build work gets a **Probe Pack** before handoff.
   - Known-change work gets a concise **Probe Note**, not a durable doc.
4. Distinguish true blockers from safe defaults.
5. Keep implementation design freedom with the executor unless the user or source explicitly constrains the method.

WHEN a `.local*/context/` directory exists in the target repo THEN you SHALL use that context directory. ELSE IF a repo-root `context/` directory exists THEN you SHALL use it. ELSE you SHALL create repo-root `context/`. Durable planning artifacts live under `context/docs/` inside that context directory, and only after the direction is chosen or accepted.

WHEN the user is still choosing direction THEN you SHALL stay in chat and produce an Option Map instead of writing durable docs. WHEN execution handoff is requested or implied THEN you SHALL include acceptance probes and a final source-review checklist. WHEN a decision changes product direction, irreversible architecture, acceptance semantics, or stakeholder commitment THEN you SHALL raise it before handoff. WHEN a decision is reversible, locally testable, or executor-owned THEN you SHALL offer a safe default with a note instead of blocking. You SHALL state acceptance as outcomes, naming a method only when the user or source makes it part of the outcome.

## Reference Index

Read the reference your situation needs:

| Situation | Read |
| --- | --- |
| Need to choose the right phase or output | `<skills-file-root>/references/decision-funnel.md` |
| Vague user intent or product discovery | `<skills-file-root>/references/option-map.md` |
| Ready-to-build handoff or known-change request | `<skills-file-root>/references/probe-pack.md` |
| Need wording examples | `<skills-file-root>/references/examples.md` |
| Reviewing for failure modes | `<skills-file-root>/references/anti-patterns.md` |
| Designing a behavioral evaluation | `<skills-file-root>/references/evaluation.md` |

## Outputs

**Option Map:** plausible directions, what each optimizes for, tradeoffs, risks, weak or rejected options, and a recommended next direction. Use it before durable docs.

**Decision Capture:** after convergence, update an existing canonical doc or write one adaptive decision brief under `context/docs/` only when later turns or agents will need it. Preserve chosen direction, rejected alternatives, rationale, source nuance, unresolved risks, and the Probe Pack needed for execution.

**Probe Pack:** acceptance probes, adversarial examples, compatibility checks, non-goals, safe defaults, true blockers, executor-owned design space, and a final source-review checklist. A planned execution handoff is not ready without probes.

**Probe Note:** the small-task version of a Probe Pack. For known-change requests, keep it concise and usually in chat or handoff text; do not write `context/docs/` unless the user asked for durable docs or cross-session handoff requires it.
