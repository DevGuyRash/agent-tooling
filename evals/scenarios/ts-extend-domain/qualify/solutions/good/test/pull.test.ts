import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { compare, parse } from '../src/callnumber.ts';

const root = fileURLToPath(new URL('..', import.meta.url));

function shelf(...texts: string[]): string[] {
  return [...texts].sort((a, b) => compare(parse(a), parse(b)));
}

test('shelf order', () => {
  assert.deepEqual(shelf('813 S64', '813 S637', '813 S6', 'FIC ADAMS', '641.6 A', '641.5945 A', 'J 001 A'),
    ['641.5945 A', '641.6 A', '813 S6', '813 S637', '813 S64', 'FIC ADAMS', 'J 001 A']);
  assert.deepEqual(shelf("FIC OKAFOR", "FIC O'BRIEN", 'FIC OATES'), ['FIC OATES', "FIC O'BRIEN", 'FIC OKAFOR']);
});

test('pull list from the sample export', () => {
  const r = spawnSync(process.execPath, ['bin/shelfwise.ts', 'pull', '--branch', 'Eastside', 'test/data/holds.csv'],
    { cwd: root, encoding: 'utf8' });
  assert.equal(r.status, 1);
  assert.equal(r.stdout, [
    'Pull list for Eastside: 4 holds',
    '',
    'Adult · 600s',
    '  641.5945 HAZ 2019  The essentials of classic Italian cooking  #2231',
    '',
    'Adult · Fiction',
    "  FIC O'BRIEN        The \"good\" weekend  #2251",
    '',
    "Children's · 500s",
    '  J 595.789 KIR      Butterflies of the world  #2236',
    '',
    'Not pulled, call number needs fixing:',
    "  #2240  \"64.5 ABC\": bad class number '64.5'",
    '',
  ].join('\n'));
});
