// Source geometry and faithful generated markup, not native-browser visual approval.
const assert = require('node:assert/strict'), path = require('node:path');
const { layoutGraph } = require(path.join(process.argv[2], 'graph-layout.js'));
const overlaps = (a, b) => a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
const inside = (p, r) => p.x > r.x + 1e-7 && p.x < r.x + r.width - 1e-7 && p.y > r.y + 1e-7 && p.y < r.y + r.height - 1e-7;
const boundary = (p, r) => p.x >= r.x - 1e-7 && p.x <= r.x + r.width + 1e-7 && p.y >= r.y - 1e-7 && p.y <= r.y + r.height + 1e-7 && [p.x - r.x, p.x - r.x - r.width, p.y - r.y, p.y - r.y - r.height].some(delta => Math.abs(delta) < 1e-7);
function crosses(a, b, r) {
  assert(a.x === b.x || a.y === b.y, 'Routes must remain orthogonal');
  return a.x === b.x ? a.x > r.x + 1e-7 && a.x < r.x + r.width - 1e-7 && Math.max(a.y, b.y) > r.y + 1e-7 && Math.min(a.y, b.y) < r.y + r.height - 1e-7
    : a.y > r.y + 1e-7 && a.y < r.y + r.height - 1e-7 && Math.max(a.x, b.x) > r.x + 1e-7 && Math.min(a.x, b.x) < r.x + r.width - 1e-7;
}
function verify(layout, inputNodes, inputEdges) {
  assert.equal(layout.nodes.length, inputNodes.length); assert.equal(layout.edges.length, inputEdges.length);
  const boxes = [...layout.nodes, ...layout.edges.map(edge => edge.box)];
  for (const [i, box] of boxes.entries()) {
    assert([box.x, box.y, box.width, box.height].every(Number.isFinite));
    assert(box.x >= 0 && box.y >= 0 && box.x + box.width <= layout.width && box.y + box.height <= layout.height);
    for (const other of boxes.slice(i + 1)) assert(!overlaps(box, other), 'Text and node boxes overlap');
  }
  for (const edge of layout.edges) {
    const original = inputEdges[edge.index];
    assert.equal(edge.id, original.id); assert.equal(edge.from, original.from); assert.equal(edge.to, original.to); assert.equal(edge.label.text, original.relation);
    assert(boundary(edge.points[0], layout.nodes[edge.source])); assert(boundary(edge.points.at(-1), layout.nodes[edge.target]));
    for (const point of [...edge.points, ...edge.arrow]) assert(Number.isFinite(point.x) && Number.isFinite(point.y) && point.x >= 0 && point.y >= 0 && point.x <= layout.width && point.y <= layout.height);
    for (let i = 1; i < edge.points.length; i++) {
      for (const node of layout.nodes) assert(!crosses(edge.points[i - 1], edge.points[i], node), `Edge ${edge.id} enters node ${node.id}`);
      for (const other of layout.edges) if (other !== edge) assert(!crosses(edge.points[i - 1], edge.points[i], other.box), `Edge ${edge.id} enters label ${other.id}`);
    }
    assert.deepEqual(edge.arrow[0], edge.points.at(-1));
    assert(!inside(edge.arrow[1], layout.nodes[edge.target]) && !inside(edge.arrow[2], layout.nodes[edge.target]));
    const previous = edge.points.at(-2), tip = edge.arrow[0], base = { x: (edge.arrow[1].x + edge.arrow[2].x) / 2, y: (edge.arrow[1].y + edge.arrow[2].y) / 2 };
    assert((tip.x - previous.x) * (tip.x - base.x) + (tip.y - previous.y) * (tip.y - base.y) > 0, 'Arrow reverses supplied direction');
  }
  assert.equal(new Set(layout.edges.map(edge => JSON.stringify(edge.points))).size, layout.edges.length, 'Distinct relationships share their entire route');
}
const nodes = Array.from({ length: 5 }, (_, i) => ({ id: 'n' + i, label: 'Node ' + i, kind: 'record' }));
const single = [{ id: 'distant', from: 'n0', to: 'n4', relation: 'supports only within the retained session' }];
verify(layoutGraph(nodes, single), nodes, single);
const edges = [
  { id: 'support', from: 'n0', to: 'n1', relation: 'supports under the stated condition' },
  { id: 'objection', from: 'n0', to: 'n1', relation: 'contradicts a broader interpretation' },
  { id: 'reverse', from: 'n1', to: 'n0', relation: 'depends on its original source' },
  { id: 'loop-1', from: 'n0', to: 'n0', relation: 'revises an earlier position without changing identity' },
  { id: 'loop-2', from: 'n0', to: 'n0', relation: 'a distinct repeated self relationship' },
  { id: 'loop-3', from: 'n1', to: 'n1', relation: 'right-hand loop with complete wording' },
  { id: 'down', from: 'n0', to: 'n4', relation: 'reaches past an unrelated node' },
  { id: 'up', from: 'n4', to: 'n0', relation: 'returns to its original source' },
  { id: 'diagonal', from: 'n3', to: 'n0', relation: 'a diagonal relationship' },
];
for (const width of [240, 420, 1120, 1600]) verify(layoutGraph(nodes, edges, { width }), nodes, edges);
const unicodeNodes = [
  { id: 'same-prefix-'.repeat(8) + 'one', label: '日本語の条件を保持する👨‍👩‍👧‍👦 ' + 'W'.repeat(75), kind: 'source with a long complete kind' },
  { id: 'same-prefix-'.repeat(8) + 'two', label: '日本語の条件を保持する👨‍👩‍👧‍👦 ' + 'W'.repeat(75), kind: 'source with a long complete kind' },
];
const unicodeEdges = [{ id: 'relationship-'.repeat(6), from: unicodeNodes[0].id, to: unicodeNodes[1].id, relation: 'All conditions remain visible e\u0301 🇺🇸 👨‍👩‍👧‍👦\nincluding this second paragraph and its scope.' }];
verify(layoutGraph(unicodeNodes, unicodeEdges, { width: 1120 }), unicodeNodes, unicodeEdges);
verify(layoutGraph(unicodeNodes, unicodeEdges, { width: 1120, measure: text => [...text].length * 6 }), unicodeNodes, unicodeEdges);
verify(layoutGraph(unicodeNodes, unicodeEdges, { width: 1120.3, measure: text => [...text].reduce((sum, character) => sum + (character.codePointAt(0) % 9 + 1) * .731, 0) }), unicodeNodes, unicodeEdges);
const largeNodes = Array.from({ length: 36 }, (_, i) => ({ id: 'retained-' + i, label: 'Retained object ' + i, kind: 'observation' }));
const largeEdges = Array.from({ length: 35 }, (_, i) => ({ id: 'link-' + i, from: largeNodes[i].id, to: largeNodes[(i + 5) % largeNodes.length].id, relation: 'retains the supplied relationship ' + i }));
verify(layoutGraph(largeNodes, largeEdges), largeNodes, largeEdges);
verify(layoutGraph([nodes[0]], []), [nodes[0]], []);
assert.deepEqual(layoutGraph([], []).nodes, []);
assert.throws(() => layoutGraph(nodes, [{ ...single[0], to: 'absent' }]), /undeclared/);
assert.throws(() => layoutGraph(nodes, [single[0], single[0]]), /unique/);
assert.throws(() => layoutGraph(nodes, [], { width: 2 }), /at least 240/);

if (process.argv[3] === 'geometry') { console.log('graph text, obstacle routing, direction and bounds contracts passed'); process.exit(0); }
const { evidenceLineage } = require(path.join(process.argv[2], 'qualitative.js'));
const input = { title: 'Inspectable graph', nodes, edges: edges.map(edge => ({ ...edge, note: 'Grounds for ' + edge.id, evidence: [{ label: 'Original ' + edge.id, href: '#original-evidence' }] })) };
const rendered = evidenceLineage(input);
for (const edge of input.edges) { assert(rendered.includes(edge.relation)); assert(rendered.includes('Grounds for ' + edge.id)); assert(rendered.includes('data-av-edge-id="' + edge.id + '"')); }
assert(rendered.includes('<details class="av-inspector" open><summary>Inspect evidence</summary>'));
for (const key of [...nodes.map((_, i) => 'node-' + i), ...edges.map((_, i) => 'edge-' + i)]) { assert(rendered.includes('data-av-inspect="' + key + '"')); assert(rendered.includes('data-av-object="' + key + '"')); }
const differentMetrics = evidenceLineage({ ...input, context: { width: 760, measureText: text => text.length * 6 } });
assert.deepEqual([...rendered.matchAll(/data-av-inspect="([^"]+)"/g)].map(m => m[1]), [...differentMetrics.matchAll(/data-av-inspect="([^"]+)"/g)].map(m => m[1]));
const fallback = evidenceLineage({ title: 'Repeated occurrences', nodes: nodes.slice(0, 2), edges: [{ from: 'n0', to: 'n1', relation: 'same wording', note: 'first grounds' }, { id: 'Relation 1', from: 'n0', to: 'n1', relation: 'same wording', note: 'second grounds' }] });
assert(fallback.includes('Occurrence Relation 1')); assert(fallback.includes('first grounds')); assert(fallback.includes('second grounds')); assert(fallback.includes('(occurrence)'));
const unsafe = evidenceLineage({ title: '<script>unsafe</script>', nodes: [{ id: 'a', label: '<img src=x onerror=bad()>', kind: '<record>' }], edges: [{ from: 'a', to: 'a', relation: '<script>unsafe</script>', note: '<unsafe>' }] });
assert(!unsafe.includes('<script>')); assert(!unsafe.includes('<img')); assert(unsafe.includes('&lt;script&gt;unsafe&lt;/script&gt;')); assert(unsafe.includes('&lt;unsafe&gt;'));
console.log('graph text, obstacle routing, direction, identity and inspection contracts passed');
