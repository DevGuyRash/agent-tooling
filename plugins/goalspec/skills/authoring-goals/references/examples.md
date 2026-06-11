# Examples

## Clear task

Input:

```text
Fix the checkout total rounding bug.
```

Output: one `.goals/current.md` with terminal state, verifier, scope, budget, give-up, completeness, and paste-ready `/goal`.

## Vague aspiration

Input:

```text
Make onboarding better.
```

Output: not launchable as written. Suggested finite replacements:

1. Fix all current onboarding form validation errors reproduced by tests.
2. Update onboarding copy to match glossary G and pass human review checklist R.
3. Reduce onboarding completion time under benchmark B after identifying the top three measured friction points.

## Existing GOALS.md

Input: a registry with mixed vague and ready items.

Output: lint report with statuses: ready, conditional, blocked, maintenance-loop, too broad, duplicate.

## Existing run report

Input: `.goals/current.md` and `.goals/reports/latest.md`.

Output: audit result based on evidence, not confidence.

## Decompose a large request

Input:

```text
Modernize the whole app: upgrade deps, add tests everywhere, refactor the API, and improve performance.
```

Output: not one contract. A campaign manifest (`.goals/campaign-modernize.md`) splitting the aspiration into finite children with readiness statuses, e.g.:

1. `ready` — Upgrade dependency set S to versions available as of date D; build and test command C exit 0.
2. `conditional` — Add tests for module M once its public API is frozen (needs decision).
3. `not-launchable` — "Refactor the API" has no checkable terminal state; needs a concrete target.

Compile only child 1 into `.goals/current.md`. The campaign parent is never run.

## Greenfield / from spec

Input:

```text
Build a CLI that converts CSV to JSON. No code yet; here is a one-paragraph spec.
```

Output: skip the repo scan, inventory the language/test runner, and compile one small `.goals/current.md`: a minimal `csv2json` plus a smoke test, terminal state "the smoke test command exits 0 on the sample input", verifier = that command, bounded budget. Not "the CLI is done".
