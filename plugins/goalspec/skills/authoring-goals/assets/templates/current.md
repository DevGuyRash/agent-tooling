# Goal Contract: G-000 Replace With Title

## Status

- State: active
- Created: YYYY-MM-DD
- Source: user prompt
- Contract hash: pending
- Blocks: [child ids this goal unblocks, or none — informational mirror; the campaign manifest stays the dependency truth]
- Blocked by: [ids or none]

## Provenance

- Artifact: .goals/provenance/G-000.md
- Request hash: pending
- Reference only; not execution scope. The verbatim original request lives in the artifact and must not be executed or re-derived. Execute only this frozen contract.

## Objective

[One sentence describing the desired terminal state.]

## Intent

[Why this matters, anchored in the user's own words — quote the Intent Inventory item this goal serves; tradeoffs follow from it.]

## Context

[Source anchors, prior attempts, assumptions. Line-level anchors are right for
a goal that executes now; for an unlocked tail goal prefer section/outcome
anchors — files will have changed by the time it runs. Either way the executor
re-verifies anchors during its discovery pass before acting.]

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
- [Checkable proposition — enumerate the source's acceptance criteria]
- [Checkable proposition]
- [Checkable proposition]

## Tasks

[The definition of done decomposed into a declarative outcome tree: every item
is a state to make true, never a step; nest subtasks and sub-subtasks freely
(2-space indent per level). Order implies nothing — dependency lives in
Blocked by/Blocks and the campaign graph. Boxes stay unticked in this frozen
contract; the live cursor is projected into .goals/focus.md and moved with
`focus.py done <id>`. Marks are bookkeeping; the Verifier is the oracle.]

- [ ] [Outcome]
  - [ ] [Sub-outcome]
    - [ ] [Sub-sub-outcome]
- [ ] [Outcome]

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
