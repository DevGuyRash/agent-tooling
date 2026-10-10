# Interactive explainers — standalone HTML

For anything the user should operate: sliders changing a model, toggles switching states, steppers walking through stages, live calculators. The decision rule from diagrams.md: if the real-world system has a control, give the diagram that control. A cross-section you can operate beats one you can only look at.

Output is a full .html page: DOCTYPE, head with the token CSS from tokens.md, content, then all `<script>` blocks at the end of body. The page is its own container: set the page background, max-width (~760px), and padding from the token CSS.

## All interactivity is local

The page runs with no backend and no agent runtime — every behavior is implemented in the file's own JavaScript:

- Filtering, sorting, toggling, stepping, and calculation are all local JS. Nothing calls out to a model or server at runtime.
- Where per-element explanations are wanted ("click a stage to learn more"), precompute the content into the page and reveal it in a local detail panel — never wire a control to an answer that doesn't exist in the file.
- Links (`<a href>`) work normally — use them for further reading.

## Page scaffold

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Compound interest</title>
[token CSS block from tokens.md]
<style>
input[type=range]{width:100%;accent-color:#378ADD}
button{font:inherit;background:transparent;color:var(--p);
border:0.5px solid var(--b2);border-radius:var(--r-md);padding:6px 14px;cursor:pointer}
button:hover{background:var(--bg2)} button:active{transform:scale(0.98)}
.card{background:var(--bg1);border:0.5px solid var(--b);
border-radius:var(--r-lg);padding:1rem 1.25rem}
</style>
</head>
<body>
[content]
[scripts]
</body>
</html>
```

## Control patterns

Slider with live readout (label left, slider flex, value right):

```html
<div style="display:flex;align-items:center;gap:12px;margin:0 0 1.5rem;">
  <label style="font-size:14px;color:var(--s);">Years</label>
  <input type="range" min="1" max="40" value="20" step="1" id="years" style="flex:1;">
  <span style="font-size:14px;font-weight:500;min-width:24px;" id="years-out">20</span>
</div>
<div style="display:flex;align-items:baseline;gap:8px;">
  <span style="font-size:14px;color:var(--s);">£1,000 →</span>
  <span style="font-size:24px;font-weight:500;" id="result">£3,870</span>
</div>
```

- Set `step` on every range so the input emits round values, and still round on display: `Math.round`, `.toFixed(n)`, or `toLocaleString()` for currency. Integers for counts, 1–2 decimals for percentages.
- Toggle switches: a styled checkbox track (32×18px rounded track, 14px thumb, transform on :checked) — no library needed.
- Wire with `oninput`/`onchange` or addEventListener; keep state in plain JS variables and re-render the affected DOM only.

## Steppers — the correct form for cycles

One panel per stage, position dots (● ○ ○), Prev/Next buttons; Next wraps from the last stage to the first — the wrap IS the loop. Each panel owns its stage's inputs and products (an event loop's pending callbacks live inside the Poll panel, not floating beside a ring). Nothing collides because nothing shares a canvas.

```html
<div id="panels"></div>
<div style="display:flex;align-items:center;gap:12px;margin-top:1rem;">
  <button onclick="step(-1)">Prev</button>
  <span id="dots" style="font-size:12px;color:var(--s);letter-spacing:4px;"></span>
  <button onclick="step(1)">Next</button>
</div>
<script>
const stages = [
  { title:'Poll', body:'Collect pending callbacks…' },
  { title:'Check', body:'Run setImmediate callbacks…' },
  { title:'Close', body:'Run close handlers…' },
];
let i = 0;
function render(){
  const s = stages[i];
  document.getElementById('panels').innerHTML =
    `<div class="card"><h3 style="margin:0 0 8px">${s.title}</h3>
     <p style="margin:0;font-size:14px;color:var(--s)">${s.body}</p></div>`;
  document.getElementById('dots').textContent =
    stages.map((_,k)=>k===i?'●':'○').join(' ');
}
function step(d){ i = (i + d + stages.length) % stages.length; render(); }
render();
</script>
```

Panels may contain inline SVG drawn to the same rules as diagrams.md — keep `viewBox="0 0 680 H"` so all label math holds.

## Inline SVG + controls (operable illustrative diagrams)

The richest pattern: an SVG mechanism with HTML controls under it. The controls mutate SVG attributes or toggle classes. Example wiring for a two-zone gradient boundary driven by a slider:

```html
<svg viewBox="0 0 680 400" width="100%">
  <defs><linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">
    <stop id="gh" offset="40%" stop-color="#D85A30" stop-opacity="0.45"/>
    <stop id="gc" offset="40%" stop-color="#378ADD" stop-opacity="0.4"/>
  </linearGradient></defs>
  <rect x="180" y="40" width="260" height="320" rx="14" fill="url(#tg)"
        stroke="#888780" stroke-width="1"/>
</svg>
<input type="range" min="10" max="90" value="40" step="1"
  oninput="document.getElementById('gh').setAttribute('offset',this.value+'%');
           document.getElementById('gc').setAttribute('offset',this.value+'%');">
```

## Animation

- CSS `@keyframes` animating only `transform` and `opacity` (plus stroke-dashoffset for flow-along-path effects).
- Loops under ~2s; gentle, purposeful — show how the system behaves (convection, rotation, packet flight), never motion for its own sake.
- Wrap every animation in `@media (prefers-reduced-motion: no-preference)` so it's opt-out by default.
- Flow along a path: `stroke-dasharray: 5 5` + keyframes to `stroke-dashoffset: -20` at ~1.6s linear infinite; vary --dur per path for organic feel. Toggle off by pausing animation-play-state and fading opacity.
- No physics engines or heavy animation libraries.

## Libraries

Online: load UMD builds from cdnjs.cloudflare.com / cdn.jsdelivr.net / unpkg.com via `<script src>`, or ES modules from esm.sh via `<script type="module">`. Offline requirement: vanilla JS only — every pattern above works without a library. State the dependency in your reply either way.
