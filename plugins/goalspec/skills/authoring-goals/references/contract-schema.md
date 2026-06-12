# Goal Contract Schema

Use this schema for `.goals/current.md`.

```markdown
# Goal Contract: G-000 Title

## Status

- State: active | candidate | blocked | completed | abandoned
- Created: YYYY-MM-DD
- Source: user prompt | file | issue | scan | follow-up
- Contract hash: set by validate_goal.py --write-hash
- Blocks: [ids] | none      (informational mirror — the campaign manifest is dependency truth)
- Blocked by: [ids] | none

## Objective

[One sentence describing the desired terminal state.]

## Intent

[Why this matters. Used for tradeoffs.]

## Context

[Source anchors, prior attempts, assumptions. Line-level anchors suit a goal
that executes now; an unlocked tail goal prefers section/outcome anchors —
files will have changed by the time it runs. The executor re-verifies anchors
during its discovery pass before acting.]

## Available Capabilities

[Discovered skills, plugins, MCP servers, hooks, subagents, and project commands relevant to this goal.]

## Completeness Dimensions

This goal must cover:
- [Functional behavior]
- [Verification]
- [Regression safety]
- [Docs / UX / security / performance / data / rollout if relevant]

## Terminal State

This goal is complete when:
- [Checkable proposition — enumerate the source's acceptance criteria]
- [Checkable proposition]
- [Checkable proposition]

## Tasks

[The definition of done as a declarative outcome tree. Every item is a state
to make true, never a step; nest freely (2-space indent per level — tasks,
subtasks, sub-subtasks). Order implies nothing; dependency lives in
Blocked by/Blocks and the campaign graph. Boxes stay unticked here: the frozen
contract is immutable, and the live cursor is projected into .goals/focus.md
and moved with `focus.py done <id>` (positional dotted ids: 1, 1.2, 1.2.3).
Marks are progress bookkeeping; the Verifier remains the only oracle.]

- [ ] [Outcome]
  - [ ] [Sub-outcome]
    - [ ] [Sub-sub-outcome]

## Verifier

Completion must be verified by:
- [Command / metric / checklist / artifact / human gate]
- [Expected result]
- Pinned: [path] sha256 [64-hex]   (optional: freezes a companion artifact the
  verifier depends on, e.g. a shared verify script; sha256sum of its bytes at
  lock time. run_verifiers.py checks pins before executing and audit_goal.py
  re-checks them — a mutated companion fails loudly.)

Fenced ```bash blocks run each non-comment line as its own command; a heredoc
(`python3 - <<'PY' … PY`) spans as one command, body verbatim.

## Scope

In scope:
- [Allowed files/modules/behaviors]

Out of scope:
- [Forbidden files/modules/behaviors]

## Budget

- Max implementation iterations: N
- Max changed files: N
- Max new dependencies: N
- Max exploration files/directories: N
- Stop when the budget is exhausted even if incomplete.

## Give-Up Conditions

Stop and report blocked/incomplete if:
- [Missing access]
- [Verifier unavailable]
- [Product decision required]
- [Out-of-scope change required]
- [Target infeasible within budget]

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
```

## Source of truth rule

`.goals/current.md` is the source of truth. A rendered `/goal` objective is a projection. The auditor checks against `current.md`, not against a shortened prompt.

## Register

Write contract sections in natural declarative prose: terminal outcomes, constraints, and what proves them. An EARS-style WHEN/THEN/SHALL clause belongs in a contract only for its few hard stop/scope gates; a contract that reads as a procedure script binds the executor to a method instead of an outcome.
