# Goal Contract: G-000 Replace With Title

## Status

- State: active
- Created: YYYY-MM-DD
- Source: user prompt
- Contract hash: pending

## Objective

[One sentence describing the desired terminal state.]

## Intent

[Why this matters and how to make tradeoffs.]

## Context

[Relevant files, logs, docs, tickets, previous attempts, assumptions.]

## Available Capabilities

- Skills: [discovered relevant skills]
- Plugins: [discovered relevant plugins]
- MCP servers: [discovered relevant MCP servers]
- Hooks: [relevant active hooks]
- Subagents/custom agents: [discovered relevant agents]
- Project commands: [test/build/lint commands]

## Completeness Dimensions

This goal must cover:
- Functional behavior:
- Verification:
- Regression safety:
- Other relevant dimensions:

## Terminal State

This goal is complete when:
- [Checkable proposition]
- [Checkable proposition]
- [Checkable proposition]

## Verifier

Completion must be verified by:
- [Command / metric / checklist / artifact / human gate]
- [Expected result]

## Scope

In scope:
- [Allowed files/modules/behaviors]

Out of scope:
- [Forbidden files/modules/behaviors]

## Budget

- Max implementation iterations: 3
- Max changed files: 6
- Max new dependencies: 0
- Max exploration files/directories: 30
- Stop when the budget is exhausted even if incomplete.

## Give-Up Conditions

Stop and report blocked/incomplete if:
- Required access or credentials are unavailable.
- The verifier cannot run.
- A product or architecture decision is required.
- Satisfying the goal requires out-of-scope changes.
- The target proves infeasible within budget.

## Priority Order

1. Correctness
2. Minimal scope
3. Verification
4. Simplicity

## Follow-Up Policy

Discovered adjacent work must be recorded as candidate goals, not performed, unless required for the terminal state.

## Evidence Required

Final report must include:
- Files changed
- Commands run
- Raw pass/fail results or artifact paths
- Budget used
- Remaining risks
- Follow-up candidates
