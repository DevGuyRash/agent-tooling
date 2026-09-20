/* Independent assertions over values, omission boundaries and observable markup. */
const assert = require('node:assert/strict');
const path = require('node:path');
const V = require(path.join(process.argv[2], 'src/index.js'));
const core = require(path.join(process.argv[2], 'src/core.js'));
const { renderDemo } = require(path.join(process.argv[2], 'examples/demo.js'));

let checks = 0;
function check(name, test) { try { test(); checks++; } catch (error) { error.message = `${name}: ${error.message}`; throw error; } }
function plotMarkup(html) { return html.match(/<svg\b[^>]*\bdata-av-zoom-target\b[^>]*>[\s\S]*?<\/svg>/)[0]; }
const attrs = markup => Object.fromEntries([...markup.matchAll(/([\w:-]+)="([^"]*)"/g)].map(match => [match[1], match[2]]));
const decode = value => value.replace(/&(?:amp|lt|gt|quot|#39);/g, entity => ({ '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" })[entity]);
const visibleText = markup => decode(markup.replace(/<title\b[^>]*>[\s\S]*?<\/title>/g, '').replace(/<[^>]*>/g, ''));
const svgLayers = html => [...html.matchAll(/<svg\b([^>]*)>[\s\S]*?<\/svg>/g)].map(match => ({ markup: match[0], attrs: attrs(match[1]) }));
function groups(markup) {
  const stack = [], result = [];
  for (const match of markup.matchAll(/<g\b([^>]*)>|<\/g>/g)) {
    if (!match[0].startsWith('</')) stack.push({ attrs: attrs(match[1]), start: match.index, bodyStart: match.index + match[0].length });
    else { const group = stack.pop(); assert(group, 'Unbalanced SVG group'); result.push({ attrs: group.attrs, body: markup.slice(group.bodyStart, match.index), start: group.start }); }
  }
  assert.equal(stack.length, 0); return result.sort((a, b) => a.start - b.start);
}
const near = (actual, expected, message) => assert(Math.abs(actual - expected) <= 1e-7, message || `${actual} differs from ${expected}`);
function pairs(value) { const numbers = value.trim().split(/[ ,]+/).map(Number); assert.equal(numbers.length % 2, 0); assert(numbers.every(Number.isFinite)); return Array.from({ length: numbers.length / 2 }, (_, i) => [numbers[i * 2], numbers[i * 2 + 1]]); }
function linearPath(value) {
  assert(/^\s*M(?:[\d.,+\-eE\s]|[ML])+$/u.test(value), 'Expected the emitted orthogonal M/L route or linear marker');
  return pairs(value.replace(/[ML]/g, ' '));
}
function shapeBounds(tag, value) {
  const a = attrs(value), n = key => { const number = Number(a[key]); assert(Number.isFinite(number), `Nonfinite ${key}`); return number; };
  let points;
  if (tag === 'circle') points = [[n('cx') - n('r'), n('cy') - n('r')], [n('cx') + n('r'), n('cy') + n('r')]];
  else if (tag === 'rect') points = [[n('x'), n('y')], [n('x') + n('width'), n('y') + n('height')]];
  else if (tag === 'line') points = [[n('x1'), n('y1')], [n('x2'), n('y2')]];
  else if (tag === 'polygon' || tag === 'polyline') points = pairs(a.points);
  else if (tag === 'path' && /^\s*M(?:[\d.,+\-eE\s]|[ML])+$/u.test(a.d || '')) points = linearPath(a.d);
  else return null;
  if (!points.length) return null;
  return { left: Math.min(...points.map(p => p[0])), right: Math.max(...points.map(p => p[0])), top: Math.min(...points.map(p => p[1])), bottom: Math.max(...points.map(p => p[1])) };
}
function markerIn(markup) {
  const match = markup.match(/<(circle|rect|polygon|path)\b([^>]*)><title>[\s\S]*?<\/title><\/\1>/);
  assert(match, 'An observation needs a visible geometric marker with its supplied title');
  const bounds = shapeBounds(match[1], match[2]); assert(bounds);
  assert(bounds.right > bounds.left && bounds.bottom > bounds.top, 'A visible observation cannot have a zero-size marker');
  return { tag: match[1], attrs: attrs(match[2]), bounds, x: (bounds.left + bounds.right) / 2 };
}
const observationMarks = html => groups(plotMarkup(html)).filter(group => group.attrs['data-av-observation'] !== undefined).map(group => ({ ...group, marker: markerIn(group.body) }));
function geometry(html) {
  assert(!/(?:NaN|Infinity)/.test(html), 'nonfinite geometry');
  for (const layer of svgLayers(html)) {
    if (!layer.attrs.viewBox) continue;
    const [left, top, width, height] = layer.attrs.viewBox.split(/\s+/).map(Number);
    assert([left, top, width, height].every(Number.isFinite) && width > 0 && height > 0);
    for (const match of layer.markup.matchAll(/<(circle|rect|line|polygon|polyline|path)\b([^>]*?)(?:\/>|>)/g)) {
      const bounds = shapeBounds(match[1], match[2]); if (!bounds) continue;
      const a = attrs(match[2]), stroke = a.style?.match(/(?:^|;)stroke-width:([\d.]+)/)?.[1] ?? a['stroke-width'];
      const margin = stroke === undefined ? 0 : Number(stroke) / 2;
      assert(bounds.left - margin >= left - 1e-7 && bounds.right + margin <= left + width + 1e-7 && bounds.top - margin >= top - 1e-7 && bounds.bottom + margin <= top + height + 1e-7, `Clipped ${match[1]} bounds ${JSON.stringify(bounds)} in ${layer.attrs.viewBox}`);
    }
    for (const match of layer.markup.matchAll(/\b(?:cx|cy|x1|x2|y1|y2)="([^"]+)"/g)) assert(Number.isFinite(Number(match[1])), match[0]);
  }
}
function tableCells(html) {
  const table = html.match(/<table>([\s\S]*?)<\/table>/)[1];
  return [...table.matchAll(/<tr>([\s\S]*?)<\/tr>/g)].map(row => [...row[1].matchAll(/<t[hd]\b[^>]*>([\s\S]*?)<\/t[hd]>/g)].map(cell => cell[1]));
}
function suppliedId(html) {
  const identity = html.match(/<code class="av-id">([^<]*)<\/code>/);
  assert(identity, `Missing visible identity: ${html}`);
  return identity[1];
}
function attributedMatrix(html) {
  const [headers, ...rows] = tableCells(html), dimensions = headers.slice(1).map(suppliedId);
  return rows.flatMap(row => dimensions.map((dimension, i) => [JSON.stringify([suppliedId(row[0]), dimension]), row[i + 1]])).sort(([left], [right]) => left.localeCompare(right));
}
const repeatedMatrix = {
  title: 'Versions and operating systems',
  alternatives: [{ id: 'release-2024', label: 'Fieldbook', note: 'Earlier release scope' }, { id: 'release-2026', label: 'Fieldbook', note: 'Later release scope' }],
  dimensions: [{ id: 'offline-android', label: 'Offline capture', note: 'Android source context', evidence: [{ label: 'Android native evidence' }] }, { id: 'offline-ios', label: 'Offline capture', note: 'iOS source context', evidence: [{ label: 'iOS native evidence' }] }],
  findings: [
    { alternative: 'release-2024', dimension: 'offline-android', value: 0, status: 'supported', note: 'No observed loss' },
    { alternative: 'release-2024', dimension: 'offline-ios', value: 2, status: 'failed', note: 'Two notes lost' },
    { alternative: 'release-2026', dimension: 'offline-android', value: null, status: 'missing', note: 'Run not retained' },
  ],
};
function reassignMatrix(input, field, references) {
  const copy = structuredClone(input), ids = copy[field].map(item => item.id);
  copy[field].forEach((item, i) => { item.id = ids[ids.length - i - 1]; });
  copy.findings.forEach(finding => { finding[references] = ids[ids.length - ids.indexOf(finding[references]) - 1]; });
  return copy;
}

check('real demo renders each presentation with offline native interactions', () => {
  const html = renderDemo();
  assert(html.includes('synthetic demonstration inputs'));
  assert(html.includes('<svg'));
  assert(/<details\b[^>]*data-av-object="scenario-\d+"[^>]*>[\s\S]*?<summary>/.test(html), 'native grounded scenario disclosure missing');
  assert(html.includes('tabindex="0"'));
  assert(!html.includes('<script>'));
  assert(!html.includes('onclick='));
  geometry(html);
});

check('unsafe labels and URLs cannot introduce HTML execution', () => {
  const html = V.evidenceExcerpts({ title: '<img src=x onerror=alert(1)>', items: [{ label: '</h3><script>alert(1)</script>', text: '<iframe src="https://bad.test">', evidence: [{ label: '<svg/onload=alert(1)>', href: 'javascript:alert(1)' }, { label: 'Tricky', href: 'https://safe.test/" onmouseover="alert(1)' }, { label: 'Good', href: 'https://example.com/?a=1&b=2' }] }] });
  assert(!/<(?:script|iframe|img)\b/.test(html));
  assert(!/<svg\b[^>]*\son[a-z]+=/.test(html));
  assert(html.includes('&lt;svg/onload=alert(1)&gt;'));
  assert(html.includes('&lt;/h3&gt;&lt;script&gt;alert(1)&lt;/script&gt;'));
  assert(!html.includes('href="javascript:'));
  assert(html.includes('link omitted: javascript:alert(1)'));
  assert(html.includes('href="https://example.com/?a=1&amp;b=2"'));
  assert(html.includes('&lt;iframe'));
});

check('matrix retains missingness, status, annotation, dimensions and arbitrary alternatives', () => {
  const alternatives = Array.from({ length: 103 }, (_, n) => ({ id: `a${n}`, label: `Alternative ${n}` }));
  const html = V.comparisonMatrix({ title: 'Matrix', alternatives, dimensions: [{ id: 'd', label: 'Requirement', note: 'Dimension grounds' }], findings: [{ alternative: 'a102', dimension: 'd', value: 0, status: 'failed', note: 'Failure despite zero', evidence: [{ label: 'Native record', href: '#record' }] }] });
  assert(html.includes('Alternative 102'));
  assert.equal((html.match(/Not supplied/g) || []).length, 102);
  assert(html.includes('Failure despite zero'));
  assert(html.includes('Dimension grounds'));
  assert(html.includes('href="#record"'));
  assert.throws(() => V.comparisonMatrix({ title: '', alternatives, dimensions: [{ id: 'd', label: 'D' }], findings: [{ alternative: 'absent', dimension: 'd', value: 1 }] }), /undeclared/);
  assert.throws(() => V.comparisonMatrix({ title: '', alternatives, dimensions: [{ id: 'd', label: 'D' }], findings: [{ alternative: 'a0', dimension: 'd', value: 1 }, { alternative: 'a0', dimension: 'd', value: 2 }] }), /duplicate/);
});

check('repeated matrix labels retain attributable findings and context across representations', () => {
  const equivalent = { ...repeatedMatrix, alternatives: [...repeatedMatrix.alternatives].reverse(), dimensions: [...repeatedMatrix.dimensions].reverse(), findings: [...repeatedMatrix.findings].reverse() };
  const reliability = input => V.reliabilityProfile({ ...input, conditions: input.alternatives, behaviors: input.dimensions, observations: input.findings.map(finding => ({ ...finding, condition: finding.alternative, behavior: finding.dimension })) });
  for (const render of [V.comparisonMatrix, V.coverageMatrix, V.constraintSatisfaction, reliability]) {
    const original = render(repeatedMatrix), represented = attributedMatrix(original), cells = new Map(represented);
    assert(cells.get('["release-2024","offline-android"]').includes('>supported</span>'));
    assert(cells.get('["release-2024","offline-ios"]').startsWith('2'));
    assert(cells.get('["release-2026","offline-android"]').includes('Run not retained'));
    assert(cells.get('["release-2026","offline-ios"]').includes('Not supplied'));
    assert.deepEqual(attributedMatrix(render(equivalent)), represented, 'Reordering display axes or input findings must preserve attribution');
    assert.equal(render({ ...repeatedMatrix, findings: [...repeatedMatrix.findings].reverse() }), original);
    for (const [field, reference] of [['alternatives', 'alternative'], ['dimensions', 'dimension']]) {
      const reassigned = render(reassignMatrix(repeatedMatrix, field, reference));
      assert.notEqual(reassigned, original, 'Reassigning identity must change the reader-facing evidence');
      assert.notDeepEqual(attributedMatrix(reassigned), represented, 'Attribution must follow stable IDs rather than repeated labels');
    }
    assert(original.includes('<h4>Offline capture · <code class="av-id">offline-android</code></h4><p class="av-note">Android source context</p>'));
    assert(original.includes('<h4>Offline capture · <code class="av-id">offline-ios</code></h4><p class="av-note">iOS source context</p>'));
    for (const item of [...repeatedMatrix.alternatives, ...repeatedMatrix.dimensions]) assert(original.includes(item.note));
    for (const dimension of repeatedMatrix.dimensions) assert(original.includes(dimension.evidence[0].label));
  }
  const concise = V.comparisonMatrix({ ...repeatedMatrix, alternatives: repeatedMatrix.alternatives.map(item => ({ ...item, label: item.id })), dimensions: repeatedMatrix.dimensions.map(item => ({ ...item, label: item.id })) });
  assert(!concise.includes('class="av-id"'), 'Already-distinct labels remain concise');
  const whitespace = V.comparisonMatrix({ ...repeatedMatrix, dimensions: [{ ...repeatedMatrix.dimensions[0], label: 'Offline  capture' }, { ...repeatedMatrix.dimensions[1], label: '\nOffline\tcapture ' }] });
  assert.deepEqual(attributedMatrix(whitespace), attributedMatrix(V.comparisonMatrix(repeatedMatrix)), 'Collapsed label whitespace must not remove visible identities');
});

check('heatmap retains row and column identity with exact numeric findings and annotations', () => {
  const heatInput = input => ({ ...input, rows: input.alternatives, columns: input.dimensions, cells: input.findings.map(finding => ({ ...finding, row: finding.alternative, column: finding.dimension })) });
  const original = V.heatmap(heatInput(repeatedMatrix)), represented = attributedMatrix(original);
  assert.deepEqual(attributedMatrix(V.heatmap(heatInput({ ...repeatedMatrix, alternatives: [...repeatedMatrix.alternatives].reverse(), dimensions: [...repeatedMatrix.dimensions].reverse(), findings: [...repeatedMatrix.findings].reverse() }))), represented);
  for (const [field, reference] of [['alternatives', 'alternative'], ['dimensions', 'dimension']]) assert.notDeepEqual(attributedMatrix(V.heatmap(heatInput(reassignMatrix(repeatedMatrix, field, reference)))), represented);
  assert(new Map(represented).get('["release-2024","offline-android"]').includes('>0<span'));
  assert(new Map(represented).get('["release-2026","offline-android"]').includes('Missing'));
  assert(original.includes('<h3>Offline capture · <code class="av-id">offline-android</code></h3><p class="av-note">Android source context</p>'));
  assert(original.includes('iOS native evidence'));
});

check('unknowns retain alternative identity for supplied and absent relationships', () => {
  const input = { title: 'Unknowns', alternatives: repeatedMatrix.alternatives, issues: [{ label: 'Recovery', relevance: 'Changes rollout', note: 'Question scope', affected: [{ alternative: 'release-2024', consequence: 'Inspect export recovery', note: 'Relationship scope', evidence: [{ label: 'Recovery evidence' }] }] }] };
  const relationships = html => { const [headers, row] = tableCells(html); return headers.slice(2).map((header, i) => [suppliedId(header), row[i + 2]]).sort(([left], [right]) => left.localeCompare(right)); };
  const original = V.unknownsMap(input), represented = relationships(original), cells = new Map(represented);
  assert(cells.get('release-2024').includes('Inspect export recovery'));
  assert(cells.get('release-2024').includes('Relationship scope'));
  assert(cells.get('release-2024').includes('Recovery evidence'));
  assert(cells.get('release-2026').includes('No relationship supplied'));
  assert.deepEqual(relationships(V.unknownsMap({ ...input, alternatives: [...input.alternatives].reverse() })), represented);
  const reassigned = structuredClone(input);
  reassigned.alternatives.reverse();
  reassigned.issues[0].affected[0].alternative = 'release-2026';
  assert.notEqual(V.unknownsMap(reassigned), original);
  assert.notDeepEqual(relationships(V.unknownsMap(reassigned)), represented);
  assert(original.includes('<h3>Fieldbook · <code class="av-id">release-2024</code></h3><p class="av-note">Earlier release scope</p>'));
  assert(original.includes('<h3>Fieldbook · <code class="av-id">release-2026</code></h3><p class="av-note">Later release scope</p>'));
  assert(original.includes('Question scope'));
});

check('finite extremes, constant domains, subnormal and signed zero values remain faithful', () => {
  for (const values of [[-1e308, 0, 1e308], [Number.MAX_VALUE, Number.MAX_VALUE], [0, 0], [Number.MIN_VALUE, Number.MIN_VALUE * 2]]) {
    const html = V.distribution({ title: 'Extreme values', axis: 'Value', unit: 'units', groups: [{ label: 'G', observations: values.map((value, i) => ({ label: `O${i}`, value })) }] });
    geometry(html);
    const marks = observationMarks(html);
    assert.equal(marks.length, values.length, 'Every supplied number needs its own marker regardless of category shape');
    assert.deepEqual(marks.map(mark => decode(mark.attrs['data-av-value'])), values.map(String));
    const [headers, ...rows] = tableCells(html), column = headers.map(visibleText).indexOf('Value (units)');
    assert(column >= 0);
    assert.deepEqual(rows.map(row => visibleText(row[column])), values.map(String), 'Exact numbers must be in the native table, not just metadata');
  }
  assert.equal(core.numericText(-0), '-0');
  const s = core.scale([-1e308, 0, 1e308], 100, 800);
  assert.equal(s.map(-1e308), 100); assert.equal(s.map(0), 450); assert.equal(s.map(1e308), 800);
});

check('close finite values keep their actual relative distances and distinguishable ticks', () => {
  const cases = [
    { values: [0.1, 0.10000000000000002, 0.10000000000000005], fraction: 1 / 3, center: 405 },
    { values: [0.3, 0.30000000000000004, 0.3000000000000001], fraction: 1 / 2, center: 515 },
    { values: [-0.3000000000000001, -0.30000000000000004, -0.3], fraction: 1 / 2, center: 515 },
  ];
  for (const { values, fraction, center } of cases) {
    assert.equal((values[1] - values[0]) / (values[2] - values[0]), fraction);
    const domain = core.scale(values, 185, 845);
    assert.equal(domain.map(values[1]), center);
    assert.equal(new Set(domain.ticks).size, domain.ticks.length);
    assert.equal(new Set(domain.tickLabels).size, domain.ticks.length);
    assert.equal(domain.offset, values[0]);
    const html = V.distribution({ title: 'Narrow domain', axis: 'Value', groups: [{ label: 'G', observations: values.map((value, i) => ({ label: `${i}`, value })) }] });
    const marks = observationMarks(html), xs = marks.map(mark => mark.marker.x);
    assert.equal(xs.length, values.length); assert(xs[2] > xs[0]);
    near((xs[1] - xs[0]) / (xs[2] - xs[0]), fraction, 'Rendered category markers must retain the original domain ratio');
    for (const mark of marks) near(mark.marker.x, Number(mark.attrs['data-av-x']), 'Marker geometry must agree with its retained coordinate');
    const axis = svgLayers(html).find(layer => layer.attrs['data-av-axis-layer'] === 'x'); assert(axis, 'A row plot needs a separate scale layer');
    assert(visibleText(axis.markup).includes(`Add ${values[0]} to tick labels`));
    for (const label of domain.tickLabels) assert([...axis.markup.matchAll(/<text\b[^>]*>[\s\S]*?<\/text>/g)].some(match => visibleText(match[0]) === label));
    const heat = V.heatmap({ title: 'Same numeric domain', rows: [{ id: 'r', label: 'R' }], columns: values.map((_, i) => ({ id: `${i}`, label: `${i}` })), cells: values.map((value, i) => ({ row: 'r', column: `${i}`, value })) });
    const magnitudes = [...heat.matchAll(/data-av-magnitude="([^"]+)"/g)].map(m => Number(m[1]));
    assert.equal(magnitudes.length, 3); assert.equal(magnitudes[0], 0); assert.equal(magnitudes[2], 100);
    near(magnitudes[1] / 100, fraction, 'Theme-independent magnitude must retain the original numeric ratio');
    geometry(html);
  }
  for (const values of [[-Number.MAX_VALUE, 0, Number.MAX_VALUE], [0, Number.MIN_VALUE, Number.MIN_VALUE * 2]]) {
    const domain = core.scale(values, 0, 1);
    assert.equal(domain.map(values[0]), 0); assert.equal(domain.map(values[1]), .5); assert.equal(domain.map(values[2]), 1);
    assert(domain.ticks.every(Number.isFinite));
    assert.equal(new Set(domain.tickLabels).size, domain.ticks.length);
  }
});

check('graph tables preserve stable IDs when labels repeat, including argument maps', () => {
  const nodes = [{ id: 'prior', label: 'Output', kind: 'observation', detail: 'Earlier run' }, { id: 'later', label: 'Output', kind: 'observation', detail: 'Later run' }, { id: 'claim', label: 'Claim', kind: 'claim' }];
  for (const renderer of [V.evidenceLineage, V.argumentMap]) {
    const first = renderer({ title: 'Identities', nodes, edges: [{ from: 'prior', to: 'claim', relation: 'supports' }] });
    const second = renderer({ title: 'Identities', nodes, edges: [{ from: 'later', to: 'claim', relation: 'supports' }] });
    const relations = html => html.match(/<caption\b[^>]*>Evidence and version relationships<\/caption>[\s\S]*?<\/table>/)[0];
    assert.notEqual(relations(first), relations(second));
    assert(relations(first).includes('<code class="av-id">prior</code>'));
    assert(relations(second).includes('<code class="av-id">later</code>'));
    assert(relations(first).includes('<code class="av-id">claim</code>'));
    assert(first.includes('<th scope="col">Node ID</th>'));
  }
  const points = [{ id: 'first', label: 'Output', x: 1, y: 1 }, { id: 'second', label: 'Output', x: 2, y: 2 }, { id: 'target', label: 'Target', x: 3, y: 3 }];
  const scatter = from => V.scatterPlot({ title: 'Points', xAxis: 'X', yAxis: 'Y', points, frontiers: [{ label: 'Path', pointIds: [from, 'target'] }] });
  const connection = html => html.match(/<caption\b[^>]*>Supplied frontier connections<\/caption>[\s\S]*?<\/table>/)[0];
  assert.notEqual(connection(scatter('first')), connection(scatter('second')));
  assert(connection(scatter('first')).includes('<li><code class="av-id">first</code> — Output</li>'));
  assert(scatter('first').includes('<th scope="col">Point ID</th>'));
});

check('emitted graph routes retain attachment, obstacles, direction and every relationship occurrence', () => {
  const epsilon = 1e-7;
  const inside = (point, rect) => point[0] > rect.left + epsilon && point[0] < rect.right - epsilon && point[1] > rect.top + epsilon && point[1] < rect.bottom - epsilon;
  const boundary = (point, rect) => point[0] >= rect.left - epsilon && point[0] <= rect.right + epsilon && point[1] >= rect.top - epsilon && point[1] <= rect.bottom + epsilon && [point[0] - rect.left, point[0] - rect.right, point[1] - rect.top, point[1] - rect.bottom].some(delta => Math.abs(delta) <= epsilon);
  const overlaps = (a, b) => a.left < b.right - epsilon && a.right > b.left + epsilon && a.top < b.bottom - epsilon && a.bottom > b.top + epsilon;
  function segmentsOf(d) {
    const token = /[MLC]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/g;
    assert(!d.replace(token, '').replace(/[\s,]/g, ''), 'Unsupported path syntax must be inspected rather than silently ignored');
    const tokens = d.match(token), segments = []; let index = 0, point;
    const pair = () => { const value = [Number(tokens[index++]), Number(tokens[index++])]; assert(value.every(Number.isFinite)); return value; };
    while (index < tokens.length) {
      const command = tokens[index++];
      if (command === 'M') { assert(!point, 'A relationship route must be one connected path'); point = pair(); }
      else if (command === 'L') { assert(point); const next = pair(); segments.push([point, next]); point = next; }
      else if (command === 'C') { assert(point); const first = pair(), second = pair(), next = pair(); segments.push([point, first, second, next]); point = next; }
      else assert.fail('Unexpected path command');
    }
    assert(segments.length, 'A relationship needs a visible route'); return segments;
  }
  function lineHits([a, b], rect) {
    let enter = 0, leave = 1;
    for (const [axis, low, high] of [[0, rect.left + epsilon, rect.right - epsilon], [1, rect.top + epsilon, rect.bottom - epsilon]]) {
      const delta = b[axis] - a[axis];
      if (!delta) { if (a[axis] <= low || a[axis] >= high) return false; continue; }
      const first = (low - a[axis]) / delta, second = (high - a[axis]) / delta;
      enter = Math.max(enter, Math.min(first, second)); leave = Math.min(leave, Math.max(first, second));
    }
    return leave > enter && leave > 0 && enter < 1;
  }
  function routeHits(segment, rect, depth = 0) {
    if (segment.length === 2) return lineHits(segment, rect);
    const hull = { left: Math.min(...segment.map(point => point[0])), right: Math.max(...segment.map(point => point[0])), top: Math.min(...segment.map(point => point[1])), bottom: Math.max(...segment.map(point => point[1])) };
    if (!overlaps(hull, rect)) return false;
    if (segment.some(point => inside(point, rect)) && segment.every(point => inside(point, rect))) return true;
    if (depth === 18) return lineHits([segment[0], segment[3]], rect);
    const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    const a = mid(segment[0], segment[1]), b = mid(segment[1], segment[2]), c = mid(segment[2], segment[3]), d = mid(a, b), e = mid(b, c), f = mid(d, e);
    return routeHits([segment[0], a, d, f], rect, depth + 1) || routeHits([f, e, c, segment[3]], rect, depth + 1);
  }
  function inspect(input) {
    const html = V.evidenceLineage(input), plot = plotMarkup(html), rendered = groups(plot);
    const nodeGroups = rendered.filter(group => (group.attrs.class || '').split(' ').includes('av-graph-node'));
    const edgeGroups = rendered.filter(group => (group.attrs.class || '').split(' ').includes('av-graph-edge'));
    assert.equal(nodeGroups.length, input.nodes.length); assert.equal(edgeGroups.length, input.edges.length);
    const rectangles = new Map(nodeGroups.map(group => [group.attrs['data-av-inspect'], shapeBounds('rect', group.body.match(/<rect\b([^>]*)/)[1])]));
    const identities = new Map(nodeGroups.map(group => [decode(group.attrs['data-av-node-id']), group.attrs['data-av-inspect']]));
    for (const node of input.nodes) {
      const group = nodeGroups.find(group => decode(group.attrs['data-av-node-id']) === node.id); assert(group);
      for (const value of [node.label, node.id, node.kind]) assert(visibleText(group.body).includes(value.replace(/\r\n|\r|\n/g, '')), 'Full graph text must be visible, not only in hover titles');
    }
    const labels = edgeGroups.map(group => shapeBounds('rect', group.body.match(/<rect\b([^>]*)/)[1]));
    const boxes = [...rectangles.values(), ...labels];
    for (let i = 0; i < boxes.length; i++) for (const other of boxes.slice(i + 1)) assert(!overlaps(boxes[i], other), 'Graph node/relationship boxes overlap');
    const routes = [];
    for (let i = 0; i < edgeGroups.length; i++) {
      const group = edgeGroups[i], original = input.edges[i], identity = decode(group.attrs['data-av-edge-id']);
      if (original.id !== undefined) assert.equal(identity, original.id);
      assert.equal(group.attrs['data-av-from'], identities.get(original.from)); assert.equal(group.attrs['data-av-to'], identities.get(original.to));
      assert(visibleText(group.body).includes(original.relation));
      const path = [...group.body.matchAll(/<path\b([^>]*)/g)].map(match => attrs(match[1])).find(path => path.class?.split(' ').includes('av-edge-route'));
      assert(path, 'A transparent hit target cannot replace the visible relationship');
      const segments = segmentsOf(path.d); routes.push(path.d);
      const first = segments[0][0], last = segments.at(-1).at(-1), source = rectangles.get(group.attrs['data-av-from']), target = rectangles.get(group.attrs['data-av-to']);
      assert(boundary(first, source)); assert(boundary(last, target));
      for (const segment of segments) {
        for (const rectangle of rectangles.values()) assert(!routeHits(segment, rectangle), 'A route enters a node interior');
        for (let j = 0; j < labels.length; j++) if (j !== i) assert(!routeHits(segment, labels[j]), 'A route enters an unrelated relationship label');
      }
      const arrow = pairs(attrs(group.body.match(/<polygon\b([^>]*)/)[1]).points); assert.equal(arrow.length, 3);
      near(arrow[0][0], last[0]); near(arrow[0][1], last[1]);
      const prior = segments.at(-1).at(-2), tangent = [last[0] - prior[0], last[1] - prior[1]], head = [last[0] - (arrow[1][0] + arrow[2][0]) / 2, last[1] - (arrow[1][1] + arrow[2][1]) / 2];
      assert(tangent[0] * head[0] + tangent[1] * head[1] > 0, 'Arrow opposes supplied direction');
      near(tangent[0] * head[1] - tangent[1] * head[0], 0, 'Arrow must follow the actual final path tangent');
      assert(!inside(arrow[1], target) && !inside(arrow[2], target), 'Arrowhead base enters the target');
      assert(html.includes(`data-av-object="${group.attrs['data-av-inspect']}"`), 'Each relationship needs a native inspector');
    }
    assert.equal(new Set(routes).size, input.edges.length, 'Repeated relations need distinct complete routes');
    const relationTable = html.match(/<table><caption\b[^>]*>Evidence and version relationships<\/caption>[\s\S]*?<\/table>/)[0];
    const [, ...rows] = tableCells(relationTable); assert.equal(rows.length, input.edges.length);
    assert.equal(new Set(rows.map(row => suppliedId(row[0]))).size, input.edges.length);
    rows.forEach((row, i) => { assert.equal(suppliedId(row[1]), input.edges[i].from); assert.equal(visibleText(row[3]), input.edges[i].relation); assert.equal(suppliedId(row[4]), input.edges[i].to); if (input.edges[i].note) assert(row[6].includes(input.edges[i].note)); });
    geometry(html);
  }
  const nodes = ['first', 'second', 'third', 'fourth', 'fifth'].map(id => ({ id, label: 'Repeated visible node label', kind: 'claim' }));
  const edges = [[0, 1], [1, 0], [0, 2], [2, 0], [0, 3], [3, 0], [0, 0], [1, 1], [0, 1], [0, 0], [0, 4]].map(([from, to], i) => ({ id: `relation-${i}`, from: nodes[from].id, to: nodes[to].id, relation: `Relationship ${i} retains its complete supplied condition`, note: `Native grounds ${i}` }));
  for (const width of [420, 1120, 1600]) inspect({ title: 'Directed relationships', nodes, edges, context: { width } });
  inspect({ title: 'Single nonadjacent edge', nodes, edges: [{ from: 'first', to: 'fifth', relation: 'supports only the declared target' }] });
  inspect({ title: 'Unicode identities', nodes: [{ id: 'same-prefix-'.repeat(5) + 'A', label: '条件 👨‍👩‍👧‍👦 e\u0301 ' + 'W'.repeat(42), kind: 'original observation' }], edges: [{ from: 'same-prefix-'.repeat(5) + 'A', to: 'same-prefix-'.repeat(5) + 'A', relation: 'Revises only this retained claim 👨‍👩‍👧‍👦', note: 'Retained loop grounds' }] });
});

check('intervals never fabricate estimates and retain incomplete bounds', () => {
  const html = V.intervalPlot({ title: 'Bounds', axis: 'Value', intervalLabel: 'Observed range', items: [{ label: 'Range only', low: -2, high: 5, note: 'No estimate' }, { label: 'Known estimate', estimate: 0 }, { label: 'Upper only', high: 9 }, { label: 'Missing' }] });
  assert.equal((html.match(/<circle /g) || []).length, 1);
  assert(html.includes('No estimate'));
  assert(html.includes('Upper only'));
  assert(html.includes('Missing'));
  geometry(html);
  assert.throws(() => V.intervalPlot({ title: '', axis: '', intervalLabel: 'Range', items: [{ label: 'Bad', low: 2, high: 1 }] }), /Lower/);
});

check('larger data sets grow the SVG rather than clipping later rows', () => {
  const html = V.intervalPlot({ title: 'Large', axis: 'Value', intervalLabel: 'Bounds', items: Array.from({ length: 140 }, (_, n) => ({ label: `Item ${n}`, low: n - 120, high: n + 100 })) });
  const height = Number(plotMarkup(html).match(/<svg[^>]+height="(\d+)"/)[1]);
  const ys = [...html.matchAll(/\by1="([^"]+)"/g)].map(m => Number(m[1]));
  assert(Math.max(...ys) < height);
  assert(html.includes('Item 139'));
  const layers = svgLayers(html), axis = layers.find(layer => layer.attrs['data-av-axis-layer'] === 'x'), rows = layers.find(layer => layer.attrs['data-av-axis-layer'] === 'rows');
  assert(axis && rows, 'Rows and scale must remain separate from the tall data canvas');
  assert.equal(Number(rows.attrs.height), height);
  assert(Number(axis.attrs.height) < height / 10, 'The scale must not be placed below all observations');
  assert(visibleText(axis.markup).includes('Value')); assert(visibleText(rows.markup).includes('Item 139'));
  geometry(html);
});

check('invalid numbers fail clearly rather than becoming misleading graphics', () => {
  for (const bad of [NaN, Infinity, -Infinity, '2']) {
    assert.throws(() => V.distribution({ title: '', axis: '', groups: [{ label: '', observations: [{ label: '', value: bad }] }] }), /finite/);
    assert.throws(() => V.scatterPlot({ title: '', xAxis: '', yAxis: '', points: [{ id: 'a', label: '', x: bad, y: 1 }] }), /finite/);
  }
  assert.throws(() => V.annotatedTable({ title: '', columns: ['X'], rows: [[{ value: Infinity }]] }), /finite/);
});

check('missing trajectory values break connections; supplied order remains explicit', () => {
  const html = V.trajectory({ title: 'Gaps', xAxis: 'Round', yAxis: 'Value', series: [{ label: 'A', points: [{ label: '1', x: 1, y: 2 }, { label: '2', x: 2, y: null, note: 'Interrupted run' }, { label: '3', x: 3, y: 4 }, { label: '4', x: 4, y: 5 }] }] });
  assert.equal((html.match(/<polyline /g) || []).length, 1);
  const points = html.match(/<polyline [^>]* points="([^"]+)"/)[1].split(' ');
  assert.equal(points.length, 2);
  assert(html.includes('Interrupted run'));
  assert.throws(() => V.trajectory({ title: '', xAxis: '', yAxis: '', series: [{ label: '', points: [{ label: '', x: 2, y: 1 }, { label: '', x: 1, y: 1 }] }] }), /nondecreasing/);
});

check('repeated series and group names preserve different grouping in their native tables', () => {
  const points = [1, 2, 3, 4].map(value => ({ label: 'Repeated observation', x: value, y: value }));
  const trajectory = cut => V.trajectory({ title: 'Grouping', xAxis: 'Round', yAxis: 'Value', series: [{ label: 'Run', points: points.slice(0, cut) }, { label: 'Run', points: points.slice(cut) }] });
  const distribution = cut => V.distribution({ title: 'Grouping', axis: 'Value', groups: [{ label: 'Run', observations: points.slice(0, cut).map(point => ({ label: point.label, value: point.y })) }, { label: 'Run', observations: points.slice(cut).map(point => ({ label: point.label, value: point.y })) }] });
  for (const render of [trajectory, distribution]) {
    const first = render(2), second = render(1), firstRows = tableCells(first).slice(1), secondRows = tableCells(second).slice(1);
    assert.equal(firstRows.length, 4); assert.equal(secondRows.length, 4);
    const a = firstRows.map(row => suppliedId(row[0])), b = secondRows.map(row => suppliedId(row[0]));
    assert.equal(a[0], a[1]); assert.equal(a[2], a[3]); assert.notEqual(a[0], a[2]);
    assert.equal(b[1], b[2]); assert.equal(b[2], b[3]); assert.notEqual(b[0], b[1]);
    assert.notDeepEqual(firstRows, secondRows, 'The accessible alternative must expose the changed boundary');
  }
  assert.equal((plotMarkup(trajectory(2)).match(/<polyline /g) || []).length, 2);
  assert.equal((plotMarkup(trajectory(1)).match(/<polyline /g) || []).length, 1);
  const explicit = [{ id: 'one', label: 'Same', points: points.slice(0, 2) }, { id: 'two', label: 'Same', points: points.slice(2) }];
  const mapping = html => tableCells(html).slice(1).map(row => [suppliedId(row[0]), ...row.slice(2).map(visibleText)]).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
  const render = series => V.trajectory({ title: 'Attributed', xAxis: 'X', yAxis: 'Y', series });
  assert.deepEqual(mapping(render(explicit)), mapping(render([...explicit].reverse())));
  const collision = V.distribution({ title: 'Occurrence collision', axis: 'Value', groups: [{ label: 'Same', observations: [{ label: 'A', value: 1 }] }, { id: 'Group 1', label: 'Same', observations: [{ label: 'B', value: 2 }] }] });
  assert.equal(new Set(tableCells(collision).slice(1).map(row => suppliedId(row[0]))).size, 2);
});

check('category appearance follows identity and remains distinguishable without color', () => {
  function fingerprint(group, withColor = true) {
    const marker = markerIn(group.body), a = marker.attrs, centerY = (marker.bounds.top + marker.bounds.bottom) / 2;
    const normalized = marker.tag === 'circle' ? [Number(a.r)] : marker.tag === 'rect' ? [Number(a.width), Number(a.height)]
      : (marker.tag === 'path' ? linearPath(a.d) : pairs(a.points)).map(([x, y]) => [x - marker.x, y - centerY]);
    const code = [...group.body.matchAll(/<text\b[^>]*class="av-category-code"[^>]*>[\s\S]*?<\/text>/g)].map(match => visibleText(match[0])).join('');
    return JSON.stringify([marker.tag, normalized, code, ...(withColor ? [a.fill, a.stroke] : [])]);
  }
  const definitions = Array.from({ length: 8 }, (_, i) => ({ id: `category-${i}`, label: `Category ${i}`, style: { color: 1 } }));
  const context = V.createChartContext({ categories: definitions });
  const groupData = definitions.map((item, i) => ({ id: item.id, label: item.label, observations: [{ label: 'Observation', value: i }] }));
  const distribution = groups => V.distribution({ title: 'Categories', axis: 'Value', context, groups });
  const styles = html => new Map(groups(plotMarkup(html)).filter(group => group.attrs['data-av-observation'] !== undefined).map(group => [decode(group.attrs['data-av-category-id']), fingerprint(group)]));
  const original = styles(distribution(groupData)), reordered = styles(distribution([...groupData].reverse()));
  assert.deepEqual([...original].sort(), [...reordered].sort(), 'Harmless reordering cannot recolor or reshape an identity');
  const scope = styles(distribution([groupData[1], groupData[7]]));
  for (const [id, appearance] of scope) assert.equal(appearance, original.get(id), 'A shared context preserves appearance across narrower views');
  const rendered = distribution(groupData), marks = groups(plotMarkup(rendered)).filter(group => group.attrs['data-av-observation'] !== undefined);
  assert.equal(new Set(marks.map(group => fingerprint(group, false))).size, 8, 'Shape plus visible code must distinguish more than six monochrome categories');
  for (const group of marks) {
    const code = group.body.match(/<text\b[^>]*class="av-category-code"[^>]*>([\s\S]*?)<\/text>/)?.[1];
    if (code) {
      const item = [...rendered.matchAll(/<li\b([^>]*)>([\s\S]*?)<\/li>/g)].find(match => attrs(match[1])['data-av-category-id'] === group.attrs['data-av-category-id']);
      assert(item && visibleText(item[2]).includes(visibleText(code) + ' · '), 'A repeated-shape code needs a visible legend mapping');
    }
  }
  const forced = V.createChartContext({ categories: definitions.slice(0, 2).map(item => ({ ...item, style: { color: 1, shape: 'circle', dash: '' } })) });
  const forcedPlot = V.distribution({ title: 'Custom monochrome', axis: 'Value', context: forced, groups: groupData.slice(0, 2) });
  const forcedMarks = groups(plotMarkup(forcedPlot)).filter(group => group.attrs['data-av-observation'] !== undefined);
  assert.equal(new Set(forcedMarks.map(group => fingerprint(group, false))).size, 2, 'Identical explicit shapes need distinct visible identity codes');
  const scatterPoints = definitions.slice(0, 3).map((item, i) => ({ id: `point-${i}`, label: 'Repeated', groupId: item.id, group: item.label, x: i, y: 3 - i }));
  const scatterStyles = points => groups(plotMarkup(V.scatterPlot({ title: 'Scatter identities', xAxis: 'X', yAxis: 'Y', context, points }))).filter(group => group.attrs['data-av-category-id']).map(group => [group.attrs['data-av-category-id'], fingerprint(group)]).sort();
  assert.deepEqual(scatterStyles(scatterPoints), scatterStyles([...scatterPoints].reverse()));
  const series = definitions.slice(0, 3).map((item, i) => ({ id: item.id, label: 'Repeated', points: [{ label: 'First', x: 1, y: i }, { label: 'Second', x: 2, y: i + 1 }] }));
  const trajectoryStyles = items => {
    const html = V.trajectory({ title: 'Series identities', xAxis: 'X', yAxis: 'Y', context, series: items });
    return [...plotMarkup(html).matchAll(/<polyline\b([^>]*)/g)].map(match => { const a = attrs(match[1]); return [a['data-av-category-id'], a.stroke, a['stroke-dasharray'] || '']; }).sort();
  };
  assert.deepEqual(trajectoryStyles(series), trajectoryStyles([...series].reverse()));
  geometry(rendered); geometry(forcedPlot);
});

check('partial-coordinate bands retain known values without inventing coordinate pairs', () => {
  const points = [{ id: 'one', label: 'A', x: 1, y: 1 }, { id: 'two', label: 'B', x: 2, y: 2 }, { id: 'partial-x', label: 'X only', x: 1e9, y: null, note: 'Y was not observed' }, { id: 'partial-y', label: 'Y only', x: null, y: -9, note: 'X was not observed' }, { id: 'absent', label: 'Neither', x: null, y: null, note: 'No coordinates retained' }];
  const render = extra => V.scatterPlot({ title: 'Partial coordinates', xAxis: 'X', yAxis: 'Y', points, ...extra });
  const html = render(), cloud = plotMarkup(html), cloudPoints = groups(cloud).filter(group => group.attrs.class === 'av-terrain-point');
  assert.equal(cloudPoints.length, 2); assert(!cloud.includes('data-av-inspect="point-2"')); assert(!cloud.includes('data-av-inspect="point-3"')); assert(!cloud.includes('data-av-inspect="point-4"'));
  const x = cloudPoints.map(group => markerIn(group.body).x); assert(x[1] - x[0] < .01, 'Known partial x must still affect the declared default domain');
  const bands = [...html.matchAll(/<section class="av-missing-coordinate-band">([\s\S]*?)<\/section>/g)].map(match => match[1]);
  assert.equal(bands.length, 2);
  const partialMarks = bands.flatMap(band => groups(band).filter(group => group.attrs['data-av-partial-coordinate']));
  assert.equal(partialMarks.length, 2);
  assert.deepEqual(partialMarks.map(group => [group.attrs['data-av-inspect'], group.attrs['data-av-partial-coordinate']]).sort(), [['point-2', 'x'], ['point-3', 'y']]);
  assert(visibleText(bands[0]).includes('Y not observed')); assert(visibleText(bands[1]).includes('X not observed'));
  assert(partialMarks[0].body.includes('1000000000; Y missing')); assert(partialMarks[1].body.includes('-9; X missing'));
  const [, ...rows] = tableCells(html); assert.equal(rows.length, points.length);
  const byId = new Map(rows.map(row => [suppliedId(row[0]), row]));
  assert.equal(visibleText(byId.get('partial-x')[4]), '1000000000'); assert.equal(visibleText(byId.get('partial-x')[5]), 'Missing');
  assert.equal(visibleText(byId.get('partial-y')[4]), 'Missing'); assert.equal(visibleText(byId.get('partial-y')[5]), '-9');
  assert(byId.get('absent')[6].includes('No coordinates retained'));
  const scopes = [...html.matchAll(/<div\b([^>]*data-av-coordinate-scope="([^"]+)"[^>]*)>/g)].map(match => ({ tag: match[0], scope: match[2] }));
  assert(scopes.find(scope => scope.scope === 'known') && !scopes.find(scope => scope.scope === 'known').tag.includes(' hidden'));
  const explicit = render({ coordinateScope: 'complete', points: points.slice(0, 2) });
  const selected = explicit.match(/<div\b[^>]*data-av-coordinate-scope="complete"[^>]*>/);
  assert(selected && !selected[0].includes(' hidden'), 'An explicitly selected complete scope must exist even when all observations are complete');
  assert.equal((explicit.slice(selected.index).match(/class="av-terrain-point"/g) || []).length, 2);
  geometry(html); geometry(explicit);
});

check('supplied statuses and full Unicode labels remain visibly attributable', () => {
  const label = 'A'.repeat(20) + '😀 condition 👨‍👩‍👧‍👦 e\u0301 ' + '日本語'.repeat(8);
  const html = V.distribution({ title: 'Status and text', axis: 'Time', groups: [{ id: 'group', label: 'Same group', observations: [{ label, value: 4, status: 'failed' }, { label: 'Supported numeric', value: 4, status: 'supported' }, { label: 'Failed missing', value: null, status: 'failed' }, { label: 'Unknown missing', value: null, status: 'missing' }] }] });
  const rows = svgLayers(html).find(layer => layer.attrs['data-av-axis-layer'] === 'rows'); assert(rows);
  const visible = visibleText(rows.markup); assert(visible.includes(label)); assert(visible.includes('— failed')); assert(visible.includes('— supported')); assert(visible.includes('— missing'));
  const plot = visibleText(plotMarkup(html)); assert(plot.includes('Missing (failed)')); assert(plot.includes('Missing (missing)'));
  assert(!/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(visible));
  assert(!visible.includes('…'), 'Full reader labels cannot be replaced with truncation');
  const pair = V.pairedComparison({ title: 'Unicode pair', axis: 'Value', leftLabel: 'A', rightLabel: 'B', pairs: [{ label, left: -0, right: 0 }] });
  const pairRows = svgLayers(pair).find(layer => layer.attrs['data-av-axis-layer'] === 'rows'); assert(visibleText(pairRows.markup).includes(label));
  const [, values] = tableCells(pair); assert.equal(visibleText(values[1]), '-0'); assert.equal(visibleText(values[2]), '0');
  geometry(html); geometry(pair);
});

check('heatmap does not hide zero or negative values through opacity', () => {
  const html = V.heatmap({ title: 'Signed', rows: [{ id: 'r', label: 'Row' }], columns: [{ id: 'n', label: 'Negative' }, { id: 'z', label: 'Zero' }, { id: 'p', label: 'Positive' }, { id: 'm', label: 'Missing' }], cells: [{ row: 'r', column: 'n', value: -8 }, { row: 'r', column: 'z', value: 0 }, { row: 'r', column: 'p', value: 8 }, { row: 'r', column: 'm', value: null }] });
  assert(!html.includes('opacity:'));
  assert(html.includes('>-8</div>')); assert(html.includes('>0</div>')); assert(html.includes('>Missing</div>'));
  const colors = [...html.matchAll(/background-color:([^"]+)/g)].map(m => m[1]);
  assert.notEqual(colors[0], colors[1]); assert.notEqual(colors[1], colors[2]);
  const amounts = [...html.matchAll(/data-av-magnitude="([^"]+)"/g)].map(match => Number(match[1]));
  assert.deepEqual(amounts.slice(0, 3), [0, 50, 100]);
  for (let i = 0; i < 3; i++) assert(colors[i].includes(`var(--av-heat-high) ${amounts[i]}%`), 'Visual shading must use the retained normalized magnitude');
  assert(!colors.some(color => /hsl\(/.test(color)), 'The quantitative scale should use the declared theme roles');
});

check('frontier edges only use declared complete points; no inferred edge exists', () => {
  const input = { title: 'Tradeoff', xAxis: 'X', yAxis: 'Y', points: [{ id: 'a', label: 'A', x: -1, y: 4 }, { id: 'b', label: 'B', x: 2, y: null }] };
  assert(!V.scatterPlot(input).includes('<polyline'));
  assert.throws(() => V.scatterPlot({ ...input, frontiers: [{ label: 'Bad', pointIds: ['a', 'b'] }] }), /complete/);
  assert.throws(() => V.evidenceLineage({ title: '', nodes: [], edges: [{ from: 'a', to: 'b', relation: 'supports' }] }), /undeclared/);
});

check('freshness validates actual calendar dates and preserves unknown dates', () => {
  const base = { title: 'Freshness', events: [{ label: 'X', source: 'S', date: '2026-02-03', event: 'Observed' }, { label: 'Y', source: 'S', date: null, event: 'Unknown', note: 'Date not retained' }] };
  const html = V.evidenceFreshness(base); geometry(html);
  assert(html.includes('Date not retained'));
  assert.throws(() => V.evidenceFreshness({ ...base, events: [{ ...base.events[0], date: '2026-02-30' }] }), /Invalid/);
  assert.throws(() => V.evidenceFreshness({ ...base, events: [{ ...base.events[0], date: '02/03/2026' }] }), /ISO/);
});

check('scenarios use native controls and preserve conditional recommendations', () => {
  const html = V.scenarioExplorer({ title: 'Scenarios', scenarios: [{ label: 'Offline', condition: 'No network', outcomes: [{ alternative: 'A', outcome: 'Preferred under this supplied condition', status: 'conditional', note: 'Upstream adjudication' }] }, { label: 'Online', condition: 'Network available', outcomes: [] }] });
  assert.equal((html.match(/<summary>/g) || []).length, 2);
  assert(html.includes('Preferred under this supplied condition'));
  assert(html.includes('Upstream adjudication'));
  assert(/<details\b[^>]*data-av-object="scenario-0"[^>]*\sopen>/.test(html));
});

check('artifact and extension inputs cannot supply executable content', () => {
  assert.throws(() => V.nativeArtifactViewer({ title: '', artifacts: [{ label: 'A', mediaType: 'image/svg+xml', imageData: 'data:image/svg+xml;base64,PHN2Zz4=', alt: 'A' }] }), /SVG/);
  assert.throws(() => V.nativeArtifactViewer({ title: '', artifacts: [{ label: 'A', mediaType: 'image/png', imageData: 'https://remote.test/a.png', alt: 'A' }] }), /embedded/);
  assert.throws(() => V.renderExtension({ title: '', purpose: 'Show input', blocks: [{ kind: 'html', text: '<script>' }] }), /Unknown/);
  assert(V.nativeArtifactViewer({ title: '', artifacts: [{ label: 'HTML as source', mediaType: 'text/html', text: '<script>alert(1)</script>' }] }).includes('&lt;script&gt;'));
});

check('expanded presentations preserve supplied grounds without rank conversion', () => {
  const confidence = V.confidenceProvenance({ title: 'Grounds', claims: [{ claim: 'C', judgment: '0.8 as supplied; calibration not established', basis: [{ dimension: 'Coverage', observation: '3 cases', note: 'Narrow domain' }], evidence: [{ label: 'Original assessment' }] }] });
  assert(confidence.includes('0.8 as supplied')); assert(confidence.includes('Narrow domain'));
  const unknowns = V.unknownsMap({ title: 'Unknown', alternatives: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }], issues: [{ label: 'Latency', relevance: 'Needed for rollout', affected: [{ alternative: 'a', consequence: 'Decision remains conditional' }] }] });
  assert(unknowns.includes('No relationship supplied')); assert(unknowns.includes('Decision remains conditional'));
  const profile = V.reliabilityProfile({ title: 'Conditions', conditions: [{ id: 'offline', label: 'Offline' }], behaviors: [{ id: 'complete', label: 'Completion' }], observations: [{ condition: 'offline', behavior: 'complete', value: 'Fails with missing input', status: 'failed', note: 'Observed scope' }] });
  assert(profile.includes('Operating condition')); assert(profile.includes('Observed scope'));
  const history = V.decisionHistory({ title: 'History', decisions: [{ label: 'D', when: 'Round 2', decision: 'Accept conditionally', availableThen: 'Native artifact', changesSince: 'Scope narrowed', supersedes: 'Round 1' }] });
  assert(history.includes('Available then')); assert(history.includes('Scope narrowed')); assert(history.includes('Round 1'));
});

console.log(`${checks} renderer contracts passed`);
