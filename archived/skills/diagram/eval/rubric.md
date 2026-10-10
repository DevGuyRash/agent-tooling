# Scoring rubric — the six validity layers

Every output is scored on six layers. Layers 1–4 are mechanical or checklist-driven and gate delivery. Layers 5–6 are judgment, scored 0–2, improved through the critique loop, never guaranteed.

## Layer definitions

**L1 — parse (pass/fail).** SVG: the file parses as XML — `validate_svg.py` reports no "XML parse failure". HTML: the file begins with `<!DOCTYPE html>` and loads without parse-level errors.

**L2 — render (pass/fail/unavailable).** `render_preview.sh` produces a PNG, or the file opens in a browser without a blank canvas or console exception. If no renderer exists in the runtime, record `unavailable` — that is a preflight finding, not an output failure. CDN-backed HTML scored offline is also `unavailable`, but the output must have stated its network dependency (checked under L5).

**L3 — mechanical layout (pass/fail + counts).** `validate_svg.py` reports zero errors. Record the warning count; warnings don't fail the layer, but a warning type that recurs across runs belongs in the failure corpus.

**L4 — accessibility (pass/fail).** Checklist: SVG root carries `role="img"` with `<title>` and `<desc>`; every canvas carries `role="img"` + `aria-label` + fallback text; no text below 11px; multi-series visuals pair color with a second cue (dash, marker, hatch); a dark-mode block exists wherever ramp classes are used. All present = pass.

**L5 — semantic (0–2).**

- 0: the visual says something false or misleading — wrong relationship, wrong mechanism, invented data presented as real, or an undisclosed network dependency.
- 1: accurate but shallow — true boxes and arrows that miss what matters about the subject.
- 2: accurate and well-chosen — the form fits the ask (route-on-verb honored); an illustrative piece would survive having its labels removed; a reference piece is a correct map.

**L6 — aesthetic (0–2).**

- 0: cluttered, unbalanced, off-token (rainbow-cycled steps, shadows, mixed fonts), or unreadable in either color mode.
- 1: clean and on-token but generic or stiff.
- 2: polished — balanced composition, color that carries meaning, generous whitespace (or rich fill, for art), instantly readable in light and dark.

## Delivery gate

A file may be delivered only when every layer-1–4 check that could be run passes; checks that could not run (degraded environment) must be disclosed per the preflight ladder. L5–L6 never block delivery and are never promised.

## Suite metrics — per family × variant × runtime

- `first_pass_clean`: share of outputs passing L1–L4 with no repair round. Target for the `skill` variant: ≥95% (long-run); record the baseline gap from the first run onward.
- `repair_rounds`: mean validator/render iterations to reach clean.
- `l5_mean`, `l6_mean`: judgment means. Target: `skill` beats `baseline`. If `det-layout` decisively beats `skill` on a graph-shaped family, the routing default for that family changes — that is the arm's purpose.
- `runtime_parity`: gap between runtimes on `first_pass_clean` ≤5 points; anything larger is a portability finding, not noise.

## Failure corpus format

One directory per distinct defect: `failures/NNN-short-slug/`

- `prompt.txt` — suite id + the verbatim prompt
- `output.svg` / `output.html` — the failing artifact, untouched
- `defect.md` — the layer failed, the symptom, the rule violated or missing, the proposed fix, and a recurrence list (run dates on which it appeared)

Rules of evidence: one occurrence is an anecdote. The same `defect.md` gaining a second run date is the threshold for changing guidance. When a rule change ships, cite the failure ids in the skill-root CHANGES.md so every rule traces to evidence — and a rule whose failure mode stops recurring for two full runs is a pruning candidate.
