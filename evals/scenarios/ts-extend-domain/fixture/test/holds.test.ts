import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { problem, readHolds } from '../src/holds.ts';

const data = fileURLToPath(new URL('data/', import.meta.url));

test('reads every hold', () => {
  const holds = readHolds(`${data}holds.csv`);
  assert.equal(holds.length, 7);
  assert.deepEqual(holds[2], {
    id: 2240, branch: 'Eastside', placed: '2026-09-29', title: 'Soups, stews, and broths', callNumber: '64.5 ABC',
    status: 'waiting', line: 4,
  });
});

test('problems', () => {
  assert.equal(problem(['1', 'B', '2026-01-01', 'T', '', 'waiting']), null);
  assert.equal(problem(['0', 'B', '2026-01-01', 'T', '', 'waiting']), "bad hold id '0'");
  assert.equal(problem(['1', '', '2026-01-01', 'T', '', 'waiting']), 'no branch');
  assert.equal(problem(['1', 'B', '2026-01-01', ' ', '', 'waiting']), 'no title');
});
