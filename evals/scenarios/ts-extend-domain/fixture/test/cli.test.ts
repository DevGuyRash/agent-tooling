// shelfwise run as the desk PCs run it: node bin/shelfwise.ts.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));

function shelfwise(...args: string[]) {
  const r = spawnSync(process.execPath, ['bin/shelfwise.ts', ...args], { cwd: root, encoding: 'utf8' });
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}

test('holds lists a branch oldest first', () => {
  const r = shelfwise('holds', '--branch', 'Eastside', 'test/data/holds.csv');
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.stdout, [
    'Holds for Eastside: 5 holds',
    '2026-09-27  #2251  waiting    The "good" weekend',
    '2026-09-28  #2231  waiting    The essentials of classic Italian cooking',
    '2026-09-29  #2236  waiting    Butterflies of the world',
    '2026-09-29  #2240  waiting    Soups, stews, and broths',
    '2026-09-30  #2245  ready      On food and cooking',
    '',
  ].join('\n'));
});

test('holds by status', () => {
  const r = shelfwise('holds', '--branch', 'Eastside', '--status', 'ready', 'test/data/holds.csv');
  assert.equal(r.stdout, 'Holds for Eastside: 1 hold\n2026-09-30  #2245  ready      On food and cooking\n');
});

test('holds stops at the first bad record', () => {
  const r = shelfwise('holds', '--branch', 'Eastside', 'test/data/bad.csv');
  assert.equal(r.status, 2);
  assert.equal(r.stdout, '');
  assert.equal(r.stderr, "shelfwise holds: test/data/bad.csv line 3: bad hold id '22x6'\n");
});

test('check reports every problem', () => {
  const r = shelfwise('check', 'test/data/bad.csv');
  assert.equal(r.status, 1);
  assert.equal(r.stdout, [
    "line 3: bad hold id '22x6'",
    "line 4: bad date '2026-02-30'",
    "line 5: unknown status 'lost'",
    'line 6: expected 6 fields, found 4',
    '5 holds, 4 problems',
    '',
  ].join('\n'));
});

test('a clean export checks clean', () => {
  const r = shelfwise('check', 'test/data/holds.csv');
  assert.equal(r.status, 0);
  assert.equal(r.stdout, '7 holds, 0 problems\n');
});

test('usage errors', () => {
  assert.equal(shelfwise('holds', 'test/data/holds.csv').status, 2);
  assert.equal(shelfwise('frobnicate').status, 2);
  assert.match(shelfwise('holds', '--branch', 'X', '--colour', 'red', 'f').stderr, /usage: shelfwise/);
  assert.equal(shelfwise('holds', '--branch', 'X', 'missing.csv').stderr, 'shelfwise holds: cannot read missing.csv: ENOENT\n');
});
