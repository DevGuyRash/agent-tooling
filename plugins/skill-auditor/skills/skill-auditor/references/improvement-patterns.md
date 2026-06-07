# Improvement Patterns

Use these patterns as a short fix library after you identify the leading
failure.

## Wrong Primitive

WHEN the content is ambient policy THEN you SHALL move it to `AGENTS.md` or
custom instructions.
WHEN the value is a user-chosen workflow THEN you SHALL consider an explicit
prompt surface.
WHEN the value is mostly execution THEN you SHALL favor a tool or script.
Verification: confirm the new packaging reduces false triggers or ambiguity.

## Trigger Too Broad

WHEN generic words create false positives THEN you SHALL remove them before
adding new workflow detail.
WHEN nearby tasks should not trigger the skill THEN you SHALL add
discriminating terms to the description.
Verification: rerun explicit, implicit, negative, and ambiguous prompts.

## Trigger Too Narrow

WHEN obvious intended prompts do not match THEN you SHALL add missing domain,
file-type, or task-family terms.
Verification: confirm implicit prompts now activate without increasing negative
control failures.

## Top-Level Overload

WHEN `SKILL.md` explains too much theory THEN you SHALL cut it back to product
summary, routing, and output contract.
WHEN details are still needed THEN you SHALL move them into direct references.
Verification: confirm a fresh agent can understand the workflow from
`SKILL.md` plus one next reference file.

## Workflow Ambiguity

WHEN the skill leaves the first move unclear THEN you SHALL add a clear
"first do / then do" sequence.
WHEN failure modes are predictable THEN you SHALL add a retry or fallback note.
Verification: rerun one canonical task and compare thrash level before/after.

## Missing Verification Loop

WHEN recommendations do not say how to confirm success THEN you SHALL add
fix → rerun → compare guidance.
Verification: ensure each change has a paired check and next action on failure.

## Script Overreach

WHEN a heuristic lint script dominates the workflow THEN you SHALL replace it
with guidance unless it provides structural evidence that reasoning cannot.
Verification: confirm the active script set stays small and focused.

## Portability Mismatch

WHEN a recommendation depends on host-specific behavior THEN you SHALL label it
with the correct profile instead of presenting it as universal.
Verification: confirm open-standard guidance still stands on its own.
