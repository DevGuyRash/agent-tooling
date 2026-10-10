---
name: diagram
description: Produce polished standalone visuals as files and open them in the browser — SVG flowcharts, architecture and containment diagrams, illustrative explainers, decision tables, level ladders, charts (Chart.js), geographic choropleth maps (D3), database ERDs (mermaid), interactive HTML explainers with sliders and steppers, UI mockups, and SVG art. Use this skill whenever the user asks for a diagram, chart, graph, map, mockup, visualization, schematic, ladder, or illustration, or says "draw", "sketch", "visualize", "plot", "show me", or "illustrate" about any structure, process, data, comparison, or concept — even if they never mention SVG or HTML.
---

# Visuals

This is a visuals skill, not an SVG skill. It renders diagrams, charts, interactive explainers, mockups, and art as standalone files (.svg or .html) and opens them in the browser when one is available. Routing charts, maps, ERDs, interactivity, and mockups to HTML + libraries is deliberate: those are the right media, and forcing them into hand-placed SVG makes them worse.

The generic asset is the method — routing, geometry rules, the token system, the checklist, the validators, and the verification loop. The output families and the house style are specialized instances of that method; fork them per domain (see Maintaining this skill). Quality is measured, not promised: the target is measurably fewer invalid, clipped, unreadable, or low-quality outputs than a no-skill baseline on the fixed suite in `eval/`, scored per output family.

## Scope

In scope: the ten output families in the routing table below.

Out of scope for the base skill: logos, icon systems, print-ready layout, production brand systems, CAD or technical drawings, animation beyond the constrained CSS patterns in interactive.md, photorealistic illustration, highly bespoke data journalism, and guaranteed artistic mastery. These can become specialized forks; they are not implied by the base skill.

When a request falls out of scope: say it is outside this skill's tested envelope, offer the nearest in-scope alternative (a wordmark request → a typographic SVG with the geometry rules; a print poster → a 680-wide SVG the user can scale externally), and proceed best-effort only if the user still wants it — without claiming the guarantees below.

## Definition of done — six validity layers

1 parse · 2 render · 3 mechanical layout · 4 accessibility · 5 semantic · 6 aesthetic. Validity is a taxonomy, not a promise.

Layers 1–4 are machine-checkable and gate delivery: the file parses, it renders (preview PNG, or the stated degradation below), the validator reports zero errors, and the accessibility items in the checklist are present. Never deliver a file that fails a layer-1–4 check you were able to run.

Layers 5–6 — does the visual say something true, and is it good — are judged from the rendered preview, improved through the critique loop, and never guaranteed. If the user asks for a guarantee of accuracy or beauty, say plainly that those are reviewed, not certified.

## Environment preflight — once per session

Run `scripts/preflight.sh` before the first visual. Degradation ladder for any capability it reports missing:

- No renderer → validator-only verification; tell the user the visual pass was skipped and suggest installing `librsvg2-bin`.
- No network → offline routes only: hand-computed SVG charts (charts.md fallback), no D3 maps, no mermaid, no icon webfonts. State the dependency instead of failing silently.
- No browser/opener → deliver the file path; skip the open step.
- No python3 → checklist-only verification; flag the reduced check in your reply.

## Workflow

1. Route the request (table below) and read the matching reference file. ALWAYS read `references/tokens.md` first — it defines the color system, typography, and the reusable stylesheet every output embeds.
2. Write every label first. Count nodes. Size boxes from the longest label.
3. Compute all coordinates (positions, gaps, viewBox height) before markup.
4. Run the final checklist below; fix and re-check on any failure.
5. Write the file to `./visuals/<slug>-<yyyy-mm-dd>.<svg|html>` (create the directory if needed), then verify it (Verification section) before delivering.
6. Open it if an opener exists: `open` (macOS), `xdg-open` (Linux), `cmd.exe /c start ""` (Windows; `explorer.exe` under WSL). Reply with the path and a one-line summary.

## Routing — pick by intent, route on the verb not the noun

| Request shape | Output | Reference |
| --- | --- | --- |
| Steps, process, branching, "what's the flow" | SVG flowchart | references/diagrams.md |
| Containment, architecture, "where does X live" | SVG structural | references/diagrams.md |
| "How does X actually work", intuition, mechanisms | SVG/HTML illustrative | references/diagrams.md |
| If/then rules, triggers, level ladders | SVG decision table / ladder | references/diagrams.md |
| Data series, comparisons over time, distributions | HTML + Chart.js | references/charts.md |
| Values by region/country/state | HTML + D3 choropleth | references/charts.md |
| Database schema, ERD, class diagram | HTML + mermaid | references/charts.md |
| Anything with controls: sliders, toggles, steppers | HTML interactive | references/interactive.md |
| App screens, dashboards, forms, cards | HTML mockup | references/mockups.md |
| Decorative illustration, patterns, scenes | SVG art | references/art.md |

A cycle (event loop, Krebs, retry loop) is never drawn as a ring — use an HTML stepper (interactive.md) or a linear flow with a "returns to start" note. Six or more components in one ask → split into an overview plus one small diagram per sub-flow; never cram one canvas. A dense or heavily branching graph (≈8+ nodes, multi-way fan-in/fan-out) exceeds the hand-layout envelope → render it as a mermaid `flowchart` via the init pattern in charts.md instead. This routing threshold is under evaluation (`eval/` variant `det-layout`); don't move it without suite evidence.

## Universal rules (apply to every output)

- Sentence case everywhere. No ALL CAPS, no Title Case, no rotated text.
- Two font sizes: 14px titles/labels, 12px secondary. Nothing below 11px. Two weights only: 400 and 500. Never 600/700.
- Font stack: Inter, system-ui, sans-serif.
- Flat design: no drop shadows, blur, glow, or decorative gradients. One two-stop gradient is allowed only in illustrative diagrams for a continuous physical property (see diagrams.md), and freestyle color is allowed in art.
- Color encodes meaning (category, state, intensity) — never sequence. Don't rainbow-cycle steps. ≤2 color ramps per diagram plus gray; if color encodes meaning, add a one-line legend.
- Text on a colored fill uses a dark stop from the same ramp — never black.
- Borders 0.5px, level/connector lines 1px, emphasis 1.5px. rx="4" default corner; rx="8" max emphasis; rx ≥ half height = pill, deliberate only.
- Every connector `<path>`/`<polyline>` carries `fill="none"` — SVG defaults to black fill and a curved connector without it renders as a black blob.
- Box subtitles ≤5 words. Detail goes in the reply text, not the box.
- No emoji anywhere in visual output. No icon webfonts in pure SVG files; HTML outputs may load Tabler icons from a CDN when online (see mockups.md). Never hand-draw icon paths.
- If the reply promises N visuals, deliver N files. Several small related diagrams beat one dense one; explain each in the reply text between them.
- Standalone files render on unknown backdrops: every SVG starts with a background rect, every HTML page sets a page background. Both must support dark mode via the prefers-color-scheme pattern in tokens.md.
- Accessibility: SVG roots carry `role="img"` with `<title>` and `<desc>` as first children; every chart canvas carries `role="img"` + `aria-label` + fallback text; never rely on color alone to distinguish series — pair color with a dash pattern, marker shape, or hatching.
- Round every displayed number (`toFixed`, `Math.round`, `Intl.NumberFormat`) — float math leaks 0.30000000000000004 onto screens.

## Geometry quick reference (full math in diagrams.md)

- Coordinate space is 680 wide: `viewBox="0 0 680 H"`. The label-width math below assumes this 1:1 space — don't shrink the viewBox to hug content; center narrow content instead.
- Safe area x=40..640, y=40..(H−40). H = lowest element's bottom edge + 40, computed, never guessed. No negative coordinates.
- Text width: ~8px/char at 14px weight 500, ~7px/char at 12px. Formulas, subscripts, CJK, and symbols: add 30–50%. Box width = longest label + 24px.
- 60px minimum between sibling boxes, 24px padding inside boxes, 10px gap between an arrowhead and the box it points to. Same-type boxes share a height: 44px single-line, 56px two-line.
- SVG text never wraps; deliberate multi-line needs explicit `<tspan x="..." dy="1.2em">` — but a label that needs wrapping is usually a label that needs shortening.
- Vertical centering: `dominant-baseline="central"` with y at the slot center.

## Final checklist — run before saving every file

1. viewBox height = lowest element + 40? Rightmost edge ≤ 640?
2. Any `text-anchor="end"` label extending past x=0? (chars × 7 < anchor x)
3. Every box wide enough for its longest label + 24px padding?
4. Any line crossing a box or label it isn't connected to? Reroute (L-bend).
5. Any two unrelated elements' bounding boxes intersecting? Move one. The only legal overlaps: a label inside its own box, an arrowhead touching its target, deliberate shape layering in illustrative diagrams (never text).
6. Same-row boxes: left box's x+width ≤ next box's x − 20? (Tier packing: n×w + (n−1)×gap must fit the safe width — compute, don't eyeball.)
7. Every connector has `fill="none"`? Every text has a class or explicit fill?
8. Colored fills paired with same-ramp dark text, not black? Dark mode block present? Background element present?
9. Accessibility present? SVG: `role="img"` + `<title>`/`<desc>` as first children. HTML canvas: `role="img"` + `aria-label` + fallback text.
10. HTML only: every displayed number rounded? Scripts at the end of the body?

## Verification

SVG and HTML are written without a live preview, so verification is part of the workflow, not an optional extra. Two tools in scripts/ — together they cover the machine-checkable layers (validator: layers 1, 3, and part of 4; rendered preview: layer 2 plus the layer-5/6 critique):

1. `python3 scripts/validate_svg.py <file>` — mechanical pre-flight: extents vs viewBox, estimated text width vs box width, label collisions, lines crossing boxes or text, missing fill="none", sub-11px text, row packing, background and dark-mode presence. Errors are must-fix — correct and re-run until 0 errors. Warnings are look-twice. (Widths are estimates, not font metrics; a borderline fit deserves a wider box anyway.)
2. `scripts/render_preview.sh <file>` — rasterizes to PNG via rsvg-convert, inkscape, imagemagick, or headless chromium, whichever exists. Then READ the PNG and critique your own output against the checklist — clipping, crowding, balance, and whether the visual actually says what the subject needs said — fix and re-render. The visual pass catches what static checks can't. If no renderer is installed, say so and rely on the validator (suggest `librsvg2-bin` as the lightweight install). Rasterizers render light mode only and don't resolve CSS variables — render_preview.sh pre-resolves them (scripts/resolve_css_vars.py) before rasterizing; check dark mode by opening the file in a dark-themed browser.

## Common failure modes

Clipped content (viewBox guessed) · arrows slashing through boxes · labels colliding · text overflowing boxes · black-blob curves (missing fill="none") · black text on colored fills · rainbow-cycled steps · rings for cycles · one mega-diagram instead of several small ones · unreadable output in dark mode · dense graphs crammed into hand-placed SVG instead of mermaid · CDN-dependent output delivered without noting the network requirement.

## Maintaining this skill

Two rules govern every edit to this skill:

- Add no new guidance unless it fixes a failure that repeats in the `eval/` suite. Anecdotes don't qualify; repeated, logged failures do.
- Remove guidance the suite shows no longer earns its context cost. Base models improve — the tax has to be re-justified over time, so pruning is as much a maintenance act as adding.

Log each change against a failure id in `eval/failures/` so every rule traces to evidence.

Forking for a brand or domain: copy this folder under a new name, override the ramp table in tokens.md with the brand's design tokens, and add domain recipes to references/. Keep the workflow, geometry, checklist, and verification unchanged — they are the invariant method; the tokens and recipes are the instance.

## Evaluation

`eval/` holds the fixed prompt suite (37 prompts — 36 across the ten families plus one scope-boundary probe), the six-layer scoring rubric, a mechanical scorer (`eval/score.sh`), and the failure corpus. Run it before and after any change to this skill; procedure, variants (no-skill baseline, skill, deterministic-layout arm), and targets are in `eval/README.md`.
