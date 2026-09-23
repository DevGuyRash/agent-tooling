// Local Mermaid 12.0.0 patch. Input/output geometry stays in SVG user units.
// Pure placement is shared with the maintained geometry regression.
function avVennLabelPosition(inside, outside, width, height, preferred, clearance = 2) {
  if (!inside.length || !Number.isFinite(width + height) || width <= 0 || height <= 0) return null;
  const minY = Math.max(...inside.map(c => c.y - c.radius + clearance + height / 2));
  const maxY = Math.min(...inside.map(c => c.y + c.radius - clearance - height / 2));
  if (minY > maxY) return null;
  const ys = new Set([minY, maxY, Math.max(minY, Math.min(maxY, preferred.y))]);
  const step = Math.max(1, Math.min(width, height) / 12, (maxY - minY) / 192);
  for (let y = minY; y < maxY; y += step) ys.add(y);
  let best = null;
  for (const y of ys) {
    let left = -Infinity, right = Infinity;
    for (const c of inside) {
      const dy = Math.abs(y - c.y) + height / 2;
      const radius = c.radius - clearance;
      if (radius < dy) { left = Infinity; break; }
      const reach = Math.sqrt(Math.max(0, radius * radius - dy * dy)) - width / 2;
      left = Math.max(left, c.x - reach); right = Math.min(right, c.x + reach);
    }
    if (left > right) continue;
    let intervals = [[left, right]];
    for (const c of outside) {
      const dy = Math.max(0, Math.abs(y - c.y) - height / 2);
      const radius = c.radius + clearance;
      if (dy >= radius) continue;
      const reach = Math.sqrt(radius * radius - dy * dy) + width / 2;
      const lo = c.x - reach, hi = c.x + reach;
      intervals = intervals.flatMap(([a, b]) => {
        if (hi <= a || lo >= b) return [[a, b]];
        const result = [];
        if (a <= lo) result.push([a, lo]);
        if (hi <= b) result.push([hi, b]);
        return result;
      });
      if (!intervals.length) break;
    }
    for (const [a, b] of intervals) {
      const x = Math.max(a, Math.min(b, preferred.x));
      const distance = (x - preferred.x) ** 2 + (y - preferred.y) ** 2;
      if (!best || distance < best.distance) best = { x, y, distance };
    }
  }
  return best;
}

function eDi(config, layouts, root, notes, scale, styles) {
  const svg = root.select('svg');
  const layer = svg.append('g').attr('class', 'venn-text-nodes');
  const byArea = new Map();
  for (const note of notes) {
    const key = [...note.sets].sort().join('|');
    if (!byArea.has(key)) byArea.set(key, []);
    byArea.get(key).push(note);
  }
  const circles = new Map();
  for (const area of layouts.values()) {
    if (area.data.sets.length === 1 && area.circles.length) circles.set(area.data.sets[0], area.circles[0]);
  }
  const settings = ri();
  const requested = Number.parseFloat(settings.fontSize || settings.themeVariables?.fontSize);
  const base = Number.isFinite(requested) && requested > 0 ? requested : 16;
  const gap = base * 0.35;
  for (const name of svg.node().querySelectorAll('.venn-area text')) name.style.fontSize = `${base * 1.125}px`;
  for (const [key, items] of byArea) {
    const area = layouts.get(key);
    if (!area?.text) throw new Error(`Venn region ${key} has no drawable label region. Check the set values; the original source is retained.`);
    const members = new Set(area.data.sets);
    const inside = [...circles].filter(([id]) => members.has(id)).map(([, circle]) => circle);
    // A containing set cannot be excluded from its own subset's label region.
    const outside = [...circles].filter(([id, c]) => !members.has(id) && !inside.some(m => Math.hypot(c.x - m.x, c.y - m.y) + m.radius <= c.radius + 1e-6)).map(([, circle]) => circle);
    const group = [...svg.node().querySelectorAll('.venn-area')].find(node => [...(node.__data__?.sets || [])].sort().join('|') === key);
    const name = group?.querySelector('text');
    const nameText = name?.textContent || '';
    const noteGroup = layer.append('g').attr('class', 'venn-text-area').attr('data-venn-area', key);
    if (name) {
      name.setAttribute('aria-label', nameText);
      name.style.whiteSpace = 'pre';
      name.setAttribute('text-anchor', 'middle');
      name.removeAttribute('dy'); name.removeAttribute('transform');
    }
    const boxes = items.map(note => {
      const fo = noteGroup.append('foreignObject').attr('class', 'venn-text-node-fo').attr('data-venn-note', note.id).attr('height', 1).attr('overflow', 'visible');
      const text = fo.append('xhtml:span').attr('class', 'venn-text-node').style('display', 'block').style('width', '100%').style('height', 'auto').style('font-size', `${base}px`).style('line-height', '1.2').style('white-space', 'pre-wrap').style('text-align', 'center').style('overflow-wrap', 'anywhere').style('word-break', 'normal').text(note.label ?? note.id);
      const color = styles.get(note.id)?.color;
      if (color) text.style('color', color);
      return { fo, text };
    });
    const wrapName = width => {
      if (!name || !nameText) return { height: 0, y: 0, width: 0 };
      name.textContent = ''; name.setAttribute('x', '0'); name.setAttribute('y', '0');
      const probe = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
      name.append(probe);
      const lines = []; let line = '';
      for (const token of nameText.match(/\S+\s*|\s+/gu) || []) {
        probe.textContent = line + token;
        if (line && probe.getComputedTextLength() > width) { lines.push(line); line = token; }
        else line += token;
      }
      if (line) lines.push(line);
      name.textContent = '';
      lines.forEach((text, index) => {
        const span = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        span.setAttribute('x', '0'); span.setAttribute('y', String(index * base * 1.35)); span.textContent = text; name.append(span);
      });
      const bounds = name.getBBox();
      return { height: bounds.height, y: bounds.y, width: bounds.width };
    };
    let best = null;
    const maxWidth = Math.min(...inside.map(c => 2 * c.radius - 4));
    const minWidth = Math.min(maxWidth, base * 4);
    const widthStep = Math.max(base / 2, maxWidth / 96);
    const widths = new Set([maxWidth, minWidth]);
    for (let width = maxWidth; width > minWidth; width -= widthStep) widths.add(width);
    for (const width of widths) {
      if (!Number.isFinite(width) || width <= 0) continue;
      const header = wrapName(width);
      if (header.width > width + 0.5) continue;
      const heights = boxes.map(({ fo, text }) => {
        fo.attr('width', width);
        const rect = text.node().getBoundingClientRect();
        return Math.max(base * 1.2, rect.width > 0 ? rect.height * width / rect.width : NaN);
      });
      if (heights.some(h => !Number.isFinite(h)) || boxes.some(({ text }) => text.node().scrollWidth > text.node().clientWidth + 1)) continue;
      const height = header.height + (header.height ? gap : 0) + heights.reduce((a, b) => a + b, 0) + gap * Math.max(0, boxes.length - 1);
      const point = avVennLabelPosition(inside, outside, width, height, area.text);
      if (!point) continue;
      const cost = point.distance + width * height * 0.002;
      if (!best || cost < best.cost) best = { ...point, width, height, header, heights, cost };
    }
    if (!best) throw new Error(`Venn region ${key} could not place its labels at the configured font size. Increase the diagram width or height; the original source is retained.`);
    wrapName(best.width);
    let top = best.y - best.height / 2;
    if (name && best.header.height) name.setAttribute('transform', `translate(${best.x},${top - best.header.y})`);
    top += best.header.height + (best.header.height ? gap : 0);
    boxes.forEach(({ fo }, index) => {
      fo.attr('width', best.width).attr('height', best.heights[index]).attr('x', best.x - best.width / 2).attr('y', top);
      top += best.heights[index] + gap;
    });
  }
}
