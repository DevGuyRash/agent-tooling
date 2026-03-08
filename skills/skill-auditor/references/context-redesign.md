# Context Redesign

Context redesign keeps the active skill short, navigable, and progressively
disclosed.

## Loading Model

- Level 0 — metadata for retrieval
- Level 1 — a short `SKILL.md` that routes the workflow
- Level 2 — one question-specific reference at a time
- Level 3 — scripts or assets only on demand

## Redesign Rules

You SHALL keep `SKILL.md` operational rather than encyclopedic.
You SHALL keep every active reference directly reachable from `SKILL.md`.
You SHALL keep active reference depth to one hop from `SKILL.md`.
WHEN theory, long examples, or pattern libraries are not needed for the current
question THEN you SHALL move them out of `SKILL.md`.
WHEN a reference mostly repeats `SKILL.md` THEN you SHALL collapse the
duplication into one source of truth.
WHEN scripts or assets are not needed for the current question THEN you SHALL
leave them unloaded.

## What To Inspect

- Top-level file size and navigability
- Directness of reference links
- Duplication between `SKILL.md` and references
- Whether scripts replace context instead of inflating it
- Whether the next step is obvious after reading only one file

## Trimming Plan

1. Keep the product summary.
2. Keep the question router.
3. Keep the output contract pointer.
4. Move theory, examples, and patterns into direct references.
5. Flatten any reference chain that requires opening another reference.

## Deliverables

You SHALL describe the main source of context waste.
You SHALL propose a trimming or restructuring plan.
You SHALL say which file should own each moved fact.
You SHALL include a verification step that proves a fresh agent can understand
the workflow from `SKILL.md` plus one next reference file.
