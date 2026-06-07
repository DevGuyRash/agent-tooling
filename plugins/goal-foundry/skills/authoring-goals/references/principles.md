# Goal Foundry Principles

## Doctrine

Open-world discovery. Closed-world execution.

- Discovery is expansive: inspect files, plans, logs, tests, docs, existing goals, capabilities, and project state.
- Execution is bounded: execute one frozen goal contract, then stop and report.

## The six launchability fields

1. Terminal state: the goal can be phrased as a checkable proposition.
2. Verifier: something other than the executor's confidence can check the proposition.
3. Budget: the run has a ceiling even when success is unreachable.
4. Scope edges: the agent knows what not to touch.
5. Give-up conditions: the agent knows when to stop unsuccessfully.
6. Completeness dimensions: satisfying every clause would not omit something the user reasonably expected.

## Failure modes

- No terminal state -> busywork.
- No context -> rediscovery and guesswork.
- No scope -> sprawl.
- No verifier -> vibes.
- No budget or give-up -> forever loop.
- No completeness -> correct proxy, wrong result.
- Mutable contract -> target drift.
- No capability inventory -> missed tools, missed evidence, or invented tools.

## Contract grammar

A good contract says:

- What must be true.
- What must not change.
- What proves it.
- What limits the run.
- What stops the run unsuccessfully.
- What evidence the final report must contain.

It does not prescribe a brittle implementation route.
