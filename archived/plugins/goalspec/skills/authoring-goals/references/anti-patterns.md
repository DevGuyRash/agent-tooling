# GoalSpec Anti-Patterns

GoalSpec fails when it produces artifacts before decisions, blocks on safe defaults, or hands execution a context summary without probes.

## Premature Docs

Bad:

```md
Created `context/docs/imports-prd.md` for "Make imports less painful."
```

The user is still exploring. The first output should be an Option Map, not a durable doc.

Better:

```md
Options:
1. Correctness first.
2. Diagnostics first.
3. Tolerance first.

Recommendation: choose diagnostics first if the pain is support burden; choose correctness first if there is a named broken case.
```

## False Blockers

Bad:

```md
Stop until the owner decides whether missing owners are represented as `null` or `"unknown"`.
```

If either representation is reversible and locally testable, this is not a true blocker.

Better:

```md
Safe default: use `owner: null`, preserve the row, and note that product ops may later choose a different missing-owner representation.
```

## Option Theater

Bad:

```md
Option A: write a PRD.
Option B: write a design doc.
Option C: write a roadmap.
```

Those are artifact choices, not product directions.

Better:

```md
Option A: optimize import correctness.
Option B: optimize error diagnosis.
Option C: optimize tolerance for messy files.
```

## Probe-Free Handoff

Bad:

```md
Next worker: implement the Recipe Search MVP according to the PRD.
```

This leaves the executor to rediscover what a weak implementation would miss.

Better:

```md
Probe: query `soup` over `Soup`, `Tomato Soup`, and `Soup Dumplings`; exact `Soup` must rank first.
Probe: existing code can still iterate non-empty results and read `recipe["title"]`.
```

## HOW Leakage

Bad:

```md
Acceptance:
- Use `csv.reader`.
- Add a helper function.
```

Those are implementation moves. They may be good choices, but they are not the user-visible outcome.

Better:

```md
Acceptance probe:
- `Ada,ada@example.com,"123 Main St, Apt 4"` produces one address value: `123 Main St, Apt 4`.
```

## Lost Rejected Alternatives

Bad:

```md
Decision: use metadata-bearing search results.
```

Future readers cannot tell why this was chosen.

Better:

```md
Chosen: metadata-bearing list.
Rejected: sentinel dict because it creates fake recipe objects; non-list object because it breaks existing iteration.
```

## Runtime Overreach

Default authority from lock files, lifecycle state, verifier gates, hooks, graph promotion, and reviewer machinery looks safer than it is: if source interpretation is wrong, the machinery preserves the wrong thing.

Keep authority with the agent and reviewer: shape decisions and generate probes instead of pretending to automate semantic correctness.
