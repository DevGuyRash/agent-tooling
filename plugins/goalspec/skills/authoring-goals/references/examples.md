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
