# Charts, maps, and ERDs — standalone HTML

All outputs here are .html files using the page scaffold and token CSS from tokens.md. Scripts load from public CDNs (cdnjs.cloudflare.com, esm.sh, cdn.jsdelivr.net, unpkg.com) — note in your reply that the file needs an internet connection to render. If the user needs offline output, draw simple bar/line charts as hand-computed SVG rects/polylines instead (same ladder math as diagrams.md) and skip maps/ERDs.

## Chart.js

```html
<div style="position:relative;width:100%;height:300px;">
  <canvas id="chart1" role="img" aria-label="Bar chart of quarterly revenue, Q1 through Q4">
    Quarterly revenue: Q1 12, Q2 19, Q3 8, Q4 15.</canvas>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const dark = matchMedia('(prefers-color-scheme: dark)').matches;
Chart.defaults.color = dark ? '#B4B2A9' : '#5F5E5A';
Chart.defaults.borderColor = dark ? 'rgba(180,178,169,.2)' : 'rgba(95,94,90,.2)';
Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
new Chart(document.getElementById('chart1'), {
  type: 'bar',
  data: { labels:['Q1','Q2','Q3','Q4'],
    datasets:[{ label:'Revenue', data:[12,19,8,15], backgroundColor:'#378ADD' }] },
  options: { responsive:true, maintainAspectRatio:false,
    plugins:{ legend:{ display:false } } }
});
</script>
```

Rules:

- Every canvas: `role="img"`, descriptive `aria-label`, fallback text between the tags. Without these the chart is invisible to screen readers.
- Canvas can't resolve CSS variables — hardcode hex; pick light/dark via `matchMedia` as above (use 400-stop hexes for series; they read on both).
- Height ONLY on the wrapper div (position:relative), never on the canvas. `responsive:true, maintainAspectRatio:false`. Horizontal bar charts: wrapper height ≥ bars × 40 + 80.
- Load the UMD build via plain `<script src>` (sets window.Chart), then a plain script after it — no type="module" for Chart.js.
- Multiple charts → unique ids, each with its own wrapper div.
- Never rely on color alone between series: pair each color with a dash pattern (lines), marker shape (scatter), or hatching (bars/pies), and show both in the legend.
- Bubble/scatter: radii extend past centers and clip at the scale edge — pad `scales.{x,y}.min/max` ~10% beyond the data, or `layout:{padding:20}`.
- ≤12 categories where every label matters (months, waterfall): `scales.x.ticks:{ autoSkip:false, maxRotation:45 }`.
- Number formatting: sign before currency — `-$5M`, never `$-5M`: `v => (v<0?'-':'') + '$' + Math.abs(v) + 'M'`. Round everything displayed.

Legends — always disable the Chart.js default and build custom HTML above or below the canvas (small squares, tight spacing, values included for categorical data):

```html
<div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:8px;font-size:12px;color:var(--s);">
  <span style="display:flex;align-items:center;gap:4px;"><span style="width:10px;height:10px;border-radius:2px;background:#378ADD;"></span>Chrome 65%</span>
  <span style="display:flex;align-items:center;gap:4px;"><span style="width:10px;height:10px;border-radius:2px;background:#888780;"></span>Safari 18%</span>
</div>
```

Dashboards: metric cards (mockups.md) in a 2–4 column grid above, chart below without a card wrapper.

## Geographic maps — D3 choropleth

Never invent coordinates: no hand-drawn region paths, no inline GeoJSON. Fetch real topology or don't draw a map.

Topology sources (cdn.jsdelivr.net only — other hosts/packages 404):

- US states: `https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json` → `d3.geoAlbersUsa()`, object key `.states`
- World: `https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json` → `d3.geoNaturalEarth1()`, object key `.countries`
- Country subdivisions: `https://cdn.jsdelivr.net/npm/datamaps@0.5.10/src/js/data/{iso3}.topo.json` (lowercase alpha-3: deu, jpn, gbr…), object key `.{iso3}`

Before writing the widget, fetch the first ~1KB of the topology (`curl -s <url> | head -c 1000`) to see the real feature `id` and `properties.name` values — key your data on those, never guess. Granularity varies (16 features or 232); if it doesn't match the ask, say so in the reply.

```html
<div id="map" style="width:100%;"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/topojson/3.0.2/topojson.min.js"></script>
<script>
const values = { 'California': 39, 'Texas': 30, 'New York': 19 };
const isDark = matchMedia('(prefers-color-scheme: dark)').matches;
const color = d3.scaleQuantize([0, 40],
  isDark ? d3.schemeBlues[5].slice().reverse() : d3.schemeBlues[5]);
const svg = d3.select('#map').append('svg')
  .attr('viewBox','0 0 900 560').attr('width','100%');
const path = d3.geoPath(d3.geoAlbersUsa().scale(1100).translate([450,280]));
d3.json('https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json').then(us => {
  svg.selectAll('path')
    .data(topojson.feature(us, us.objects.states).features).join('path')
    .attr('d', path)
    .attr('stroke', isDark ? 'rgba(255,255,255,.15)' : '#fff')
    .attr('fill', d => color(values[d.properties.name] ?? 0));
});
</script>
```

Add a quantize-scale legend (one swatch row per bucket) in HTML below the map.

## ERDs and class diagrams — mermaid

A schema table is header + N field rows + typed columns + crow's-foot connectors: a text-layout problem that hand-placed SVG fails every time. Use mermaid `erDiagram` (or `classDiagram` — same init, different source).

The same init also renders `flowchart TD` / `flowchart LR` sources — this is the target for the dense-graph fallback in diagrams.md. Keep the themeVariables identical so flowcharts, ERDs, and class diagrams match.

```html
<div id="erd"></div>
<script type="module">
import mermaid from 'https://esm.sh/mermaid@11/dist/mermaid.esm.min.mjs';
const dark = matchMedia('(prefers-color-scheme: dark)').matches;
await document.fonts.ready;
mermaid.initialize({
  startOnLoad: false, theme: 'base',
  fontFamily: 'Inter, system-ui, sans-serif',
  themeVariables: {
    darkMode: dark, fontSize: '13px',
    fontFamily: 'Inter, system-ui, sans-serif',
    lineColor: dark ? '#9c9a92' : '#73726c',
    textColor: dark ? '#c2c0b6' : '#3d3d3a',
    primaryColor: dark ? '#2C2C2A' : '#F1EFE8',
  },
});
const { svg } = await mermaid.render('erd-svg', `erDiagram
  USERS ||--o{ POSTS : writes
  POSTS ||--o{ COMMENTS : has
  USERS { uuid id PK
    string email
    timestamp created_at }
  POSTS { uuid id PK
    uuid user_id FK
    string title }`);
document.getElementById('erd').innerHTML = svg;
</script>
```

Keep fontFamily and fontSize exactly in the init — mermaid measures text for layout with them; deviate and labels clip. Optional polish: post-render, replace each entity's sharp-cornered outer `<path>` with a rounded `<rect rx="8">` and strip strokes from attribute-row paths so only the outer container and header keep borders — alternating row fills already separate rows. Skip the polish if it's not worth the script weight for the use case.
