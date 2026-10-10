# Diagrams — flowcharts, structural, illustrative, decision tables, ladders

Diagrams are the hardest output type — they have the highest failure rate due to precise coordinate math. The two rules that prevent most failures:

1. Arrow intersection check: before writing any `<line>` or `<path>`, trace its coordinates against every box already placed. If it crosses any rect's interior (not just its source/target) it will visibly slash through — use an L-bend detour: `<path d="M x1 y1 L x1 ym L x2 ym L x2 y2" fill="none"/>`. Applies equally to lines crossing labels.
2. Box width from longest label: `rect_width = max(title_chars × 8, subtitle_chars × 7) + 24`. A 100px box holds a 10-char subtitle at most.

Tier packing — compute total width BEFORE placing. Example, four boxes:

- WRONG: x=40,160,260,360 at w=160 → overlaps (4×160 = 640 > available).
- RIGHT: x=50,200,350,500 at w=130, gap=20 → 4×130 + 3×20 = 580 ≤ 590 safe width; right edge 630 ≤ 640. Trees are sized bottom-up: leaf tier first, parent width ≥ sum of children.

## Picking the type — document vs understand

Reference diagrams (the user wants a map to point at — precision first):

- Flowchart: steps, decisions, transformations. "Walk me through the process", "what are the steps", "what's the flow".
- Structural: things inside things. "What's the architecture", "how is this organized", "where does X live".

Intuition diagrams (the user wants to feel the mechanism — mental model first). These should look nothing like a flowchart:

- Illustrative: draw the mechanism. Physical subjects get cross-sections and cutaways; abstract subjects get spatial metaphors. "How does X actually work", "explain X", "I don't get X".

Route on the verb, not the noun — same subject, different drawing:

| User says | Type | Draw |
| --- | --- | --- |
| "how do LLMs work" | Illustrative | token row, stacked layer slabs, attention threads between tokens |
| "transformer architecture" | Structural | labeled boxes: embedding, heads, FFN, norm |
| "how does attention work" | Illustrative | one query token, fan of lines to every key, opacity = weight |
| "how does gradient descent work" | Illustrative | contour surface, ball, trail of steps |
| "what are the training steps" | Flowchart | forward → loss → backward → update |
| "how does TCP work" | Illustrative | two endpoints, numbered packets in flight, ACK returning |
| "TCP handshake sequence" | Flowchart | SYN → SYN-ACK → ACK |
| "Krebs cycle / event loop" | HTML stepper | click through stages — never a ring |
| "how does a hash map work" | Illustrative | key falling through a funnel into buckets |
| "database schema / ERD" | mermaid | see charts.md — not hand-placed SVG |
| "CI pipeline with 12 jobs and fan-in" | mermaid flowchart | see Dense graphs below — not hand-placed SVG |

The illustrative route is the default for "how does X work" with no further qualification — it's the ambitious choice; don't retreat to a flowchart because it feels safer. Don't mix families in one canvas: if both are needed, draw the intuition version first, then the reference version as a second file. For complex topics, produce a series of small diagrams rather than one dense one, and explain each in the reply text between them.

## Flowchart

- Single direction (all top-down or all left-right). Max 4–5 nodes per diagram; ≤4 boxes per horizontal tier at full width (~140px); 5+ → shrink to ≤110px, wrap to two rows, or split diagrams.
- 60px between boxes, 24px inside padding, 10px arrowhead gap, two-line boxes ≥56px tall with 22px between lines.
- Vertical centering: every `<text>` gets `dominant-baseline="central"` with y at the center of its slot (for a row inside a multi-row box, that row's center, not the box's).
- Same content type = same height: 44px single-line, 56px two-line.
- Arrow labels are usually unnecessary — if meaning isn't obvious from source + target, put it in the box subtitle or the reply prose. Standalone floating labels collide and read ambiguous; minimize them.

Dense graphs: ≈8+ nodes or multi-way fan-in/fan-out exceeds the hand-layout envelope — emit a mermaid `flowchart TD` (or `LR`) instead, rendered via the mermaid init pattern in charts.md with identical themeVariables. Hand-placed SVG stays the default below that threshold, where its aesthetic control pays off. This routing is under evaluation (`eval/` variant `det-layout`); don't move the threshold without suite evidence.

Components (classes from tokens.md stylesheet):

Single-line node (44px):

```svg
<g class="c-blue">
  <rect x="100" y="20" width="180" height="44" rx="8" stroke-width="0.5"/>
  <text class="th" x="190" y="42" text-anchor="middle" dominant-baseline="central">T-cells</text>
</g>
```

Two-line node (56px):

```svg
<g class="c-blue">
  <rect x="100" y="20" width="200" height="56" rx="8" stroke-width="0.5"/>
  <text class="th" x="200" y="38" text-anchor="middle" dominant-baseline="central">Dendritic cells</text>
  <text class="ts" x="200" y="56" text-anchor="middle" dominant-baseline="central">Detect foreign antigens</text>
</g>
```

Connector: `<line x1="200" y1="76" x2="200" y2="120" class="arr" marker-end="url(#arrow)"/>` Neutral start/end/generic nodes: `<rect class="box" .../>` with default text.

Cycles and feedback: never a physical return arrow fighting the flow direction and never a ring layout (every spacing rule here is Cartesian — rings guarantee satellite-box collisions and tangential arrows). Use a small `↻ returns to start` text near the cycle point, or build an HTML stepper (interactive.md) where each stage is a panel and Next wraps around — each panel owns its inputs/products so nothing shares a canvas.

## Structural diagram

For containment: where processes happen. Cells/organelles, VPC/subnet/ instance, cache hierarchies, buildings.

- Outermost container: large rect, rx=20–24, lightest fill, 0.5px stroke, 14px medium label top-left inside.
- Inner regions: rx=8–12, side by side, 16px+ gaps, 20px minimum padding inside every container — nothing touches container edges.
- Max 2–3 nesting levels at 680px width.
- Regions contain text only: name (14px medium) + short description (12px). No flowchart boxes inside regions, no icons.
- External inputs/outputs sit outside with short labels and arrows in/out.
- Color: nested regions need distinct ramps — the same class on parent and child gives identical fills and flattens hierarchy. Related ramp for inner structure (green envelope → teal desk inside), contrasting ramp for a functionally different region (amber reading room).
- Schematic containers are dashed rects with labels — don't draw literal shapes (organelle ovals, cloud outlines, server towers). A dashed rect labeled "Reactor vessel" beats an ellipse that clips content.

Example skeleton (outer + two inner + labeled internal arrow + external in):

```svg
<g class="c-green">
  <rect x="120" y="30" width="560" height="260" rx="20" stroke-width="0.5"/>
  <text class="th" x="400" y="62" text-anchor="middle">Library branch</text>
  <text class="ts" x="400" y="80" text-anchor="middle">Main floor</text>
</g>
<g class="c-teal">
  <rect x="150" y="100" width="220" height="160" rx="12" stroke-width="0.5"/>
  <text class="th" x="260" y="130" text-anchor="middle">Circulation desk</text>
  <text class="ts" x="260" y="148" text-anchor="middle">Checkouts, returns</text>
</g>
<g class="c-amber">
  <rect x="450" y="100" width="210" height="160" rx="12" stroke-width="0.5"/>
  <text class="th" x="555" y="130" text-anchor="middle">Reading room</text>
  <text class="ts" x="555" y="148" text-anchor="middle">Seating, reference</text>
</g>
<text class="ts" x="410" y="175" text-anchor="middle">Books</text>
<line x1="370" y1="185" x2="448" y2="185" class="arr" marker-end="url(#arrow)"/>
<text class="ts" x="40" y="185" text-anchor="middle">New acq.</text>
<line x1="75" y1="185" x2="118" y2="185" class="arr" marker-end="url(#arrow)"/>
```

## Illustrative diagram

For building intuition. Physical subjects drawn as simplified selves (cross-sections, cutaways); abstract subjects drawn as invented spatial metaphors where the shape makes the mechanism obvious — a stack of slabs with a bright attention thread, a funnel over buckets, a literal stack of call frames, dots clustering in embedding space. The metaphor IS the explanation. A good illustrative diagram still works with the labels removed.

What changes from flowchart/structural rules:

- Shapes are freeform: `<path>`, `<ellipse>`, `<polygon>`, curves. A tank is a tall rounded rect; a valve is two curved paths; a trace is a polyline.
- Layout follows the subject's geometry, not a grid — tall subjects get tall canvases, wide subjects wide ones, inside the 680 width.
- Color encodes intensity: warm = heat/energy/active/attended, cool/gray = cold/dormant/ignored. A glance should show where the action is.
- Shape overlap is encouraged for depth (pipe entering tank, fan of lines through layers); later in source = on top, layered deliberately.
- Text is the exception — never let a stroke cross it. Every label needs 8px clear air. Don't fix collisions with background rects; move the text to a quiet region: above, below, or the margin with a leader line. No quiet region = the drawing is too dense; remove something or split.
- Small shape indicators allowed when they show physical state: triangles for flames, circles for bubbles/particles, wavy lines for steam, parallel lines for vibration. Simple primitives, not detailed art.
- Fidelity ceiling: schematics, not illustrations. Any `<path>` needing more than ~6 segments → simplify. Recognizable silhouette beats accurate contour; if you're tracing an outline you've overshot.
- One two-stop `<linearGradient>` permitted — only for a continuous physical property across a region (temperature stratification, pressure drop), both stops from one ramp. No radial, no multi-stop, no gradient-as-aesthetic. If two stacked flat rects say the same thing, do that.
- Lines stop at component edges — draw segments that end at the boundary; never draw through and hide with a fill (backgrounds aren't guaranteed).

Label placement: prefer outside the drawing with 0.5px dashed leaders. Large internal zones may hold labels with ≥20px clearance. Pick ONE side for the label column and put them all there — 680px can't afford two; default to right-side labels with text-anchor="start" (left-side text-anchor="end" labels are the ones that silently clip past x=0). 12px callouts, 14px medium for major component names.

Composition order: (1) main silhouette centered, (2) internal structure, (3) external connections and flow arrows, (4) state indicators last (fills, small animated elements), leaving generous whitespace for labels.

Static vs interactive: a cross-section you can operate beats one you can only look at. If the real system has a control, give the diagram that control (thermostat → slider shifting the hot/cold boundary; attention → click a token to re-fan weights; cache → drag hit rate, watch latency). Reach for HTML + inline SVG (see interactive.md); fall back to static SVG only when there's genuinely nothing to twiddle.

Worked abstract example — attention. Three layer slabs, a token row, one highlighted query, weight-scaled amber lines fanning to every token, caption below the fan in clear space:

```svg
<rect class="c-purple" x="60" y="40" width="560" height="26" rx="6" stroke-width="0.5"/>
<rect class="c-purple" x="60" y="80" width="560" height="26" rx="6" stroke-width="0.5"/>
<rect class="c-purple" x="60" y="120" width="560" height="26" rx="6" stroke-width="0.5"/>
<text class="ts" x="72" y="57">Layer 3</text>
<text class="ts" x="72" y="97">Layer 2</text>
<text class="ts" x="72" y="137">Layer 1</text>
<line stroke="#EF9F27" stroke-linecap="round" x1="340" y1="230" x2="116" y2="146" stroke-width="1" opacity="0.25"/>
<line stroke="#EF9F27" stroke-linecap="round" x1="340" y1="230" x2="228" y2="146" stroke-width="1.5" opacity="0.4"/>
<line stroke="#EF9F27" stroke-linecap="round" x1="340" y1="230" x2="340" y2="146" stroke-width="4" opacity="1"/>
<line stroke="#EF9F27" stroke-linecap="round" x1="340" y1="230" x2="452" y2="146" stroke-width="2.5" opacity="0.7"/>
<line stroke="#EF9F27" stroke-linecap="round" x1="340" y1="230" x2="564" y2="146" stroke-width="1" opacity="0.2"/>
<rect class="c-gray" x="80" y="230" width="72" height="36" rx="6" stroke-width="0.5"/>
<rect class="c-gray" x="192" y="230" width="72" height="36" rx="6" stroke-width="0.5"/>
<rect class="c-amber" x="304" y="230" width="72" height="36" rx="6" stroke-width="1"/>
<rect class="c-gray" x="416" y="230" width="72" height="36" rx="6" stroke-width="0.5"/>
<rect class="c-gray" x="528" y="230" width="72" height="36" rx="6" stroke-width="0.5"/>
<text class="ts" x="116" y="252" text-anchor="middle">the</text>
<text class="ts" x="228" y="252" text-anchor="middle">cat</text>
<text class="th" x="340" y="252" text-anchor="middle">sat</text>
<text class="ts" x="452" y="252" text-anchor="middle">on</text>
<text class="ts" x="564" y="252" text-anchor="middle">the</text>
<text class="ts" x="340" y="300" text-anchor="middle">Line thickness = attention weight from "sat" to each token</text>
```

Note what's absent: no "multi-head attention" boxes, no Q/K/V arrows — those belong in the structural version. This one is the feeling of attention.

When NOT to go illustrative: the user wants a reference ("what are the components of X" → structural; "walk me through our pipeline" → flowchart), or the metaphor would be arbitrary rather than revealing (drawing "the cloud" as a cloud teaches nothing). If the drawing doesn't make the mechanism clearer, don't draw it.

## Decision table

If/then rules as rows: neutral condition box → arrow → colored action box.

```svg
<rect class="box" x="50" y="40" width="320" height="48" rx="8"/>
<text class="th" x="210" y="64" text-anchor="middle" dominant-baseline="central">Tests pass on main</text>
<line x1="378" y1="64" x2="410" y2="64" class="arr" marker-end="url(#arrow)"/>
<g class="c-teal">
  <rect x="420" y="40" width="210" height="48" rx="8" stroke-width="0.5"/>
  <text class="th" x="525" y="64" text-anchor="middle" dominant-baseline="central">Deploy</text>
</g>
```

Rows at 64px pitch; a thin dashed separator (class="leader") may divide logical groups. Action color carries meaning: teal/green = go, coral = act against, gray = stand down, red = hard stop.

## Level ladder

Value zones stacked on a linear scale (price levels, thresholds, ranges).

- Mapping: top = highest level + ~5% headroom, bottom = lowest − ~5%; y(v) = y_top + (v_top − v) × (y_bottom − y_top)/(v_top − v_bottom).
- Ladder column x = 170..440; zone rects rx=4 with centered 14px title (12px subtitle if ≥48px tall); value labels 12px text-anchor="end" at x=158; annotations at x=474 with dashed leaders from x=440 and a 2px dot.
- Current-value marker: solid 1.5px line in an accent hex + "Now ~X" note.
- Dashed lines for invalidations/triggers, solid for hard floors; a footnote row at the bottom for what lies beyond the plotted range.
- If the value range has a vast empty stretch, cut the scale and state the far levels in the footnote rather than wasting 200px of air.
