// Execute the packaged callback only; no DOM, renderer or browser is involved.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const artifact = path.resolve(__dirname,
  '../../../plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/vendor/mermaid/mermaid.min.js');
const source = fs.readFileSync(artifact, 'utf8');
const start = source.indexOf('r.calcIntersect=function(E,S){let R=E.width,L=');
const end = source.indexOf('},l}var aKn', start);
assert(start >= 0 && end > start, 'The pinned decision-shape implementation must remain identifiable');
const code = source.slice(start, end + 1);
const node = { id: 'decision', width: 120, height: 120, x: 30, y: -40 };
const calls = [];
const polygon = (shape, vertices, endpoint) => {
  const record = { shape, vertices: JSON.parse(JSON.stringify(vertices)), endpoint };
  calls.push(record);
  return record;
};
vm.runInNewContext(code, { r: node, Ur: { polygon } });
const target = { x: 180, y: 60 };
const expected = node.intersect(target);
// The block renderer installs only width, height and intersect on its graph
// node. Its callback therefore cannot depend on a copied calcIntersect method.
const graphNode = { width: node.width, height: node.height, intersect: node.intersect };
assert.deepEqual(graphNode.intersect(target), expected,
  'A diamond copied into the block graph must retain its own polygon calculation');
const detached = graphNode.intersect;
assert.deepEqual(detached(target), expected, 'Callback invocation must not depend on this');
const wrongOwner = { calcIntersect() { throw Error('Used an unrelated shape helper'); } };
assert.deepEqual(detached.call(wrongOwner, target), expected, 'A foreign owner cannot change diamond geometry');

node.width = 200;
node.height = 200;
node.x = -100;
node.y = 90;
const nextTarget = { x: -300, y: 45 };
const moved = graphNode.intersect(nextTarget);
assert.equal(moved.shape, node, 'Intersection retains the original, currently positioned shape');
assert.equal(moved.endpoint, nextTarget, 'The relationship endpoint is forwarded unchanged');
assert.deepEqual(moved.vertices, [{ x: 100, y: 0 }, { x: 200, y: -100 }, { x: 100, y: -200 }, { x: 0, y: -100 }],
  'The diamond perimeter follows current shape width instead of a stale graph copy');
assert.equal(calls.length, 5);
console.log('Diamond intersection contract passed: block-graph copies and detached callbacks retain the original shape, perimeter and relationship endpoint.');
