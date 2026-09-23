const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../../mermaid-patches/venn-labels.js'), 'utf8'), context);
const place = context.avVennLabelPosition;
function check(members, others, width, height, preferred, required = true) {
  const result = place(members, others, width, height, preferred);
  if (required) assert.ok(result, 'expected usable label placement');
  if (!result) return;
  const corners = [-1, 1].flatMap(dx => [-1, 1].map(dy => [result.x + dx * width / 2, result.y + dy * height / 2]));
  for (const c of members) for (const [x, y] of corners) assert.ok(Math.hypot(x - c.x, y - c.y) <= c.radius - 2 + 1e-7);
  for (const c of others) {
    const nearestX = Math.max(result.x - width / 2, Math.min(result.x + width / 2, c.x));
    const nearestY = Math.max(result.y - height / 2, Math.min(result.y + height / 2, c.y));
    assert.ok(Math.hypot(nearestX - c.x, nearestY - c.y) >= c.radius + 2 - 1e-7);
  }
  return result;
}
const left = {x: -40, y: 0, radius: 100}, right = {x: 40, y: 0, radius: 100};
check([left, right], [], 40, 50, {x: 0, y: 0});
check([left], [right], 30, 40, {x: -40, y: 0});
check([left, right], [{x: 0, y: 55, radius: 45}], 25, 30, {x: 0, y: 10});
assert.equal(place([left], [], 201, 10, left), null);
assert.equal(place([left], [left], 1, 1, left), null);
assert.equal(place([], [], 10, 10, {x: 0, y: 0}), null);
assert.equal(place([left], [], Infinity, 10, left), null);
const a = check([left, right], [], 32, 24, {x: 10, y: 8});
const shifted = c => ({...c, x: c.x + 150, y: c.y - 80});
const b = check([shifted(left), shifted(right)], [], 32, 24, {x: 160, y: -72});
assert.ok(Math.abs(a.x + 150 - b.x) < 1e-7 && Math.abs(a.y - 80 - b.y) < 1e-7);
for (let separation = 10; separation < 180; separation += 17) {
  for (const width of [12, 36, 72]) {
    const one = {...left, x: 0}, two = {...right, x: separation};
    check([one, two], [], width, 18, {x: separation / 2, y: 0}, false);
    check([one], [two], width, 18, {x: -20, y: 0}, false);
  }
}
process.stdout.write('Venn rectangle membership, exclusion, infeasibility and translation checks passed. Native typography remains separate.\n');
