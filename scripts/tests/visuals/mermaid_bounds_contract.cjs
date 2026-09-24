const assert = require('node:assert/strict');
const path = require('node:path');

const compiled = process.argv[2];
if (!compiled) throw new Error('usage: node mermaid_bounds_contract.cjs <compiled-visuals-dir>');

const { diagramBounds } = require(path.join(compiled, 'mermaid.js'));
const {
  DocumentDouble,
  append,
} = require(path.resolve(__dirname, '../../../plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/tests/dom-double.cjs'));

const rect = (left, top, right, bottom) => ({
  left,
  top,
  right,
  bottom,
  x: left,
  y: top,
  width: right - left,
  height: bottom - top,
});

const matrix = {
  a: 1,
  b: 0,
  c: 0,
  d: 1,
  e: 0,
  f: 0,
  inverse() { return this; },
};

function fixture() {
  const document = new DocumentDouble();
  document.defaultView.getComputedStyle = element => ({
    transform: element.getAttribute?.('transform') || 'none',
    getPropertyValue(property) {
      return element.style?.getPropertyValue?.(property)
        || element.getAttribute?.(property)
        || '';
    },
  });
  const svg = append(document.body, 'svg', { viewBox: '0 0 120 80' });
  svg.getScreenCTM = () => matrix;
  const near = append(svg, 'rect', { x: '10', y: '10', width: '20', height: '20' });
  near.getScreenCTM = () => matrix;
  near.getBoundingClientRect = () => rect(10, 10, 30, 30);
  return { document, svg };
}

{
  const { document, svg } = fixture();
  const group = append(svg, 'g', { 'clip-path': 'url(#crop)' });
  const label = append(group, 'text', { x: '500', y: '40' }, 'clipped distant label');
  label.getScreenCTM = () => matrix;
  label.getBoundingClientRect = () => rect(500, 25, 650, 45);
  assert.deepEqual(
    diagramBounds(svg, document),
    [0, 0, 120, 80],
    'clipped text cannot re-expand a valid renderer viewport',
  );
}

{
  const { document, svg } = fixture();
  const label = append(svg, 'text', { x: '500', y: '40', opacity: '0' }, 'transparent distant label');
  label.getScreenCTM = () => matrix;
  label.getBoundingClientRect = () => rect(500, 25, 650, 45);
  assert.deepEqual(
    diagramBounds(svg, document),
    [2, 2, 36, 36],
    'fully transparent text cannot re-expand tight painted bounds',
  );
}

{
  const { document, svg } = fixture();
  svg.setAttribute('overflow', 'hidden');
  const object = append(svg, 'foreignObject', { x: '10', y: '40', width: '20', height: '20', overflow: 'visible' });
  object.getScreenCTM = () => matrix;
  object.getBoundingClientRect = () => rect(10, 40, 30, 60);
  const html = append(object, 'div', {}, 'overflowing HTML label');
  const text = html.firstChild;
  document.createRange = () => {
    let selected = null;
    return {
      selectNodeContents(node) { selected = node; },
      getClientRects() {
        assert.equal(selected, text);
        return [rect(10, 40, 170, 60)];
      },
    };
  };
  assert.deepEqual(
    diagramBounds(svg, document),
    [0, 0, 178, 80],
    'visible foreignObject glyph overflow remains protected across the root SVG viewport',
  );
}

{
  const { document, svg } = fixture();
  const object = append(svg, 'foreignObject', { x: '10', y: '40', width: '20', height: '20', overflow: 'hidden' });
  object.getScreenCTM = () => matrix;
  object.getBoundingClientRect = () => rect(10, 40, 30, 60);
  append(object, 'div', {}, 'clipped HTML label');
  let rangeReads = 0;
  document.createRange = () => ({
    selectNodeContents() {},
    getClientRects() { rangeReads += 1; return [rect(10, 40, 170, 60)]; },
  });
  assert.deepEqual(
    diagramBounds(svg, document),
    [0, 0, 120, 80],
    'clipped foreignObject text keeps the renderer viewport',
  );
  assert.equal(rangeReads, 0, 'clipped HTML text is not range-measured for expansion');
}

{
  const { document, svg } = fixture();
  const group = append(svg, 'g', { 'clip-path': 'url(#crop)' });
  const object = append(group, 'foreignObject', { x: '10', y: '40', width: '20', height: '20', overflow: 'visible' });
  object.getScreenCTM = () => matrix;
  object.getBoundingClientRect = () => rect(10, 40, 30, 60);
  append(object, 'div', {}, 'ancestor-clipped HTML label');
  let rangeReads = 0;
  document.createRange = () => ({
    selectNodeContents() {},
    getClientRects() { rangeReads += 1; return [rect(10, 40, 170, 60)]; },
  });
  assert.deepEqual(
    diagramBounds(svg, document),
    [0, 0, 120, 80],
    'an ancestor SVG clip cannot be bypassed by foreignObject range geometry',
  );
  assert.equal(rangeReads, 0, 'ancestor-clipped HTML text is not range-measured for expansion');
}

{
  const { document, svg } = fixture();
  const group = append(svg, 'g', { opacity: '0' });
  const object = append(group, 'foreignObject', { x: '10', y: '40', width: '20', height: '20', overflow: 'visible' });
  object.getScreenCTM = () => matrix;
  object.getBoundingClientRect = () => rect(10, 40, 30, 60);
  append(object, 'div', {}, 'ancestor-hidden HTML label');
  let rangeReads = 0;
  document.createRange = () => ({
    selectNodeContents() {},
    getClientRects() { rangeReads += 1; return [rect(10, 40, 170, 60)]; },
  });
  assert.deepEqual(
    diagramBounds(svg, document),
    [2, 2, 36, 36],
    'an invisible SVG ancestor cannot be bypassed by foreignObject range geometry',
  );
  assert.equal(rangeReads, 0, 'ancestor-hidden HTML text is not range-measured for expansion');
}

// A report-scoped stroke can be the only paint on a C4/system boundary. In
// the screenshot counterexample its lower edge disappeared during offscreen
// measurement because var(--av-line-strong) had no report ancestor to resolve.
for (const property of ['--av-line-strong', '--author-boundary']) {
  const { document, svg } = fixture();
  const baseComputed = document.defaultView.getComputedStyle;
  document.defaultView.getComputedStyle = element => {
    const base = baseComputed(element);
    return {
      ...base,
      getPropertyValue(name) {
        const value = base.getPropertyValue(name);
        if (name !== 'stroke' || value !== `var(${property})`) return value;
        for (let owner = element; owner; owner = owner.parentElement) {
          const inherited = owner.style.getPropertyValue(property);
          if (inherited) return inherited;
        }
        return 'none'; // An unresolved stroke variable has no initial paint.
      },
    };
  };
  const boundary = append(svg, 'rect', { fill: 'none', stroke: `var(${property})`, 'stroke-width': '2' });
  boundary.getScreenCTM = () => matrix;
  boundary.getBoundingClientRect = () => rect(5, 5, 135, 115);
  const bounds = diagramBounds(svg, document, { [property]: '#445566' });
  assert(bounds[0] + bounds[2] > 135 && bounds[1] + bounds[3] > 115,
    'Theme-dependent boundaries, including author-defined roles, must remain inside the fitted scene');
  assert.equal(boundary.getAttribute('stroke'), `var(${property})`, 'Measurement preserves the authored theme reference');
  assert.equal(document.querySelectorAll('[data-av-mermaid-staging]').length, 0);
}

console.log('Mermaid bounds contract passed: clipped/transparent text stays excluded, visible HTML overflow and theme-dependent boundaries remain inside the scene.');
