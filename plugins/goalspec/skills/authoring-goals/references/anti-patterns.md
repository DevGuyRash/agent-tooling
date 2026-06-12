# Goal Anti-Patterns

Flag or rewrite these before launching.

## Activity verbs without a fixed bar

- improve
- clean up
- polish
- modernize
- optimize
- harden
- stabilize
- productionize
- make better
- follow best practices
- as much as possible
- until satisfied
- keep up to date

Rewrite into fixed targets:

| Activity-shaped request | State-shaped rewrite |
| --- | --- |
| Improve tests | Tests cover named behaviors and pass under command C |
| Clean up code | Current lint violations are zero and duplicated helper X is consolidated |
| Optimize performance | Endpoint E p95 latency is under N ms on benchmark B |
| Make docs better | Docs include sections A/B/C and pass checklist R |
| Modernize dependencies | Update package set S to versions available as of date D |
| Make production-ready | Frozen checklist C has no unresolved P0/P1 items |
| Research options | Produce a decision memo comparing A/B/C against criteria X/Y/Z |

## Registry-as-goal

Bad: run `/goal` against all of `GOALS.md`.
Good: select one ready goal and compile `.goals/current.md`.

## Campaign-parent-as-goal

Bad: render or run a campaign parent (or a multi-objective aspiration) as one *single-goal* `/goal` — one contract, one hash, unbounded scope.
Good: decompose into finite children, each a full contract. Then either compile at most one ready child into `.goals/current.md` (human-stepped), or render the **locked** campaign as a *chain* via `render_goal.py --campaign` — every child individually frozen, the chain bounded by its own budget and failure policy. The parent is never executed as a single goal.

## Kitchen-sink single goal

Bad: one contract that bundles several independent objectives ("fix auth and add search and modernize deps").
Good: one finite objective per contract; the others become candidates in the campaign/backlog.

## Greenfield without a verifier

Bad: a first greenfield goal whose completion is "the app looks done" with no runnable check.
Good: a minimal artifact plus a smoke test and run instructions, verified by an executing command.

## Self-ratified completion

Bad: "Done because the agent says it is better."
Good: command output, artifact, metric, external review, or evidence path.

## Mutable target

Bad: executor can edit `.goals/current.md` mid-run.
Good: current.md hash is written before launch and audited at close.

## Silent adjacency creep

Bad: while fixing auth, refactor the whole API layer.
Good: record API refactor as a follow-up candidate.

## Single-goal-centered chain handoff

Bad: the handoff output says "start with G-001" — the same text is injected into every new thread, so every thread re-sees G-001 even after it is done.
Good: the rendered chain derives the next pending child from `campaign_status.py` every time, skips achieved children, and stops when the status tool says stop; the same line stays correct across the whole campaign lifecycle.

## Authoring-thread goal wrapper

Bad: after rendering the launch line, the author also creates a host thread goal ("execute the locked campaign when launched") — it persists into every new thread and duplicates the launch line under a second system.
Good: the final message ends with the launch line verbatim; the host's thread-goal tracker belongs to the thread where the user pastes it. GoalSpec goals are workspace artifacts, not host thread goals.

## Pre-baked review

Bad: `## Decomposition Review` written in the same pass as the manifest it claims to have reviewed, before validation ever ran — self-attestation shaped like a review.
Good: validate (copy the review anchor) → independent adversarial review → apply or decline each finding → record per-child verdicts plus the `Anchor:` line; a stale or missing anchor warns on every later validation.

## Milestone-wrapper decomposition

Bad: children are the source roadmap's milestone names with status labels and by-reference acceptance criteria — one child bundles a dozen work units the source already defined.
Good: the near wave decomposes to the source's own handoff grain (epics, tickets, numbered work packages), each child fitting its own budget with an oracle derived from its own clauses; the far tail stays sketched-conditional.
