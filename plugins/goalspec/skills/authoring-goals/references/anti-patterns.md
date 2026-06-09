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

Bad: render or run a campaign parent (or a multi-objective aspiration) as one `/goal`.
Good: decompose into finite children, compile at most one ready child into `.goals/current.md`; the parent is never executed.

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
