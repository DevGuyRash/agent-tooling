# Decision Funnel

Start left of execution: first determine whether the user is still discovering the direction, has selected one, is ready for execution, or already gave a concrete change.

## Request Shapes

**Design-shaped** requests are ambiguous on purpose:

- "Make onboarding better."
- "I don't know what the product should do yet."
- "Think through options for recipe search."

Answer in chat with an Option Map.

**Chosen direction** requests have a direction but need preservation:

- "Let's use the lightweight self-serve onboarding path."
- "Keep the existing API, but add automation-ready stale-flag reporting."

Capture decisions under `context/docs/` only if durable text will prevent drift across turns, agents, stakeholders, or phases.

**Ready-to-build** requests have enough direction for implementation:

- "Implement the selected Recipe Search MVP slice."
- "Build the JSON report using the chosen schema."

Generate a Probe Pack before handoff.

**Known-change** requests name the specific change:

- "Fix quoted CSV fields with commas, don't rewrite the importer."

Generate a Probe Note only. Creating durable docs for a small known change is usually artifact overhead.

## Phase Rules

WHEN the direction is not chosen THEN you SHALL produce an Option Map in chat before any durable docs. WHEN the user accepts, chooses, or clearly implies a direction THEN you MAY capture durable decisions under `context/docs/` if later work needs it. WHEN execution handoff is requested or implied THEN you SHALL include a Probe Pack or Probe Note. WHEN a task is a known change THEN you SHALL skip durable docs unless the user explicitly asks for them or the handoff spans sessions/stakeholders.

## Blockers And Defaults

Block only on these:

True blockers:

- Change product direction.
- Change acceptance semantics.
- Commit stakeholders to a policy or workflow.
- Choose irreversible architecture or migration direction.
- Create risk that cannot be repaired locally.

Safe defaults:

- Reversible implementation choices.
- Local schema choices that can be documented and adjusted.
- Testable API design options where compatibility probes define success.
- Output filenames when the user did not specify one and the location is obvious.

Give a recommended default plus a note wherever the executor can proceed without foreclosing the user's real decision.
