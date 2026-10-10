# Evaluation harness

This directory is what makes the skill a measured system instead of a prose document. The verdict that produced this version of the skill set one governing rule, restated here because it governs this folder too:

> Add no new guidance unless it fixes a failure that repeats in this suite. Remove guidance the suite shows no longer earns its context cost.

Contents:

- `prompts.yaml` — the fixed suite: 37 prompts — 36 across the ten output families plus one scope-boundary probe — each tagged with the failure mode it probes.
- `rubric.md` — the six-layer scoring definitions and suite targets.
- `score.sh` — mechanical scorer: runs the validator and renderer over a run directory and emits a CSV covering the machine-checkable layers.
- `failures/` — the retained failure corpus (format in rubric.md).

## Variants

Run each prompt under up to three variants:

- `baseline` — the agent without this skill loaded. This is the comparator; "better" means better than this, not better than nothing.
- `skill` — the agent with this skill loaded normally.
- `det-layout` — graph-shaped families only (`flowchart`, `structural`, `erd`): the agent emits nodes/edges and delegates geometry to mermaid (or graphviz if available), then applies the tokens. This arm exists to adjudicate the open question of whether hand-placed SVG or deterministic layout should be the default for graph-shaped outputs. Do not settle that question by taste; settle it here.

## Runtimes

Run the suite in every runtime the skill claims to support — at minimum Claude Code and Codex. Before the first run in a runtime, run `scripts/preflight.sh` and record its output with the results; a capability difference between runtimes is a finding, not noise.

## Procedure

1. For each runtime × variant, start fresh sessions and run each prompt from `prompts.yaml`. Save outputs to `eval/runs/<yyyy-mm-dd>-<runtime>-<variant>/<id>.<svg|html>`. One prompt per session where practical — carryover context contaminates.
2. Mechanical pass: `eval/score.sh eval/runs/<dir>` → `results.csv` with layer 1–3 proxies (parse, validator errors/warnings, render success).
3. Reviewer pass: open each rendered preview (or the file in a browser, both light and dark mode) and score layers 4–6 per `rubric.md`. A vision-capable model may pre-score; a human spot-checks.
4. Aggregate per family and per runtime. Compare `skill` against `baseline`; compare `det-layout` against both for graph-shaped families.
5. Log every layer-1–4 failure and every layer-5/6 score of 0 into `failures/` (format in rubric.md). Repeated failures are the only license to add a rule; rules whose failure mode never recurs across two full runs are pruning candidates.

## Cadence

- Before and after any change to SKILL.md or references/ — the diff in suite results is the change's justification or its indictment.
- Periodically against new base-model versions: base models improve, so the skill's context tax has to be re-justified over time. A shrinking skill-vs-baseline gap on some family means pruning that family's rules, not defending them.

## What "working" means

Targets are in rubric.md. In one line: ≥95% of first-pass `skill` outputs clean on layers 1–4, rubric preference over `baseline` on layers 5–6, scored per family, at parity across runtimes — with the suite re-run on every rule change.
